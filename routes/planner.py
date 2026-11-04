"""Planejamento do dia: MITs, regra 1-3-5, matriz de Eisenhower e meta."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from forms import WeeklyGoalForm
from models import (
    TASK_QUADRANTS,
    TASK_QUADRANT_HINTS,
    TASK_QUADRANT_LABELS,
    PomodoroCycle,
    Task,
    WeeklyReview,
)
from services.planning import week_start_for, weekly_metrics
from services.timeutils import day_start_utc, local_today

planner_bp = Blueprint("planner", __name__)


def _open_tasks() -> list[Task]:
    tasks = (
        Task.query.filter(
            Task.user_id == current_user.id, Task.status != "done"
        )
        .order_by(Task.updated_at.desc())
        .all()
    )
    return sorted(
        tasks,
        key=lambda task: (
            not task.is_mit,
            task.quadrant_rank,
            task.due_date or local_today(),
            -task.id,
        ),
    )


@planner_bp.get("/planejar")
@login_required
def plan():
    today = local_today()
    open_tasks = _open_tasks()
    metrics = weekly_metrics(current_user, today)
    review = WeeklyReview.query.filter_by(
        user_id=current_user.id, week_start=metrics["week_start"]
    ).first()

    mit_tasks = [task for task in open_tasks if task.is_mit][:3]
    planned = [task for task in open_tasks if task.planned_for == today]
    due_today = [
        task
        for task in open_tasks
        if task.due_date == today and task.planned_for != today
    ]
    daily_tasks = [task for task in open_tasks if task.repeat_daily]
    day_tasks = []
    seen_day_tasks = set()
    for task in planned + due_today + daily_tasks:
        if task.id not in seen_day_tasks:
            seen_day_tasks.add(task.id)
            day_tasks.append(task)
    day_tasks.sort(key=lambda task: (not task.is_mit, task.quadrant_rank, task.id))

    daily_progress = {}
    if daily_tasks:
        progress_rows = (
            db.session.query(PomodoroCycle.task_id, func.count(PomodoroCycle.id))
            .filter(
                PomodoroCycle.user_id == current_user.id,
                PomodoroCycle.mode == "focus",
                PomodoroCycle.completed.is_(True),
                PomodoroCycle.task_id.in_([task.id for task in daily_tasks]),
                PomodoroCycle.ended_at >= day_start_utc(today),
            )
            .group_by(PomodoroCycle.task_id)
            .all()
        )
        daily_progress = {task_id: count for task_id, count in progress_rows}

    large = [task for task in day_tasks if (task.estimate_pomodoros or 0) >= 3]
    medium = [task for task in day_tasks if (task.estimate_pomodoros or 0) == 2]
    small = [task for task in day_tasks if (task.estimate_pomodoros or 0) <= 1]

    matrix = {
        quadrant: [task for task in open_tasks if task.quadrant == quadrant][:4]
        for quadrant in TASK_QUADRANTS
    }
    unclassified = [
        task for task in open_tasks if task.quadrant not in TASK_QUADRANTS
    ][:5]
    # A lista é um atalho para todas as tarefas curtas abertas. O template
    # indica quando uma delas já está no plano/prioridade; não some daqui.
    quick_wins = [
        task for task in open_tasks if task.is_quick_win and not task.repeat_daily
    ][:5]

    goal_form = WeeklyGoalForm(
        weekly_focus_goal=current_user.weekly_focus_goal or 12
    )

    return render_template(
        "planner.html",
        today=today,
        mit_tasks=mit_tasks,
        day_tasks=day_tasks,
        planned=planned,
        due_today=due_today,
        daily_tasks=daily_tasks,
        daily_progress=daily_progress,
        rule_counts={
            "large": len(large),
            "medium": len(medium),
            "small": len(small),
            "target_large": 1,
            "target_medium": 3,
            "target_small": 5,
        },
        matrix=matrix,
        matrix_labels=TASK_QUADRANT_LABELS,
        matrix_hints=TASK_QUADRANT_HINTS,
        unclassified=unclassified,
        quick_wins=quick_wins,
        metrics=metrics,
        review=review,
        goal_form=goal_form,
    )


@planner_bp.post("/planejar/meta")
@login_required
def update_goal():
    form = WeeklyGoalForm()
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
        return redirect(url_for("planner.plan"))

    current_user.weekly_focus_goal = form.weekly_focus_goal.data
    db.session.commit()
    flash("Meta semanal atualizada.", "success")
    return redirect(url_for("planner.plan"))
