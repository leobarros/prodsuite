"""Criação de tarefas a partir do mesmo formulário em qualquer fluxo."""

from __future__ import annotations

from flask import flash

from sqlalchemy import func

from extensions import db
from models import Task, normalize_tags, utcnow
from services.timeutils import local_today


def create_task_from_form(
    user, form, project, columns, categories, requested_column_id=None
) -> Task | None:
    """Valida a coluna/MIT e cria a tarefa sem fazer commit.

    O chamador decide quando confirmar a transação (inclusive ao converter
    um rascunho, que também precisa ser atualizado).
    """
    if project is None or not columns:
        flash("Crie um projeto e uma coluna antes de adicionar tarefas.", "warning")
        return None

    wants_mit = bool(form.is_mit.data)
    mit_count = Task.query.filter(
        Task.user_id == user.id,
        Task.is_mit.is_(True),
        Task.status != "done",
    ).count()
    if wants_mit and mit_count >= 3:
        flash(
            "Você já tem 3 prioridades do dia. Remova uma antes de adicionar outra.",
            "warning",
        )
        wants_mit = False

    selected = None
    try:
        requested_id = int(requested_column_id)
    except (TypeError, ValueError):
        requested_id = None
    if requested_id is not None:
        selected = next(
            (column for column in columns if column.id == requested_id), None
        )
    if selected is None:
        selected = columns[0]

    max_position = (
        db.session.query(func.max(Task.position))
        .filter(
            Task.user_id == user.id,
            Task.column_id == selected.id,
            Task.archived_at.is_(None),
        )
        .scalar()
        or 0
    )
    task = Task(
        user_id=user.id,
        title=form.title.data,
        description=form.description.data or "",
        status="done" if selected.kind == "done" else "todo",
        column_id=selected.id,
        column_entered_at=utcnow(),
        position=max_position + 1,
        project_id=project.id,
        estimate_pomodoros=form.estimate_pomodoros.data or 0,
        due_date=form.due_date.data or local_today(),
        category=form.category.data or categories[0].key,
        quadrant=form.quadrant.data or None,
        is_mit=wants_mit,
        tags=normalize_tags(form.tags.data),
    )
    if task.status == "done":
        task.completed_at = utcnow()
    db.session.add(task)
    db.session.flush()
    return task
