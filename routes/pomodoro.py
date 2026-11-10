"""Módulo de Foco (Pomodoro): página, histórico e API de ciclos."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from extensions import db
from models import (
    POMODORO_DURATIONS,
    POMODORO_MODE_LABELS,
    PomodoroCycle,
    Task,
    utcnow,
)
from services.boards import first_task_in_focus_column
from services.pomodoro import (
    InvalidCycle,
    TaskNotFound,
    focus_stats,
    record_cycle,
    suggested_next_mode,
)
from services.timeutils import local_today
from services.timer_sync import apply_action, get_timer, serialize_timer

pomodoro_bp = Blueprint("pomodoro", __name__)


def _timer_payload(timer) -> dict | None:
    """Estado do timer + contador diário autoritativo do servidor."""
    state = serialize_timer(timer)
    if state is None:
        return None
    stats = focus_stats(current_user, days=1)
    state["focusCyclesToday"] = stats["focus_cycles_today"]
    state["focusDate"] = local_today().isoformat()
    return state


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
    tasks.sort(key=lambda task: (task.status != "doing", task.position, task.id))
    first_doing = first_task_in_focus_column(current_user)
    if first_doing is None:
        first_doing = (
            Task.query.filter(
                Task.user_id == uid,
                Task.status == "doing",
                Task.archived_at.is_(None),
            )
            .order_by(Task.position.asc(), Task.id.asc())
            .first()
        )
    stats = focus_stats(current_user, days=7)
    history = (
        PomodoroCycle.query.filter_by(user_id=uid)
        .order_by(PomodoroCycle.ended_at.desc())
        .limit(30)
        .all()
    )
    selected_task_id = request.args.get("tarefa", type=int)
    if selected_task_id is None and first_doing is not None:
        selected_task_id = first_doing.id

    # Uma seleção explícita na URL precisa valer também para o timer
    # compartilhado. Sem isso, a sincronização seguinte voltava para a
    # tarefa que estava salva no servidor.
    timer = get_timer(current_user)
    if selected_task_id is not None:
        selected_task = Task.query.filter_by(
            id=selected_task_id,
            user_id=uid,
            archived_at=None,
        ).first()
        if selected_task is None or selected_task.status == "done":
            selected_task_id = None
        elif timer is not None:
            if timer.running and timer.task_id:
                selected_task_id = timer.task_id
            elif timer.task_id != selected_task_id:
                timer.task_id = selected_task_id
                timer.revision = (timer.revision or 0) + 1
                timer.updated_at = utcnow()
                db.session.commit()
    elif timer is not None and timer.running and timer.task_id:
        selected_task_id = timer.task_id

    return render_template(
        "focus.html",
        tasks=tasks,
        stats=stats,
        history=history,
        durations=POMODORO_DURATIONS,
        mode_labels=POMODORO_MODE_LABELS,
        selected_task_id=selected_task_id,
    )


@pomodoro_bp.get("/foco/estado")
@login_required
def timer_state():
    timer = get_timer(current_user)
    return jsonify(ok=True, state=_timer_payload(timer))


@pomodoro_bp.post("/foco/estado")
@login_required
def update_timer_state():
    payload = request.get_json(silent=True) or request.form
    try:
        timer = apply_action(current_user, payload)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return jsonify(ok=True, state=_timer_payload(timer))


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
    run_id = payload.get("run_id") or None

    try:
        cycle = record_cycle(
            current_user,
            mode=mode,
            task_id=task_id,
            duration_minutes=duration,
            run_id=run_id,
        )
    except InvalidCycle as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except TaskNotFound as exc:
        return jsonify(ok=False, error=str(exc)), 404

    stats = focus_stats(current_user, days=7)
    chart_html = render_template("_weekly_chart.html", stats=stats)
    history = (
        PomodoroCycle.query.filter_by(user_id=current_user.id)
        .order_by(PomodoroCycle.ended_at.desc())
        .limit(30)
        .all()
    )
    history_html = render_template("_focus_history.html", history=history)
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
            chart_html=chart_html,
            history_html=history_html,
            suggested_next=suggested_next_mode(stats["focus_cycles_today"]),
        ),
        201,
    )
