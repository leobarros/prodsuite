"""Arquivamento de tarefas concluídas ao fechar o ciclo semanal."""

from __future__ import annotations

from datetime import timedelta

from extensions import db
from models import Task, utcnow
from services.timeutils import day_start_utc


def archive_week(user, week_start) -> int:
    """Arquiva apenas concluídas da semana informada, uma única vez."""
    end_day = week_start + timedelta(days=7)
    start_utc = day_start_utc(week_start)
    end_utc = day_start_utc(end_day)
    tasks = (
        Task.query.filter(
            Task.user_id == user.id,
            Task.status == "done",
            Task.archived_at.is_(None),
            Task.completed_at >= start_utc,
            Task.completed_at < end_utc,
        )
        .all()
    )
    now = utcnow()
    for task in tasks:
        task.archived_at = now
        task.archived_week = week_start
    if tasks:
        db.session.commit()
    return len(tasks)


def count_unarchived_week(user, week_start) -> int:
    end_day = week_start + timedelta(days=7)
    return (
        Task.query.filter(
            Task.user_id == user.id,
            Task.status == "done",
            Task.archived_at.is_(None),
            Task.completed_at >= day_start_utc(week_start),
            Task.completed_at < day_start_utc(end_day),
        ).count()
    )
