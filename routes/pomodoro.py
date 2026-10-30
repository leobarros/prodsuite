"""Módulo de Foco (Pomodoro): página, histórico e API de ciclos."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from models import (
    POMODORO_DURATIONS,
    POMODORO_MODE_LABELS,
    PomodoroCycle,
    Task,
)
from services.pomodoro import (
    InvalidCycle,
    TaskNotFound,
    focus_stats,
    record_cycle,
    suggested_next_mode,
)

pomodoro_bp = Blueprint("pomodoro", __name__)


@pomodoro_bp.get("/foco")
@login_required
def focus():
    uid = current_user.id
    tasks = (
        Task.query.filter(Task.user_id == uid, Task.status != "done")
        .order_by(Task.updated_at.desc())
        .limit(50)
        .all()
    )
    stats = focus_stats(current_user, days=7)
    history = (
        PomodoroCycle.query.filter_by(user_id=uid)
        .order_by(PomodoroCycle.ended_at.desc())
        .limit(30)
        .all()
    )
    selected_task_id = request.args.get("tarefa", type=int)

    return render_template(
        "focus.html",
        tasks=tasks,
        stats=stats,
        history=history,
        durations=POMODORO_DURATIONS,
        mode_labels=POMODORO_MODE_LABELS,
        selected_task_id=selected_task_id,
    )


@pomodoro_bp.post("/foco/ciclos")
@login_required
def create_cycle():
    """Registra um ciclo concluído. O cliente informa, o servidor valida."""
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form

    mode = (payload.get("mode") or "focus").strip()
    task_id = payload.get("task_id") or None
    duration = payload.get("duration_minutes")

    try:
        cycle = record_cycle(
            current_user,
            mode=mode,
            task_id=task_id,
            duration_minutes=duration,
        )
    except InvalidCycle as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except TaskNotFound as exc:
        return jsonify(ok=False, error=str(exc)), 404

    stats = focus_stats(current_user, days=7)
    return (
        jsonify(
            ok=True,
            cycle={
                "id": cycle.id,
                "mode": cycle.mode,
                "mode_label": cycle.mode_label,
                "duration_minutes": cycle.duration_minutes,
                "task_id": cycle.task_id,
                "ended_at": cycle.ended_at.isoformat(),
            },
            stats=stats,
            suggested_next=suggested_next_mode(stats["focus_cycles_today"]),
        ),
        201,
    )
