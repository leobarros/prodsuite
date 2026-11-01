"""Módulo de tarefas: Kanban, edição, transições e exclusão."""

from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from forms import TaskForm
from models import (
    BoardColumn,
    Category,
    Project,
    TASK_QUADRANTS,
    TASK_STATUSES,
    TASK_STATUS_LABELS,
    Scratchpad,
    Task,
    TaskColumnStay,
    normalize_tags,
    utcnow,
)
from services.boards import (
    active_project,
    ensure_default_project,
    project_by_id,
    project_columns,
)
from services.categories import (
    CATEGORY_ICON_CHOICES,
    CATEGORY_ICON_KEYS,
    MAX_CATEGORIES,
    category_by_id,
    category_by_key,
    category_choices,
    ensure_categories,
    new_category_key,
)
from services.planning import week_start_for
from services.task_creation import create_task_from_form
from services.timeutils import local_today

tasks_bp = Blueprint("tasks", __name__)

MAX_COLUMNS = 12


def _format_column_duration(seconds: int) -> str:
    total = max(0, int(seconds or 0))
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes:02d}min"
    if minutes:
        return f"{minutes} min"
    return f"{total}s"


def _record_column_stay(task: Task, now=None) -> None:
    if not task.column_id:
        task.column_entered_at = now
        return
    entered = task.column_entered_at
    if entered is None:
        task.column_entered_at = now
        return
    now = now or utcnow()
    seconds = max(0, int((now - entered).total_seconds()))
    if seconds <= 0:
        task.column_entered_at = now
        return
    column = BoardColumn.query.filter_by(
        id=task.column_id, user_id=task.user_id
    ).first()
    db.session.add(
        TaskColumnStay(
            user_id=task.user_id,
            task_id=task.id,
            project_id=task.project_id,
            column_id=task.column_id,
            column_title=column.title if column else "Coluna removida",
            entered_at=entered,
            left_at=now,
            duration_seconds=seconds,
        )
    )
    task.column_entered_at = now


def _set_task_column(task: Task, column: BoardColumn, now=None) -> None:
    """Move a tarefa e deriva conclusão da coluna de conclusão."""
    now = now or utcnow()
    if task.column_id != column.id:
        _record_column_stay(task, now)
        task.column_id = column.id
        task.project_id = column.project_id
        task.column_entered_at = now
        max_position = (
            db.session.query(func.max(Task.position))
            .filter(
                Task.user_id == task.user_id,
                Task.column_id == column.id,
                Task.archived_at.is_(None),
                Task.id != task.id,
            )
            .scalar()
            or 0
        )
        task.position = max_position + 1
    if column.kind == "done":
        if not task.is_done:
            task.move_to("done")
    elif task.is_done:
        task.move_to("todo")


def _task_timing_context(task: Task) -> dict:
    stays = (
        TaskColumnStay.query.filter_by(user_id=task.user_id, task_id=task.id)
        .order_by(TaskColumnStay.entered_at.desc())
        .all()
    )
    current_seconds = 0
    if task.column_entered_at:
        current_seconds = max(
            0, int((utcnow() - task.column_entered_at).total_seconds())
        )
    return {
        "column_stays": stays,
        "current_column_seconds": current_seconds,
        "current_column_label": _format_column_duration(current_seconds),
    }


def _get_task(task_id: int) -> Task:
    """404 para tarefa inexistente **ou de outro usuário** (sem enumeração)."""
    return Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()


def _prepare_category_form(form, categories, *, reset_default: bool = False):
    form.category.choices = category_choices(categories)
    valid_keys = {category.key for category in categories}
    if reset_default or not form.category.data or form.category.data not in valid_keys:
        form.category.data = categories[0].key


def _column_by_id(raw_id, user=None) -> BoardColumn | None:
    user = user or current_user
    try:
        column_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return BoardColumn.query.filter_by(
        id=column_id, user_id=user.id
    ).first()


def _board_column_counts(columns, tasks) -> dict:
    return {
        str(column.id): sum(1 for task in tasks if task.column_id == column.id)
        for column in columns
    }


def _status_counts() -> dict:
    from sqlalchemy import func

    rows = (
        db.session.query(Task.status, func.count(Task.id))
        .filter(Task.user_id == current_user.id)
        .group_by(Task.status)
        .all()
    )
    counts = {status: 0 for status in TASK_STATUSES}
    counts.update(dict(rows))
    counts["open"] = counts["todo"] + counts["doing"]
    return counts


def _sort_tasks(tasks: list[Task]) -> list[Task]:
    return sorted(
        tasks,
        key=lambda t: (
            t.position or 0,
            not t.is_mit,
            t.quadrant_rank,
            t.due_date or date.max,
            -t.id,
        ),
    )


def _mit_count(exclude_id: int | None = None) -> int:
    query = Task.query.filter(
        Task.user_id == current_user.id, Task.is_mit.is_(True), Task.status != "done"
    )
    if exclude_id is not None:
        query = query.filter(Task.id != exclude_id)
    return query.count()


def _redirect_back(default_endpoint: str = "tasks.index"):
    """Aceita apenas caminhos internos para voltar ao planner/quadro."""
    target = request.form.get("next") or request.args.get("next")
    if target and target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect(url_for(default_endpoint))


@tasks_bp.route("/tarefas", methods=["GET", "POST"])
@login_required
def index():
    project = active_project(current_user, request.args.get("projeto"), session)
    projects = (
        Project.query.filter_by(user_id=current_user.id)
        .order_by(Project.position.asc(), Project.id.asc())
        .all()
    )
    categories = ensure_categories(current_user)
    columns = project_columns(project) if project else []
    form = TaskForm()
    _prepare_category_form(
        form, categories, reset_default=request.method == "GET"
    )
    if request.method == "GET" and not form.due_date.data:
        form.due_date.data = local_today()
    open_modal = request.args.get("nova") == "1"

    if form.validate_on_submit():
        task = create_task_from_form(
            current_user,
            form,
            project,
            columns,
            categories,
            request.form.get("column_id"),
        )
        if task is None:
            return redirect(url_for("tasks.index", projeto=project.id) if project else url_for("tasks.index"))
        db.session.commit()
        flash("Tarefa criada.", "success")
        return _redirect_back()

    if request.method == "POST":
        open_modal = True
        flash("Revise os campos da tarefa.", "danger")

    # Filtros do método: hoje, prioridades, tarefas rápidas e matriz.
    filters = {
        "quadrante": request.args.get("quadrante", ""),
        "categoria": request.args.get("categoria", ""),
        "filtro": request.args.get("filtro", ""),
    }
    if filters["quadrante"] not in TASK_QUADRANTS:
        filters["quadrante"] = ""
    if filters["categoria"] not in {category.key for category in categories}:
        filters["categoria"] = ""
    if filters["filtro"] not in {"hoje", "mit", "rapidas"}:
        filters["filtro"] = ""

    tasks_query = Task.query.filter_by(user_id=current_user.id)
    tasks_query = tasks_query.filter(Task.archived_at.is_(None))
    tasks_query = (
        tasks_query.filter(Task.project_id == project.id)
        if project
        else tasks_query.filter(db.false())
    )
    if filters["quadrante"]:
        tasks_query = tasks_query.filter(Task.quadrant == filters["quadrante"])
    if filters["categoria"]:
        tasks_query = tasks_query.filter(Task.category == filters["categoria"])
    today = local_today()
    filter_counts = {
        "todas": tasks_query.count(),
        "hoje": tasks_query.filter(
            Task.status != "done",
            Task.due_date == today,
        ).count(),
        "mit": tasks_query.filter(
            Task.status != "done", Task.is_mit.is_(True)
        ).count(),
        "rapidas": tasks_query.filter(
            Task.status != "done", Task.estimate_pomodoros <= 1
        ).count(),
    }

    if filters["filtro"] == "hoje":
        tasks_query = tasks_query.filter(
            Task.status != "done",
            Task.due_date == today,
        )
    elif filters["filtro"] == "mit":
        tasks_query = tasks_query.filter(
            Task.status != "done", Task.is_mit.is_(True)
        )
    elif filters["filtro"] == "rapidas":
        tasks_query = tasks_query.filter(
            Task.status != "done", Task.estimate_pomodoros <= 1
        )

    tasks_all = tasks_query.order_by(Task.updated_at.desc()).all()
    active_filter = next((value for value in filters.values() if value), "")

    column_tasks: dict[int, list[Task]] = {column.id: [] for column in columns}
    for task in tasks_all:
        if task.column_id in column_tasks:
            column_tasks[task.column_id].append(task)
    for column in columns:
        column_tasks[column.id] = _sort_tasks(column_tasks[column.id])

    filtered_counts = {
        "done": sum(1 for task in tasks_all if task.status == "done"),
        "open": sum(1 for task in tasks_all if task.status != "done"),
    }
    column_counts = {
        column.id: len(column_tasks[column.id]) for column in columns
    }
    selected_column_id = (
        int(request.form.get("column_id"))
        if request.form.get("column_id", "").isdigit()
        else (columns[0].id if columns else None)
    )

    return render_template(
        "tasks.html",
        form=form,
        project=project,
        projects=projects,
        board_columns=columns,
        column_tasks=column_tasks,
        column_counts=column_counts,
        counts=filtered_counts,
        open_modal=open_modal,
        today=local_today(),
        filters=filters,
        active_filter=active_filter,
        selected_column_id=selected_column_id,
        categories=categories,
        category_icon_choices=CATEGORY_ICON_CHOICES,
        filter_counts=filter_counts,
    )


@tasks_bp.get("/tarefas/<int:task_id>/editar")
@login_required
def edit(task_id: int):
    task = _get_task(task_id)
    project = task.project or ensure_default_project(current_user)
    if project is None:
        flash("Crie um projeto e uma coluna antes de editar a tarefa.", "warning")
        return redirect(url_for("tasks.index"))
    columns = project_columns(project)
    categories = ensure_categories(current_user)
    form = TaskForm(obj=task)
    _prepare_category_form(form, categories)
    return render_template(
        "task_edit.html",
        form=form,
        task=task,
        board_columns=columns,
        categories=categories,
        project=project,
        **_task_timing_context(task),
    )


@tasks_bp.post("/tarefas/<int:task_id>/editar")
@login_required
def update(task_id: int):
    task = _get_task(task_id)
    project = task.project or ensure_default_project(current_user)
    if project is None:
        flash("Crie um projeto e uma coluna antes de editar a tarefa.", "warning")
        return redirect(url_for("tasks.index"))
    columns = project_columns(project)
    categories = ensure_categories(current_user)
    form = TaskForm(obj=task)
    _prepare_category_form(form, categories)
    if not form.validate_on_submit():
        flash("Revise os campos da tarefa.", "danger")
        return (
            render_template(
                "task_edit.html",
                form=form,
                task=task,
                board_columns=columns,
                categories=categories,
                project=project,
                **_task_timing_context(task),
            ),
            400,
        )

    task.title = form.title.data
    task.description = form.description.data or ""
    task.estimate_pomodoros = form.estimate_pomodoros.data or 0
    task.due_date = form.due_date.data
    task.category = form.category.data or categories[0].key
    task.quadrant = form.quadrant.data or None
    task.tags = normalize_tags(form.tags.data)

    wants_mit = bool(form.is_mit.data)
    if wants_mit and not task.is_mit and _mit_count(exclude_id=task.id) >= 3:
        flash(
            "Você já tem 3 prioridades do dia. Remova uma antes de adicionar outra.",
            "warning",
        )
        wants_mit = False
    task.is_mit = wants_mit
    selected_column = _column_by_id(request.form.get("column_id"))
    if selected_column is None or selected_column.project_id != project.id:
        selected_column = _column_by_id(task.column_id)
    if selected_column is None and columns:
        selected_column = columns[0]
    if selected_column is None or not columns:
        flash("Crie uma coluna para mover esta tarefa.", "warning")
        return redirect(url_for("tasks.edit", task_id=task.id))
    _set_task_column(task, selected_column)
    explicit_status = (request.form.get("status") or "").strip()
    if explicit_status in TASK_STATUSES:
        task.move_to(explicit_status)
    db.session.commit()
    flash("Tarefa atualizada.", "success")
    return _redirect_back()


@tasks_bp.post("/tarefas/<int:task_id>/status")
@login_required
def update_status(task_id: int):
    task = _get_task(task_id)
    payload = request.get_json(silent=True) or request.form
    status = (payload.get("status") or "").strip()

    if status not in TASK_STATUSES:
        if request.is_json or request.headers.get("X-Requested-With"):
            return jsonify(ok=False, error="Status inválido."), 400
        flash("Status inválido.", "danger")
        return redirect(url_for("tasks.index"))

    task.move_to(status)
    db.session.commit()

    if request.is_json or request.headers.get("X-Requested-With"):
        return jsonify(
            ok=True,
            task={
                "id": task.id,
                "status": task.status,
                "status_label": TASK_STATUS_LABELS[task.status],
                "column_id": task.column_id,
                "is_done": task.is_done,
                "is_archived": task.is_archived,
                "archived_at": task.archived_at.isoformat()
                if task.archived_at
                else None,
                "completed_at": task.completed_at.isoformat()
                if task.completed_at
                else None,
            },
            counts=_status_counts(),
        )

    return _redirect_back()


@tasks_bp.post("/tarefas/quadros")
@login_required
def create_project():
    name = (request.form.get("name") or "").strip()
    if len(name) < 2 or len(name) > 60:
        flash("Use um nome de quadro entre 2 e 60 caracteres.", "danger")
        return redirect(url_for("tasks.index"))
    projects = Project.query.filter_by(user_id=current_user.id).all()
    if any(project.name.casefold() == name.casefold() for project in projects):
        flash("Já existe um quadro com esse nome.", "warning")
        return redirect(url_for("tasks.index"))

    project = Project(
        user_id=current_user.id,
        name=name,
        position=max((item.position for item in projects), default=-1) + 1,
    )
    db.session.add(project)
    db.session.commit()
    session["active_project_id"] = project.id
    flash("Quadro criado. Agora adicione as primeiras colunas.", "success")
    return redirect(url_for("tasks.index", projeto=project.id))


@tasks_bp.post("/tarefas/quadros/<int:project_id>/editar")
@login_required
def edit_project(project_id: int):
    project = project_by_id(current_user, project_id)
    if project is None:
        return redirect(url_for("tasks.index"))
    name = (request.form.get("name") or "").strip()
    if len(name) < 2 or len(name) > 60:
        flash("Use um nome de quadro entre 2 e 60 caracteres.", "danger")
        return redirect(url_for("tasks.index", projeto=project.id))
    duplicate = Project.query.filter(
        Project.user_id == current_user.id,
        Project.id != project.id,
        func.lower(Project.name) == name.lower(),
    ).first()
    if duplicate:
        flash("Já existe um quadro com esse nome.", "warning")
        return redirect(url_for("tasks.index", projeto=project.id))
    project.name = name
    db.session.commit()
    flash("Quadro renomeado.", "success")
    return redirect(url_for("tasks.index", projeto=project.id))


@tasks_bp.post("/tarefas/quadros/<int:project_id>/excluir")
@login_required
def delete_project(project_id: int):
    projects = Project.query.filter_by(user_id=current_user.id).all()
    project = project_by_id(current_user, project_id)
    if project is None:
        return redirect(url_for("tasks.index"))
    tasks_to_move = Task.query.filter_by(
        user_id=current_user.id, project_id=project.id
    ).all()
    remaining = [item for item in projects if item.id != project.id]
    if tasks_to_move and remaining:
        target = remaining[0]
        target_columns = project_columns(target)
        if not target_columns:
            target_columns = [
                BoardColumn(
                    user_id=current_user.id,
                    project_id=target.id,
                    title="Entrada",
                    kind="todo",
                    position=0,
                )
            ]
            db.session.add(target_columns[0])
            db.session.flush()
        target_column = target_columns[0]
        for task in tasks_to_move:
            _set_task_column(task, target_column)
    elif tasks_to_move:
        # O último projeto está sendo removido. A confirmação da interface
        # deixa claro que as tarefas dele também serão excluídas.
        for task in tasks_to_move:
            db.session.delete(task)

    # Persist the new project/column references before deleting the project;
    # otherwise the ORM can null the moved tasks' foreign keys on flush.
    db.session.commit()
    db.session.delete(project)
    for position, item in enumerate(remaining):
        item.position = position
    db.session.commit()
    session.pop("active_project_id", None)
    if tasks_to_move and remaining:
        flash("Projeto removido. As tarefas foram movidas para outro projeto.", "info")
    elif tasks_to_move:
        flash("Projeto removido junto com as tarefas dele.", "info")
    else:
        flash("Projeto removido.", "info")
    if remaining:
        session["active_project_id"] = remaining[0].id
        return redirect(url_for("tasks.index", projeto=remaining[0].id))
    return redirect(url_for("tasks.index"))


@tasks_bp.post("/tarefas/categorias")
@login_required
def create_category():
    categories = ensure_categories(current_user)
    name = (request.form.get("name") or "").strip()
    icon = (request.form.get("icon") or "bi-tag").strip()

    if len(name) < 2 or len(name) > 40:
        flash("Use um nome de categoria entre 2 e 40 caracteres.", "danger")
        return redirect(url_for("tasks.index"))
    if icon not in CATEGORY_ICON_KEYS:
        icon = "bi-tag"
    if len(categories) >= MAX_CATEGORIES:
        flash(f"Você pode ter no máximo {MAX_CATEGORIES} categorias.", "warning")
        return redirect(url_for("tasks.index"))
    if any(category.name.casefold() == name.casefold() for category in categories):
        flash("Já existe uma categoria com esse nome.", "warning")
        return redirect(url_for("tasks.index"))

    db.session.add(
        Category(
            user_id=current_user.id,
            key=new_category_key(),
            name=name,
            icon=icon,
            position=max((item.position for item in categories), default=-1) + 1,
        )
    )
    db.session.commit()
    flash("Categoria criada.", "success")
    return redirect(url_for("tasks.index"))


@tasks_bp.post("/tarefas/categorias/<int:category_id>/editar")
@login_required
def edit_category(category_id: int):
    categories = ensure_categories(current_user)
    category = category_by_id(current_user, category_id)
    if category is None:
        return redirect(url_for("tasks.index"))
    name = (request.form.get("name") or "").strip()
    icon = (request.form.get("icon") or category.icon).strip()

    if len(name) < 2 or len(name) > 40:
        flash("Use um nome de categoria entre 2 e 40 caracteres.", "danger")
        return redirect(url_for("tasks.index"))
    if icon not in CATEGORY_ICON_KEYS:
        icon = category.icon
    if any(
        item.id != category.id and item.name.casefold() == name.casefold()
        for item in categories
    ):
        flash("Já existe uma categoria com esse nome.", "warning")
        return redirect(url_for("tasks.index"))

    category.name = name
    category.icon = icon
    db.session.commit()
    flash("Categoria atualizada.", "success")
    return redirect(url_for("tasks.index"))


@tasks_bp.post("/tarefas/categorias/<int:category_id>/excluir")
@login_required
def delete_category(category_id: int):
    categories = ensure_categories(current_user)
    category = category_by_id(current_user, category_id)
    if category is None:
        return redirect(url_for("tasks.index"))
    if len(categories) <= 1:
        flash("Você precisa manter pelo menos uma categoria.", "warning")
        return redirect(url_for("tasks.index"))

    target = next(item for item in categories if item.id != category.id)
    Task.query.filter_by(
        user_id=current_user.id, category=category.key
    ).update({"category": target.key}, synchronize_session=False)
    db.session.delete(category)
    db.session.flush()
    remaining = (
        Category.query.filter_by(user_id=current_user.id)
        .order_by(Category.position.asc(), Category.id.asc())
        .all()
    )
    for position, item in enumerate(remaining):
        item.position = position
    db.session.commit()
    flash("Categoria removida. As tarefas foram para outra categoria.", "info")
    return redirect(url_for("tasks.index"))


@tasks_bp.post("/tarefas/colunas")
@login_required
def create_column():
    project = project_by_id(current_user, request.form.get("project_id"))
    if project is None:
        project = active_project(current_user, None, session)
    if project is None:
        flash("Crie um projeto antes de adicionar colunas.", "warning")
        return redirect(url_for("tasks.index"))
    columns = project_columns(project)
    title = (request.form.get("title") or "").strip()
    is_done = bool(request.form.get("is_done"))

    if not title:
        flash("Dê um nome para a coluna.", "danger")
        return redirect(url_for("tasks.index", projeto=project.id))
    if len(title) > 50:
        flash("O nome da coluna pode ter no máximo 50 caracteres.", "danger")
        return redirect(url_for("tasks.index", projeto=project.id))
    if len(columns) >= MAX_COLUMNS:
        flash(
            f"Você pode ter no máximo {MAX_COLUMNS} colunas.",
            "warning",
        )
        return redirect(url_for("tasks.index", projeto=project.id))
    if BoardColumn.query.filter(
        BoardColumn.user_id == current_user.id,
        BoardColumn.project_id == project.id,
        func.lower(BoardColumn.title) == title.lower(),
    ).first():
        flash("Já existe uma coluna com esse nome.", "warning")
        return redirect(url_for("tasks.index", projeto=project.id))
    if is_done and any(column.kind == "done" for column in columns):
        flash("Este projeto já tem uma coluna de conclusão.", "warning")
        return redirect(url_for("tasks.index", projeto=project.id))

    next_position = max((column.position for column in columns), default=-1) + 1
    db.session.add(
        BoardColumn(
            user_id=current_user.id,
            project_id=project.id,
            title=title,
            kind="done" if is_done else "todo",
            position=next_position,
        )
    )
    db.session.commit()
    flash("Coluna criada.", "success")
    return redirect(url_for("tasks.index", projeto=project.id))


@tasks_bp.post("/tarefas/colunas/<int:column_id>/editar")
@login_required
def edit_column(column_id: int):
    column = BoardColumn.query.filter_by(
        id=column_id, user_id=current_user.id
    ).first_or_404()
    title = (request.form.get("title") or "").strip()
    is_done = bool(request.form.get("is_done"))

    if not title:
        flash("Dê um nome para a coluna.", "danger")
        return redirect(url_for("tasks.index", projeto=column.project_id))
    if len(title) > 50:
        flash("O nome da coluna pode ter no máximo 50 caracteres.", "danger")
        return redirect(url_for("tasks.index", projeto=column.project_id))
    duplicate = BoardColumn.query.filter(
        BoardColumn.user_id == current_user.id,
        BoardColumn.project_id == column.project_id,
        BoardColumn.id != column.id,
        func.lower(BoardColumn.title) == title.lower(),
    ).first()
    if duplicate:
        flash("Já existe uma coluna com esse nome.", "warning")
        return redirect(url_for("tasks.index", projeto=column.project_id))
    if is_done and any(
        item.id != column.id and item.kind == "done"
        for item in project_columns(column.project)
    ):
        flash("Este projeto já tem uma coluna de conclusão.", "warning")
        return redirect(url_for("tasks.index", projeto=column.project_id))

    was_done = column.kind == "done"
    column.title = title
    if is_done:
        column.kind = "done"
        for task in column.tasks.all():
            if not task.is_done:
                task.move_to("done")
        ordered = [item for item in project_columns(column.project) if item.id != column.id]
        for position, item in enumerate(ordered):
            item.position = position
        column.position = len(ordered)
    elif was_done:
        column.kind = "todo"
        for task in column.tasks.all():
            if task.is_done:
                task.move_to("todo")
    else:
        column.kind = "todo"
    db.session.commit()
    flash("Coluna atualizada.", "success")
    return redirect(url_for("tasks.index", projeto=column.project_id))


@tasks_bp.post("/tarefas/colunas/<int:column_id>/mover")
@login_required
def move_column(column_id: int):
    column = BoardColumn.query.filter_by(
        id=column_id, user_id=current_user.id
    ).first_or_404()
    columns = project_columns(column.project)
    direction = (request.form.get("direction") or "").strip()
    ordered = [item for item in columns if item.id != column.id]
    index = next(
        (position for position, item in enumerate(columns) if item.id == column.id),
        0,
    )

    if direction == "up" and index > 0:
        ordered.insert(index - 1, column)
    elif direction == "down" and index < len(columns) - 1:
        ordered.insert(index + 1, column)
    else:
        return redirect(url_for("tasks.index", projeto=column.project_id))

    done_column = next((item for item in ordered if item.kind == "done"), None)
    if done_column is not None:
        ordered = [item for item in ordered if item.id != done_column.id] + [
            done_column
        ]
    for position, item in enumerate(ordered):
        item.position = position
    db.session.commit()
    flash("Ordem das colunas atualizada.", "success")
    return redirect(url_for("tasks.index", projeto=column.project_id))


@tasks_bp.post("/tarefas/colunas/<int:column_id>/excluir")
@login_required
def delete_column(column_id: int):
    column = BoardColumn.query.filter_by(
        id=column_id, user_id=current_user.id
    ).first_or_404()
    columns = project_columns(column.project)

    if len(columns) <= 1 and column.tasks.count() > 0:
        flash("Mova ou conclua as tarefas antes de remover a última coluna.", "warning")
        return redirect(url_for("tasks.index", projeto=column.project_id))

    if len(columns) <= 1:
        db.session.delete(column)
        db.session.commit()
        flash("Coluna removida. O projeto está em branco.", "info")
        return redirect(url_for("tasks.index", projeto=column.project_id))

    target = next(item for item in columns if item.id != column.id)

    for task in column.tasks.all():
        _set_task_column(task, target)
    # Persist the reassignment before removing the old column; otherwise the
    # ORM relationship can null the foreign keys during the delete flush.
    db.session.commit()

    db.session.delete(column)
    db.session.flush()
    remaining = (
        BoardColumn.query.filter_by(
            user_id=current_user.id, project_id=column.project_id
        )
        .order_by(BoardColumn.position.asc(), BoardColumn.id.asc())
        .all()
    )
    for position, item in enumerate(remaining):
        item.position = position
    db.session.commit()
    flash("Coluna removida. As tarefas foram movidas para outra coluna.", "info")
    return redirect(url_for("tasks.index", projeto=column.project_id))


@tasks_bp.post("/tarefas/<int:task_id>/ordenar")
@login_required
def reorder_task(task_id: int):
    """Move/reordena um card antes ou depois de outro na mesma coluna."""
    task = _get_task(task_id)
    if task.project is None:
        return jsonify(ok=False, error="Crie um projeto primeiro."), 400
    payload = request.get_json(silent=True) or request.form
    column = _column_by_id(payload.get("column_id"))
    if column is None or column.project_id != task.project_id:
        return jsonify(ok=False, error="Coluna inválida."), 400

    old_column_id = task.column_id
    _set_task_column(task, column)

    def _siblings(column_id):
        return (
            Task.query.filter(
                Task.user_id == current_user.id,
                Task.column_id == column_id,
                Task.archived_at.is_(None),
                Task.id != task.id,
            )
            .order_by(Task.position.asc(), Task.id.asc())
            .all()
        )

    siblings = _siblings(column.id)
    before_id = str(payload.get("before_id") or "")
    after_id = str(payload.get("after_id") or "")
    insert_at = len(siblings)
    if before_id.isdigit():
        found = next(
            (index for index, item in enumerate(siblings) if item.id == int(before_id)),
            None,
        )
        if found is not None:
            insert_at = found
    elif after_id.isdigit():
        found = next(
            (index for index, item in enumerate(siblings) if item.id == int(after_id)),
            None,
        )
        if found is not None:
            insert_at = found + 1

    ordered = siblings[:insert_at] + [task] + siblings[insert_at:]
    for position, item in enumerate(ordered):
        item.position = position

    if old_column_id and old_column_id != column.id:
        for position, item in enumerate(_siblings(old_column_id)):
            item.position = position

    db.session.commit()
    return jsonify(
        ok=True,
        task={
            "id": task.id,
            "column_id": task.column_id,
            "position": task.position,
            "is_done": task.is_done,
        },
        column_counts=_board_column_counts(
            project_columns(task.project),
            Task.query.filter_by(
                user_id=current_user.id, archived_at=None
            ).all(),
        ),
    )


@tasks_bp.post("/tarefas/<int:task_id>/coluna")
@login_required
def move_to_column(task_id: int):
    task = _get_task(task_id)
    if task.project is None:
        if request.is_json or request.headers.get("X-Requested-With"):
            return jsonify(ok=False, error="Crie um projeto primeiro."), 400
        flash("Crie um projeto primeiro.", "warning")
        return redirect(url_for("tasks.index"))
    columns = project_columns(task.project)
    if not columns:
        if request.is_json or request.headers.get("X-Requested-With"):
            return jsonify(ok=False, error="Crie uma coluna primeiro."), 400
        flash("Crie uma coluna primeiro.", "warning")
        return redirect(url_for("tasks.index", projeto=task.project_id))
    payload = request.get_json(silent=True) or request.form
    column = _column_by_id(payload.get("column_id"))

    if column is None:
        if request.is_json or request.headers.get("X-Requested-With"):
            return jsonify(ok=False, error="Coluna inválida."), 400
        flash("Coluna inválida.", "danger")
        return redirect(url_for("tasks.index"))

    _set_task_column(task, column)
    db.session.commit()

    if request.is_json or request.headers.get("X-Requested-With"):
        return jsonify(
            ok=True,
            task={
                "id": task.id,
                "status": task.status,
                "status_label": TASK_STATUS_LABELS[task.status],
                "column_id": task.column_id,
                "is_done": task.is_done,
                "is_archived": task.is_archived,
                "archived_at": task.archived_at.isoformat()
                if task.archived_at
                else None,
                "completed_at": task.completed_at.isoformat()
                if task.completed_at
                else None,
            },
            column_counts=_board_column_counts(
                columns,
                Task.query.filter_by(
                    user_id=current_user.id, archived_at=None
                ).all(),
            ),
        )

    return _redirect_back()


@tasks_bp.post("/tarefas/<int:task_id>/prioridade")
@login_required
def toggle_mit(task_id: int):
    """Liga/desliga a tarefa como uma das 3 prioridades do dia (MIT)."""
    task = _get_task(task_id)
    if task.is_mit:
        task.is_mit = False
        flash("Tarefa removida das prioridades do dia.", "info")
    elif _mit_count(exclude_id=task.id) >= 3:
        flash(
            "Você já tem 3 prioridades do dia. Remova uma antes de adicionar outra.",
            "warning",
        )
    else:
        task.is_mit = True
        flash("Tarefa marcada como prioridade do dia.", "success")
    db.session.commit()
    return _redirect_back()


@tasks_bp.post("/tarefas/<int:task_id>/planejar")
@login_required
def plan_today(task_id: int):
    """Adiciona/remove a tarefa do plano de hoje (time blocking leve)."""
    task = _get_task(task_id)
    today = local_today()
    if task.planned_for == today:
        task.planned_for = None
        flash("Tarefa removida do plano de hoje.", "info")
    else:
        task.planned_for = today
        flash("Tarefa adicionada ao plano de hoje.", "success")
    db.session.commit()
    return _redirect_back()


@tasks_bp.post("/tarefas/<int:task_id>/excluir")
@login_required
def delete(task_id: int):
    task = _get_task(task_id)
    # Mantém rascunhos como histórico, mas desvincula a tarefa removida.
    Scratchpad.query.filter_by(
        user_id=current_user.id, converted_task_id=task.id
    ).update({"converted_task_id": None}, synchronize_session=False)
    db.session.delete(task)
    db.session.commit()
    flash("Tarefa excluída.", "info")
    return redirect(url_for("tasks.index"))

@tasks_bp.get("/tarefas/arquivadas")
@login_required
def archived():
    """Consulta de tarefas concluídas que saíram do quadro semanal."""
    tasks = (
        Task.query.filter(
            Task.user_id == current_user.id, Task.archived_at.isnot(None)
        )
        .order_by(Task.archived_at.desc(), Task.completed_at.desc())
        .all()
    )
    groups = []
    for task in tasks:
        week = task.archived_week
        if not groups or groups[-1]["week"] != week:
            groups.append({"week": week, "tasks": []})
        groups[-1]["tasks"].append(task)
    return render_template(
        "tasks_archive.html",
        groups=groups,
        total=len(tasks),
    )


@tasks_bp.post("/tarefas/<int:task_id>/restaurar")
@login_required
def restore(task_id: int):
    task = _get_task(task_id)
    if not task.is_archived:
        flash("Esta tarefa não está arquivada.", "warning")
        return redirect(url_for("tasks.archived"))
    task.archived_at = None
    task.archived_week = None
    db.session.commit()
    flash("Tarefa restaurada para o quadro.", "success")
    return redirect(url_for("tasks.archived"))

