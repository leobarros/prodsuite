"""Aviso de revisão da semana anterior, compartilhado entre dispositivos."""

from __future__ import annotations

from datetime import timedelta

from models import WeeklyReview
from services.planning import week_start_for, weekly_metrics
from services.timeutils import local_today


def pending_week_review(user):
    """Retorna a semana anterior pendente de revisão, ou ``None``."""
    current_start = week_start_for(local_today())
    previous_start = current_start - timedelta(days=7)
    review = WeeklyReview.query.filter_by(
        user_id=user.id, week_start=previous_start
    ).first()
    if review is not None:
        return None

    metrics = weekly_metrics(user, previous_start)
    if not (
        metrics["sessions"]
        or metrics["completed_tasks"]
        or metrics["mit_total"]
    ):
        return None

    return {
        "week_start": previous_start,
        "week_end": metrics["week_end"],
        "sessions": metrics["sessions"],
        "completed_tasks": metrics["completed_tasks"],
    }
