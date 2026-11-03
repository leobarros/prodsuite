"""Estado compartilhado do Pomodoro entre dispositivos."""

from __future__ import annotations

import math
import uuid
from datetime import timedelta

from extensions import db
from models import POMODORO_DURATIONS, POMODORO_MODES, PomodoroTimer, Task, utcnow

MAX_TIMER_SECONDS = 6 * 60 * 60


def _normalize_timer(timer: PomodoroTimer | None) -> bool:
    """Corrige estados antigos que tenham duração acima da canônica."""
    if timer is None:
        return False
    canonical = POMODORO_DURATIONS.get(timer.mode, POMODORO_DURATIONS["focus"]) * 60
    now = utcnow()
    changed = False
    if timer.duration_seconds != canonical:
        timer.duration_seconds = canonical
        changed = True

    if timer.running and timer.ends_at:
        remaining = max(0, math.ceil((timer.ends_at - now).total_seconds()))
        if remaining > canonical:
            timer.ends_at = now + timedelta(seconds=canonical)
            timer.remaining_seconds = canonical
            changed = True
        elif timer.remaining_seconds > canonical:
            timer.remaining_seconds = canonical
            changed = True
    elif timer.remaining_seconds > canonical:
        timer.remaining_seconds = canonical
        changed = True

    if changed:
        timer.revision = (timer.revision or 0) + 1
        timer.updated_at = now
    return changed


def get_timer(user, create: bool = False) -> PomodoroTimer | None:
    timer = db.session.get(PomodoroTimer, user.id)
    if timer is None and create:
        timer = PomodoroTimer(
            user_id=user.id,
            mode="focus",
            duration_seconds=POMODORO_DURATIONS["focus"] * 60,
            remaining_seconds=POMODORO_DURATIONS["focus"] * 60,
            running=False,
        )
        db.session.add(timer)
        db.session.flush()
    elif _normalize_timer(timer):
        db.session.commit()
    return timer


def serialize_timer(timer: PomodoroTimer | None) -> dict | None:
    if timer is None:
        return None
    return {
        "mode": timer.mode,
        "duration": timer.duration_seconds,
        "remaining": timer.remaining_seconds,
        "endsAt": timer.ends_at.isoformat() + "Z" if timer.ends_at else None,
        "running": timer.running,
        "taskId": str(timer.task_id) if timer.task_id else None,
        "runId": timer.run_id,
        "revision": timer.revision,
        "updatedAt": timer.updated_at.isoformat() + "Z" if timer.updated_at else None,
    }


def _mode_duration(mode: str | None, fallback: int) -> tuple[str, int]:
    if mode not in POMODORO_MODES:
        mode = "focus"
    return mode, max(1, min(int(fallback or 60), MAX_TIMER_SECONDS))


def _task_for(user, raw_task_id) -> int | None:
    if raw_task_id in (None, "", 0, "0"):
        return None
    try:
        task_id = int(raw_task_id)
    except (TypeError, ValueError):
        return None
    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    return task.id if task else None


def apply_action(user, payload: dict) -> PomodoroTimer:
    action = (payload.get("action") or "").strip()
    timer = get_timer(user, create=True)
    now = utcnow()

    if action == "start":
        mode = payload.get("mode") or timer.mode
        if mode not in POMODORO_MODES:
            mode = "focus"
        default_seconds = POMODORO_DURATIONS[mode] * 60
        # A duração é canônica por modo; nunca aceite uma sobra de outro modo.
        duration = default_seconds
        try:
            remaining = int(payload.get("remaining") or duration)
        except (TypeError, ValueError):
            remaining = duration
        remaining = max(1, min(remaining, duration))
        timer.mode = mode
        timer.duration_seconds = duration
        timer.remaining_seconds = remaining
        timer.ends_at = now + timedelta(seconds=remaining)
        timer.running = True
        timer.run_id = uuid.uuid4().hex
        timer.task_id = _task_for(user, payload.get("task_id"))
    elif action == "pause":
        try:
            supplied_remaining = int(payload.get("remaining"))
        except (TypeError, ValueError):
            supplied_remaining = None
        if supplied_remaining is not None:
            timer.remaining_seconds = max(
                0, min(supplied_remaining, timer.duration_seconds)
            )
        elif timer.running and timer.ends_at:
            timer.remaining_seconds = max(
                0, math.ceil((timer.ends_at - now).total_seconds())
            )
        timer.running = False
        timer.ends_at = None
    elif action == "resume":
        if timer.remaining_seconds <= 0:
            timer.remaining_seconds = timer.duration_seconds
        timer.ends_at = now + timedelta(seconds=timer.remaining_seconds)
        timer.running = True
        timer.run_id = timer.run_id or uuid.uuid4().hex
    elif action == "reset":
        mode = payload.get("mode") or timer.mode
        default_seconds = (
            POMODORO_DURATIONS.get(mode, POMODORO_DURATIONS["focus"]) * 60
        )
        mode, duration = _mode_duration(mode, default_seconds)
        timer.mode = mode
        timer.duration_seconds = duration
        timer.remaining_seconds = duration
        timer.running = False
        timer.ends_at = None
        timer.run_id = None
    elif action == "mode":
        mode = payload.get("mode") or timer.mode
        default_seconds = (
            POMODORO_DURATIONS.get(mode, POMODORO_DURATIONS["focus"]) * 60
        )
        mode, duration = _mode_duration(mode, default_seconds)
        timer.mode = mode
        timer.duration_seconds = duration
        timer.remaining_seconds = duration
        timer.running = False
        timer.ends_at = None
        timer.run_id = None
    elif action == "task":
        timer.task_id = _task_for(user, payload.get("task_id"))
    elif action == "complete":
        timer.running = False
        timer.remaining_seconds = 0
        timer.ends_at = None
    else:
        raise ValueError("Ação de timer inválida.")

    timer.revision = (timer.revision or 0) + 1
    timer.updated_at = now
    db.session.commit()
    return timer
