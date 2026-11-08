"""Caixa de entrada: captura rápida, triagem e conversão em tarefa/nota."""

from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from forms import ScratchpadForm, TaskForm
from models import Note, Scratchpad, Task, utcnow
from services.boards import ensure_default_project, project_columns
from services.categories import category_choices, ensure_categories
from services.task_creation import create_task_from_form
from services.timeutils import local_today, to_local

scratchpad_bp = Blueprint("scratchpad", __name__)

VIEW_ALIASES = {
    "abertas": "decidir",
    "decidir": "decidir",
    "talvez": "talvez",
    "concluidas": "resolvidas",
    "resolvidas": "resolvidas",
    "todas": "todas",
}


def _wants_json() -> bool:
    return bool(
        request.is_json
        or request.headers.get("X-Requested-With")
        in {"fetch", "XMLHttpRequest"}
        or request.accept_mimetypes.best == "application/json"
    )


def _is_focus_next() -> bool:
    return (
        request.form.get("next") == "foco"
        or request.args.get("next") == "foco"
    )


def _back_to_flow(default_view: str = "decidir"):
    if _is_focus_next():
        return redirect(url_for("scratchpad.focus"))
    return redirect(url_for("scratchpad.index", ver=default_view))


def _get_item(item_id: int) -> Scratchpad:
    return Scratchpad.query.filter_by(
        id=item_id, user_id=current_user.id
    ).first_or_404()


def _base_query():
    return Scratchpad.query.filter(
        Scratchpad.user_id == current_user.id,
        Scratchpad.converted_task_id.is_(None),
    )


def _active_query():
    return _base_query().filter(
        Scratchpad.completed_at.is_(None),
        Scratchpad.someday_at.is_(None),
    )


def _counts() -> dict[str, int]:
    base = _base_query()
    return {
        "open": base.filter(
            Scratchpad.completed_at.is_(None),
            Scratchpad.someday_at.is_(None),
        ).count(),
        "someday": base.filter(
            Scratchpad.completed_at.is_(None),
            Scratchpad.someday_at.isnot(None),
        ).count(),
        "done": base.filter(Scratchpad.completed_at.isnot(None)).count(),
    }


def _task_form_context(item: Scratchpad, form: TaskForm | None = None) -> dict:
    categories = ensure_categories(current_user)
    task_form = form or TaskForm()
    task_form.category.choices = category_choices(categories)
    valid_categories = {category.key for category in categories}
    if not task_form.category.data or task_form.category.data not in valid_categories:
        task_form.category.data = categories[0].key
    project = ensure_default_project(current_user)
    columns = project_columns(project) if project else []
    selected_column_id = (
        int(request.form.get("column_id"))
        if request.form.get("column_id", "").isdigit()
        else (columns[0].id if columns else None)
    )
    if form is None:
        task_form.title.data = (item.content.split("\n")[0] or "")[:160]
        task_form.description.data = item.content
        task_form.estimate_pomodoros.data = 1
        task_form.due_date.data = local_today()
    return {
        "task_form": task_form,
        "categories": categories,
        "project": project,
        "board_columns": columns,
        "selected_column_id": selected_column_id,
    }


def _render_detail(
    item: Scratchpad,
    *,
    edit_form: ScratchpadForm | None = None,
    task_form: TaskForm | None = None,
    open_modal: bool = False,
    status: int = 200,
):
    edit_form = edit_form or ScratchpadForm(obj=item)
    context = _task_form_context(item, task_form)
    return (
        render_template(
            "scratchpad_detail.html",
            item=item,
            form=edit_form,
            open_modal=open_modal,
            **context,
        ),
        status,
    )


def _unique_note_title(content: str) -> str:
    title = next((line.strip() for line in content.splitlines() if line.strip()), "Captura")
    title = title[:160]
    existing = {
        row.title.strip().lower()
        for row in Note.query.filter_by(user_id=current_user.id).all()
    }
    if title.lower() not in existing:
        return title
    stem = title[:150]
    index = 2
    while True:
        suffix = f" ({index})"
        candidate = f"{stem[:160 - len(suffix)]}{suffix}"
        if candidate.lower() not in existing:
            return candidate
        index += 1


def _create_quick_task(item: Scratchpad) -> Task | None:
    project = ensure_default_project(current_user)
    columns = project_columns(project) if project else []
    if project is None or not columns:
        flash(
            "Crie um projeto e uma coluna em Tarefas para transformar esta captura.",
            "warning",
        )
        return None
    selected = next((column for column in columns if column.kind != "done"), columns[0])
    max_position = (
        db.session.query(func.max(Task.position))
        .filter(
            Task.user_id == current_user.id,
            Task.column_id == selected.id,
            Task.archived_at.is_(None),
        )
        .scalar()
        or 0
    )
    categories = ensure_categories(current_user)
    task = Task(
        user_id=current_user.id,
        title=(item.content.split("\n")[0] or "Captura")[:160],
        description=item.content,
        status="done" if selected.kind == "done" else "todo",
        column_id=selected.id,
        column_entered_at=utcnow(),
        position=max_position + 1,
        project_id=project.id,
        priority="medium",
        estimate_pomodoros=1,
        due_date=local_today(),
        planned_for=local_today(),
        category=categories[0].key,
        tags="",
    )
    if task.status == "done":
        task.completed_at = utcnow()
    db.session.add(task)
    db.session.flush()
    return task


@scratchpad_bp.route("/rascunhos", methods=["GET", "POST"])
@login_required
def legacy_index():
    target = url_for("scratchpad.index", **request.args)
    return redirect(target, code=308 if request.method == "POST" else 302)


@scratchpad_bp.route("/rascunhos/<path:rest>", methods=["GET", "POST"])
@login_required
def legacy_path(rest: str):
    query = request.query_string.decode("utf-8", "ignore")
    target = f"/entrada/{rest}"
    if query:
        target = f"{target}?{query}"
    return redirect(target, code=308 if request.method == "POST" else 302)


@scratchpad_bp.route("/anotacoes", methods=["GET", "POST"])
@login_required
def legacy_annotations():
    if request.method == "POST":
        return index()
    return redirect(url_for("scratchpad.index"), code=302)


@scratchpad_bp.route("/anotacoes/<path:rest>", methods=["GET", "POST"])
@login_required
def legacy_annotation_path(rest: str):
    query = request.query_string.decode("utf-8", "ignore")
    target = f"/entrada/{rest}"
    if query:
        target = f"{target}?{query}"
    return redirect(target, code=307 if request.method == "POST" else 302)


@scratchpad_bp.route("/entrada", methods=["GET", "POST"])
@login_required
def index():
    form = ScratchpadForm()

    if form.validate_on_submit():
        item = Scratchpad(user_id=current_user.id, content=form.content.data)
        db.session.add(item)
        db.session.commit()
        if _wants_json():
            created = to_local(item.created_at)
            return (
                jsonify(
                    ok=True,
                    scratchpad={
                        "id": item.id,
                        "content": item.content,
                        "preview": item.preview,
                        "created_at": created.strftime("%d/%m %H:%M")
                        if created
                        else "",
                    },
                ),
                201,
            )
        flash("Capturado na caixa de entrada.", "success")
        return redirect(url_for("scratchpad.index"))

    if request.method == "POST" and _wants_json():
        return jsonify(ok=False, errors=form.errors), 400

    raw_view = (request.args.get("ver") or "decidir").strip().lower()
    view = VIEW_ALIASES.get(raw_view, "decidir")
    base = _base_query()
    if view == "talvez":
        items = (
            base.filter(
                Scratchpad.completed_at.is_(None),
                Scratchpad.someday_at.isnot(None),
            )
            .order_by(Scratchpad.someday_at.desc())
            .limit(100)
            .all()
        )
    elif view == "resolvidas":
        items = (
            base.filter(Scratchpad.completed_at.isnot(None))
            .order_by(Scratchpad.completed_at.desc())
            .limit(100)
            .all()
        )
    elif view == "todas":
        items = base.order_by(Scratchpad.created_at.desc()).limit(100).all()
    else:
        items = (
            base.filter(
                Scratchpad.completed_at.is_(None),
                Scratchpad.someday_at.is_(None),
            )
            .order_by(Scratchpad.created_at.asc())
            .limit(100)
            .all()
        )
    return render_template(
        "scratchpad.html",
        form=form,
        items=items,
        view=view,
        counts=_counts(),
    )


@scratchpad_bp.get("/entrada/foco")
@login_required
def focus():
    item = _active_query().order_by(Scratchpad.created_at.asc()).first()
    next_items = []
    if item is not None:
        next_items = (
            _active_query()
            .filter(Scratchpad.id != item.id)
            .order_by(Scratchpad.created_at.asc())
            .limit(4)
            .all()
        )
    return render_template(
        "scratchpad_focus.html",
        item=item,
        next_items=next_items,
        counts=_counts(),
    )


@scratchpad_bp.get("/entrada/<int:item_id>")
@login_required
def detail(item_id: int):
    return _render_detail(_get_item(item_id))


@scratchpad_bp.post("/entrada/<int:item_id>/editar")
@login_required
def edit(item_id: int):
    item = _get_item(item_id)
    if item.is_completed:
        flash("Item resolvido é somente para consulta. Reabra para editar.", "warning")
        return redirect(url_for("scratchpad.detail", item_id=item.id))
    form = ScratchpadForm(obj=item)
    if form.validate_on_submit():
        item.content = form.content.data
        db.session.commit()
        flash("Captura atualizada.", "success")
        return _back_to_flow()
    flash("Revise a captura antes de salvar.", "danger")
    return _render_detail(item, edit_form=form, status=400)


@scratchpad_bp.post("/entrada/<int:item_id>/converter")
@login_required
def convert(item_id: int):
    item = _get_item(item_id)
    if item.is_converted:
        flash("Esta captura já virou tarefa.", "warning")
        return redirect(url_for("scratchpad.detail", item_id=item.id))
    if item.is_completed:
        flash("Item resolvido é somente para consulta. Reabra para transformar em tarefa.", "warning")
        return redirect(url_for("scratchpad.detail", item_id=item.id))

    task_form = TaskForm()
    context = _task_form_context(item, task_form)
    if not task_form.description.data:
        task_form.description.data = item.content
    if not task_form.validate_on_submit():
        flash("Revise os campos da tarefa.", "danger")
        return _render_detail(
            item, task_form=task_form, open_modal=True, status=400
        )

    task = create_task_from_form(
        current_user,
        task_form,
        context["project"],
        context["board_columns"],
        context["categories"],
        request.form.get("column_id"),
    )
    if task is None:
        return redirect(url_for("scratchpad.detail", item_id=item.id))

    db.session.delete(item)
    db.session.commit()
    flash("Captura virou tarefa.", "success")
    return redirect(url_for("tasks.edit", task_id=task.id))


@scratchpad_bp.post("/entrada/<int:item_id>/agora")
@login_required
def quick_task(item_id: int):
    item = _get_item(item_id)
    if item.is_completed:
        flash("Reabra o item para transformar em tarefa.", "warning")
        return _back_to_flow()
    task = _create_quick_task(item)
    if task is None:
        return _back_to_flow()
    db.session.delete(item)
    db.session.commit()
    flash("Captura movida para Tarefas, com prazo para hoje.", "success")
    if _is_focus_next():
        return redirect(url_for("scratchpad.focus"))
    return redirect(url_for("tasks.edit", task_id=task.id))


@scratchpad_bp.post("/entrada/<int:item_id>/nota")
@login_required
def convert_note(item_id: int):
    item = _get_item(item_id)
    if item.is_completed:
        flash("Reabra o item para guardar como nota.", "warning")
        return _back_to_flow()
    note = Note(
        user_id=current_user.id,
        title=_unique_note_title(item.content),
        body=item.content,
        tags="",
    )
    db.session.add(note)
    db.session.delete(item)
    db.session.commit()
    flash("Captura guardada em Notas. Você pode completar o texto por lá.", "success")
    if _is_focus_next():
        return redirect(url_for("scratchpad.focus"))
    return redirect(url_for("notes.view", note_id=note.id))


@scratchpad_bp.post("/entrada/<int:item_id>/talvez")
@login_required
def someday(item_id: int):
    item = _get_item(item_id)
    if item.is_completed:
        flash("Reabra o item antes de mandá-lo para Talvez.", "warning")
        return _back_to_flow()
    source_view = request.form.get("view", "").strip().lower()
    source_view = VIEW_ALIASES.get(source_view, "decidir")
    if item.someday_at is not None:
        item.someday_at = None
        flash("Item de volta para a fila.", "info")
        db.session.commit()
        return _back_to_flow(source_view)
    item.someday_at = utcnow()
    flash("Item guardado em Talvez, sem virar tarefa.", "success")
    db.session.commit()
    return _back_to_flow(source_view)


@scratchpad_bp.post("/entrada/<int:item_id>/concluir")
@login_required
def complete(item_id: int):
    item = _get_item(item_id)
    if item.is_completed:
        item.completed_at = None
        item.someday_at = None
        flash("Item reaberto na caixa de entrada.", "info")
    else:
        item.completed_at = utcnow()
        item.someday_at = None
        flash("Item resolvido.", "success")
    db.session.commit()
    return _back_to_flow()


@scratchpad_bp.post("/entrada/<int:item_id>/excluir")
@login_required
def delete(item_id: int):
    item = _get_item(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Item solto. Não virou tarefa nem nota.", "info")
    return _back_to_flow()
