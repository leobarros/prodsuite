"""Regras de negócio de Pomodoro.

O cliente mantém o relógio (para não perder tempo com o navegador em segundo
plano), mas **a verdade sobre um ciclo é registrada no servidor**: modo
válido, duração dentro do permitido, tarefa pertencente ao usuário e
``completed=True``. O cliente nunca decide que um ciclo "conta".
"""

from __future__ import annotations

from datetime import timedelta

from extensions import db
from models import (
    POMODORO_DURATIONS,
    POMODORO_MODES,
    PomodoroCycle,
    Task,
    utcnow,
)
from .timeutils import day_start_utc, local_today, to_local

# Limites por modo: foco pode ser customizado até 3h; pausas têm teto menor.
MODE_MAX_MINUTES = {"focus": 180, "short_break": 30, "long_break": 90}


class InvalidCycle(ValueError):
    """Ciclo inválido (modo/duração)."""


class TaskNotFound(LookupError):
    """Tarefa inexistente ou de outro usuário."""


def record_cycle(
    user,
    mode: str,
    task_id: int | None = None,
    duration_minutes: int | None = None,
) -> PomodoroCycle:
    if mode not in POMODORO_MODES:
        raise InvalidCycle("Modo de ciclo inválido.")

    default_duration = POMODORO_DURATIONS[mode]
    if duration_minutes is None:
        duration = default_duration
    else:
        try:
            duration = int(duration_minutes)
        except (TypeError, ValueError) as exc:
            raise InvalidCycle("Duração inválida.") from exc

    if duration < 1 or duration > MODE_MAX_MINUTES[mode]:
        raise InvalidCycle(
            f"Duração deve estar entre 1 e {MODE_MAX_MINUTES[mode]} minutos."
        )

    task = None
    if task_id not in (None, "", 0, "0"):
        try:
            task_pk = int(task_id)
        except (TypeError, ValueError) as exc:
            raise TaskNotFound("Tarefa inválida.") from exc
        task = Task.query.filter_by(id=task_pk, user_id=user.id).first()
        if task is None:
            raise TaskNotFound("Tarefa não encontrada.")

    ended_at = utcnow()
    cycle = PomodoroCycle(
        user_id=user.id,
        task_id=task.id if task else None,
        mode=mode,
        duration_minutes=duration,
        started_at=ended_at - timedelta(minutes=duration),
        ended_at=ended_at,
        completed=True,
    )
    db.session.add(cycle)

    # Apenas foco consome a estimativa da tarefa. Pausas ficam no histórico,
    # mas não inflam o contador de pomodoros concluídos.
    if task is not None and mode == "focus":
        task.completed_pomodoros = (task.completed_pomodoros or 0) + 1
        task.updated_at = utcnow()

    db.session.commit()
    return cycle


def focus_stats(user, days: int = 7) -> dict:
    """Métricas de foco agregadas por dia local (para dashboard e HUD)."""
    days = max(1, min(days, 90))
    today = local_today()
    start = day_start_utc(today - timedelta(days=days - 1))

    cycles = (
        PomodoroCycle.query.filter(
            PomodoroCycle.user_id == user.id,
            PomodoroCycle.mode == "focus",
            PomodoroCycle.ended_at >= start,
        )
        .order_by(PomodoroCycle.ended_at.asc())
        .all()
    )

    daily_map: dict[str, dict] = {}
    for offset in range(days):
        day = today - timedelta(days=days - 1 - offset)
        daily_map[day.isoformat()] = {
            "date": day.isoformat(),
            "label": _weekday_label(day),
            "day": day.day,
            "cycles": 0,
            "minutes": 0,
        }

    total_cycles = 0
    total_minutes = 0
    cycle_dates: set = set()
    for cycle in cycles:
        local_dt = to_local(cycle.ended_at)
        if local_dt is None:
            continue
        key = local_dt.date().isoformat()
        total_cycles += 1
        total_minutes += cycle.duration_minutes
        cycle_dates.add(local_dt.date())
        if key in daily_map:
            daily_map[key]["cycles"] += 1
            daily_map[key]["minutes"] += cycle.duration_minutes

    daily = list(daily_map.values())
    today_key = today.isoformat()
    today_data = daily_map.get(today_key, {"cycles": 0, "minutes": 0})

    # Streak: dias consecutivos com pelo menos um ciclo de foco. Se hoje ainda
    # não houve foco, a sequência de ontem permanece "viva".
    streak = 0
    cursor = today if today in cycle_dates else today - timedelta(days=1)
    while cursor in cycle_dates:
        streak += 1
        cursor -= timedelta(days=1)

    max_minutes = max((d["minutes"] for d in daily), default=0) or 1

    return {
        "today": {
            "cycles": today_data["cycles"],
            # foco registrado hoje (não pausas)
            "minutes": today_data["minutes"],
            "label": _format_minutes(today_data["minutes"]),
        },
        "week": {
            "cycles": total_cycles,
            "minutes": total_minutes,
            "label": _format_minutes(total_minutes),
        },
        "streak": streak,
        "daily": daily,
        "max_minutes": max_minutes,
        "focus_cycles_today": today_data["cycles"],
        "next_long_break_in": (
            4 - (today_data["cycles"] % 4) if today_data["cycles"] % 4 else 4
        ),
    }


def suggested_next_mode(focus_cycles_today: int) -> str:
    """A cada 4 focos, sugere pausa longa; caso contrário, curta."""
    count = max(0, int(focus_cycles_today or 0))
    if count and count % 4 == 0:
        return "long_break"
    return "short_break"


def _weekday_label(day) -> str:
    return ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")[day.weekday()]


def _format_minutes(minutes: int) -> str:
    total = max(0, int(minutes or 0))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}h {mins:02d}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"
