"""Projetos e suas colunas personalizadas (inclui migração de dados antigos)."""

from __future__ import annotations

from extensions import db
from models import BoardColumn, Project, Task

LEGACY_PROJECT_NAME = "Meu quadro"
# Usado apenas para recuperar dados antigos que ainda não têm projeto.
LEGACY_COLUMNS = (
    ("A fazer", "todo"),
    ("Em andamento", "doing"),
    ("Concluídas", "done"),
)


def ensure_default_project(user) -> Project:
    """Garante um quadro padrão e reencaixa colunas/tarefas antigas."""
    projects = (
        Project.query.filter_by(user_id=user.id)
        .order_by(Project.position.asc(), Project.id.asc())
        .all()
    )
    changed = False

    if not projects:
        existing_columns = BoardColumn.query.filter_by(user_id=user.id).all()
        existing_tasks = Task.query.filter_by(user_id=user.id).all()
        # Contas novas não recebem quadro nem colunas prontas. Só criamos um
        # projeto de recuperação quando existem dados antigos sem projeto.
        if not existing_columns and not existing_tasks:
            return None

        project = Project(
            user_id=user.id, name=LEGACY_PROJECT_NAME, position=0
        )
        db.session.add(project)
        db.session.flush()
        projects = [project]
        changed = True

        if not existing_columns:
            for position, (title, kind) in enumerate(LEGACY_COLUMNS):
                db.session.add(
                    BoardColumn(
                        user_id=user.id,
                        project_id=project.id,
                        title=title,
                        kind=kind,
                        position=position,
                    )
                )
            changed = True

    default_project = projects[0]
    columns = (
        BoardColumn.query.filter_by(user_id=user.id)
        .order_by(BoardColumn.position.asc(), BoardColumn.id.asc())
        .all()
    )
    for column in columns:
        if column.project_id is None:
            column.project_id = default_project.id
            changed = True
    columns = (
        BoardColumn.query.filter_by(user_id=user.id)
        .order_by(BoardColumn.position.asc(), BoardColumn.id.asc())
        .all()
    )

    columns_by_project: dict[int, list[BoardColumn]] = {}
    for column in columns:
        columns_by_project.setdefault(column.project_id, []).append(column)
    columns_by_id = {column.id: column for column in columns}

    user_has_tasks = Task.query.filter_by(user_id=user.id).count() > 0
    if (
        len(projects) == 1
        and projects[0].name == LEGACY_PROJECT_NAME
        and not user_has_tasks
    ):
        project_columns_now = columns_by_project.get(projects[0].id, [])
        if [(column.title, column.kind) for column in project_columns_now] == [
            (title, kind) for title, kind in LEGACY_COLUMNS
        ]:
            # Contas antigas que nunca usaram o quadro recebem o novo estado
            # em branco, sem apagar nenhuma tarefa.
            for column in project_columns_now:
                db.session.delete(column)
            changed = True
            columns = []
            columns_by_id = {}
            columns_by_project = {}

    for task in Task.query.filter_by(user_id=user.id).all():
        column = columns_by_id.get(task.column_id)
        if column is not None:
            if task.project_id != column.project_id:
                task.project_id = column.project_id
                changed = True
            continue

        project_id = task.project_id or default_project.id
        project_columns = columns_by_project.get(project_id) or []
        if not project_columns:
            continue
        target = next(
            (item for item in project_columns if item.kind == task.status),
            project_columns[0],
        )
        task.project_id = project_id
        task.column_id = target.id
        if task.status != target.kind:
            task.move_to(target.kind)
        changed = True

    if changed:
        db.session.commit()
    return default_project


def project_by_id(user, project_id) -> Project | None:
    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return None
    return Project.query.filter_by(id=project_id, user_id=user.id).first()


def active_project(user, project_id=None, session=None) -> Project | None:
    """Resolve o projeto pedido, a sessão ou o primeiro projeto."""
    requested = project_by_id(user, project_id)
    if requested is not None:
        if session is not None:
            session["active_project_id"] = requested.id
        return requested

    if session is not None:
        saved = project_by_id(user, session.get("active_project_id"))
        if saved is not None:
            return saved

    project = ensure_default_project(user)
    if project is None:
        if session is not None:
            session.pop("active_project_id", None)
        return None
    if session is not None:
        session["active_project_id"] = project.id
    return project


def project_columns(project) -> list[BoardColumn]:
    return (
        BoardColumn.query.filter_by(project_id=project.id)
        .order_by(BoardColumn.position.asc(), BoardColumn.id.asc())
        .all()
    )


def first_task_in_focus_column(user):
    """Primeiro card da coluna de andamento (Doing), pela ordem manual."""
    columns = (
        BoardColumn.query.join(Project, BoardColumn.project_id == Project.id)
        .filter(BoardColumn.user_id == user.id)
        .order_by(Project.position.asc(), BoardColumn.position.asc())
        .all()
    )
    focus_titles = {"doing", "em andamento", "em progresso", "fazendo"}
    focus_column = next(
        (
            column
            for column in columns
            if column.kind == "doing"
            or column.title.strip().casefold() in focus_titles
        ),
        None,
    )
    if focus_column is None:
        return None
    return (
        Task.query.filter(
            Task.user_id == user.id,
            Task.column_id == focus_column.id,
            Task.archived_at.is_(None),
        )
        .order_by(Task.position.asc(), Task.id.asc())
        .first()
    )
