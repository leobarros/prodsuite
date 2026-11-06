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


def _normalized_shares(counts: dict[str, int]) -> dict[str, int]:
    """Distribui 100% entre contextos, sem perder a soma por arredondamento."""
    total = sum(counts.values())
    if not total:
        return {}
    raw = {key: count / total * 100 for key, count in counts.items()}
    shares = {key: int(value) for key, value in raw.items()}
    missing = 100 - sum(shares.values())
    if missing:
        ranked = sorted(
            raw, key=lambda key: raw[key] - shares[key], reverse=True
        )
        for key in ranked[:missing]:
            shares[key] += 1
    return shares


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
    previous_start = day_start_utc(week_start - timedelta(days=7))
    previous_entries = (
        MoodEntry.query.filter(
            MoodEntry.user_id == user.id,
            MoodEntry.created_at >= previous_start,
            MoodEntry.created_at < start,
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
    context_mood_sums: dict[str, int] = {}
    previous_context_counts: dict[str, int] = {}
    for entry in entries:
        for key in (entry.contexts or "").split(","):
            if key in CONTEXT_KEYS:
                context_counts[key] = context_counts.get(key, 0) + 1
                context_mood_sums[key] = context_mood_sums.get(key, 0) + entry.mood
    for entry in previous_entries:
        for key in (entry.contexts or "").split(","):
            if key in CONTEXT_KEYS:
                previous_context_counts[key] = previous_context_counts.get(key, 0) + 1

    all_moods = [entry.mood for entry in entries]
    previous_moods = [entry.mood for entry in previous_entries]
    average_mood = (
        round(sum(all_moods) / len(all_moods), 1) if all_moods else 0
    )
    previous_average_mood = (
        round(sum(previous_moods) / len(previous_moods), 1)
        if previous_moods
        else 0
    )
    context_entry_count = sum(
        1
        for entry in entries
        if any(key in CONTEXT_KEYS for key in (entry.contexts or "").split(","))
    )
    previous_context_entry_count = sum(
        1
        for entry in previous_entries
        if any(key in CONTEXT_KEYS for key in (entry.contexts or "").split(","))
    )
    context_tag_count = sum(context_counts.values())
    context_shares = _normalized_shares(context_counts)
    current_max_context_count = max(context_counts.values(), default=0)
    previous_max_context_count = max(previous_context_counts.values(), default=0)
    max_context_count = max(current_max_context_count, previous_max_context_count, 1)
    comparison_frequency_max = max_context_count
    context_radar = []
    for key, label in CONTEXTS:
        count = context_counts.get(key, 0)
        mood_avg = (
            round(context_mood_sums.get(key, 0) / count, 1) if count else 0
        )
        enough = count >= 2
        context_radar.append(
            {
                "key": key,
                "label": label,
                "count": count,
                "mood_avg": mood_avg,
                "delta": round(mood_avg - average_mood, 1) if enough else 0,
                "enough": enough,
                "previous_count": previous_context_counts.get(key, 0),
                "count_delta": count - previous_context_counts.get(key, 0),
                "frequency_value": round(count / max_context_count * 100) if count else 0,
                "previous_frequency_value": round(
                    previous_context_counts.get(key, 0) / max_context_count * 100
                )
                if previous_context_counts.get(key, 0)
                else 0,
                "share_percent": context_shares.get(key, 0),
                "previous_share_percent": round(
                    previous_context_counts.get(key, 0)
                    / previous_context_entry_count
                    * 100
                )
                if previous_context_entry_count and previous_context_counts.get(key, 0)
                else 0,
                "impact_value": round(mood_avg / 5 * 100) if enough else 0,
            }
        )
    context_summary = [
        item for item in context_radar if item["count"]
    ]
    context_summary.sort(key=lambda item: item["count"], reverse=True)

    return {
        "today": today,
        "week_days": week_days,
        "today_entries": today_entries,
        "recent": recent,
        "week_count": len(entries),
        "average_mood": average_mood,
        "context_summary": context_summary,
        "context_radar": context_radar,
        "frequency_max": max_context_count,
        "comparison_frequency_max": comparison_frequency_max,
        "context_entry_count": context_entry_count,
        "context_tag_count": context_tag_count,
        "previous_context_entry_count": previous_context_entry_count,
        "previous_week_count": len(previous_entries),
        "previous_average_mood": previous_average_mood,
        "mood_delta": (
            round(average_mood - previous_average_mood, 1)
            if previous_moods
            else None
        ),
        "previous_week_start": week_start - timedelta(days=7),
        "previous_week_end": week_start - timedelta(days=1),
        "has_previous_data": bool(previous_entries),
        "has_context_data": bool(context_summary),
        "has_impact_data": any(item["enough"] for item in context_radar),
        "impact_context_count": sum(1 for item in context_radar if item["enough"]),
        "labels": MOOD_LABELS,
        "colors": MOOD_COLORS,
        "contexts": CONTEXTS,
    }
