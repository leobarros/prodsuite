"""Métricas do método: semana, metas e distribuição por categoria."""

from __future__ import annotations

from datetime import date, timedelta

from models import PomodoroCycle, Task
from services.categories import ensure_categories
from services.timeutils import day_start_utc, local_today


def week_start_for(day: date | None = None) -> date:
    """Segunda-feira da semana de ``day``."""
    current = day or local_today()
    return current - timedelta(days=current.weekday())


def weekly_metrics(user, day: date | None = None) -> dict:
    start_day = week_start_for(day)
    end_day = start_day + timedelta(days=7)
    start_utc = day_start_utc(start_day)
    end_utc = day_start_utc(end_day)

    cycles = (
        PomodoroCycle.query.filter(
            PomodoroCycle.user_id == user.id,
            PomodoroCycle.mode == "focus",
            PomodoroCycle.ended_at >= start_utc,
            PomodoroCycle.ended_at < end_utc,
        )
        .order_by(PomodoroCycle.ended_at.asc())
        .all()
    )
    completed_tasks = (
        Task.query.filter(
            Task.user_id == user.id,
            Task.status == "done",
            Task.completed_at >= start_utc,
            Task.completed_at < end_utc,
        )
        .order_by(Task.completed_at.asc())
        .all()
    )

    categories = ensure_categories(user)
    category_minutes = {category.key: 0 for category in categories}
    category_tasks = {category.key: 0 for category in categories}
    fallback_category = categories[0].key
    for cycle in cycles:
        category = cycle.task.category if cycle.task else fallback_category
        if category not in category_minutes:
            category = fallback_category
        category_minutes[category] += cycle.duration_minutes or 0
    for task in completed_tasks:
        category = (
            task.category if task.category in category_tasks else fallback_category
        )
        category_tasks[category] += 1

    mit_tasks = (
        Task.query.filter(Task.user_id == user.id, Task.is_mit.is_(True)).all()
    )
    mit_done = sum(1 for task in mit_tasks if task.is_done)

    goal = max(1, int(user.weekly_focus_goal or 12))
    focus_minutes = sum(cycle.duration_minutes or 0 for cycle in cycles)
    goal_percent = min(100, round(len(cycles) / goal * 100))

    return {
        "week_start": start_day,
        "week_end": end_day - timedelta(days=1),
        "sessions": len(cycles),
        "minutes": focus_minutes,
        "completed_tasks": len(completed_tasks),
        "completed_list": completed_tasks,
        "goal": goal,
        "goal_percent": goal_percent,
        "goal_remaining": max(0, goal - len(cycles)),
        "mit_total": len(mit_tasks),
        "mit_done": mit_done,
        "categories": [
            {
                "key": category.key,
                "label": category.name,
                "icon": category.icon,
                "minutes": category_minutes[category.key],
                "tasks": category_tasks[category.key],
            }
            for category in categories
        ],
        "category_max_minutes": max(category_minutes.values(), default=0) or 1,
    }
