"""Registro de humor: check-ins, resumo semanal e contexto."""

from __future__ import annotations

from datetime import timedelta

from extensions import db
from models import MoodEntry, utcnow
from services.timeutils import day_start_utc, local_today, to_local

MOOD_LABELS = {
    1: "Muito mal",
    2: "Mal",
    3: "Neutro",
    4: "Bem",
    5: "Muito bem",
}
MOOD_SHORT = {1: "Muito mal", 2: "Mal", 3: "Neutro", 4: "Bem", 5: "Muito bem"}
MOOD_COLORS = {1: "m1", 2: "m2", 3: "m3", 4: "m4", 5: "m5"}
CONTEXTS = [
    ("sono", "Sono"),
    ("trabalho", "Trabalho"),
    ("estudos", "Estudos"),
    ("relacoes", "Relações"),
    ("corpo", "Corpo"),
    ("familia", "Família"),
]
CONTEXT_KEYS = {key for key, _ in CONTEXTS}
CONTEXT_LABELS = dict(CONTEXTS)


def clamp_scale(value, default=3) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return default


def parse_contexts(raw_values) -> str:
    values = raw_values if isinstance(raw_values, list) else [raw_values]
    selected = []
    for raw in values:
        key = (raw or "").strip().casefold()
        if key in CONTEXT_KEYS and key not in selected:
            selected.append(key)
    return ",".join(selected)


def context_list(raw: str | None) -> list[tuple[str, str]]:
    keys = {item for item in (raw or "").split(",") if item}
    return [(key, label) for key, label in CONTEXTS if key in keys]


def create_entry(user, *, mood, energy, tension, contexts, note) -> MoodEntry:
    note = (note or "").strip()
    if len(note) > 500:
        raise ValueError("A nota pode ter no máximo 500 caracteres.")
    entry = MoodEntry(
        user_id=user.id,
        mood=clamp_scale(mood),
        energy=clamp_scale(energy),
        tension=clamp_scale(tension, 2),
        contexts=parse_contexts(contexts),
        note=note,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def summary_for(user):
    today = local_today()
    week_start = today - timedelta(days=6)
    start = day_start_utc(week_start)
    entries = (
        MoodEntry.query.filter(
            MoodEntry.user_id == user.id,
            MoodEntry.created_at >= start,
        )
        .order_by(MoodEntry.created_at.asc())
        .all()
    )

    daily = {
        week_start + timedelta(days=index): []
        for index in range(7)
    }
    for entry in entries:
        local = to_local(entry.created_at)
        if local is not None and local.date() in daily:
            daily[local.date()].append(entry)

    week_days = []
    for day, day_entries in daily.items():
        avg = (
            round(sum(item.mood for item in day_entries) / len(day_entries), 1)
            if day_entries
            else 0
        )
        week_days.append(
            {
                "date": day.isoformat(),
                "label": ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")[
                    day.weekday()
                ],
                "average": avg,
                "count": len(day_entries),
                "is_today": day == today,
                "height": round(avg / 5 * 100) if avg else 2,
            }
        )

    today_entries = daily.get(today, [])
    recent = (
        MoodEntry.query.filter_by(user_id=user.id)
        .order_by(MoodEntry.created_at.desc())
        .limit(8)
        .all()
    )
    context_counts: dict[str, int] = {}
    for entry in entries:
        for key in (entry.contexts or "").split(","):
            if key in CONTEXT_KEYS:
                context_counts[key] = context_counts.get(key, 0) + 1
    context_summary = [
        {"key": key, "label": label, "count": context_counts.get(key, 0)}
        for key, label in CONTEXTS
        if context_counts.get(key, 0)
    ]
    context_summary.sort(key=lambda item: item["count"], reverse=True)

    all_moods = [entry.mood for entry in entries]
    average_mood = (
        round(sum(all_moods) / len(all_moods), 1) if all_moods else 0
    )
    return {
        "today": today,
        "week_days": week_days,
        "today_entries": today_entries,
        "recent": recent,
        "week_count": len(entries),
        "average_mood": average_mood,
        "context_summary": context_summary,
        "labels": MOOD_LABELS,
        "colors": MOOD_COLORS,
        "contexts": CONTEXTS,
    }
