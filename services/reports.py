"""Relatório semanal integrado: foco, tarefas, água e humor."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from models import MoodEntry, PomodoroCycle, Task, WaterLog
from services.categories import ensure_categories
from services.planning import week_start_for
from services.timeutils import day_start_utc, format_minutes, local_today, to_local
from services.water import (
    BEVERAGE_COEFFICIENTS,
    BEVERAGE_LABELS,
    format_ml,
    goal_range,
    hydration_balance,
    settings_for,
)

DAY_LABELS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
DAY_LABELS_FULL = (
    "segunda",
    "terça",
    "quarta",
    "quinta",
    "sexta",
    "sábado",
    "domingo",
)


def normalize_week(raw: str | None) -> date:
    current = week_start_for(local_today())
    if not raw:
        return current
    try:
        requested = week_start_for(date.fromisoformat(raw))
    except (TypeError, ValueError):
        return current
    return requested if requested <= current else current


def _pct_change(current: float, previous: float) -> int | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100)


def _collect(user, start: date) -> dict:
    end = start + timedelta(days=7)
    start_utc = day_start_utc(start)
    end_utc = day_start_utc(end)

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
    water_logs = (
        WaterLog.query.filter(
            WaterLog.user_id == user.id,
            WaterLog.logged_at >= start_utc,
            WaterLog.logged_at < end_utc,
        )
        .order_by(WaterLog.logged_at.asc())
        .all()
    )
    moods = (
        MoodEntry.query.filter(
            MoodEntry.user_id == user.id,
            MoodEntry.created_at >= start_utc,
            MoodEntry.created_at < end_utc,
        )
        .order_by(MoodEntry.created_at.asc())
        .all()
    )

    categories = ensure_categories(user)
    labels = {category.key: category for category in categories}
    fallback = categories[0].key if categories else "work"
    category_minutes = defaultdict(int)
    category_tasks = defaultdict(int)

    for cycle in cycles:
        key = cycle.task.category if cycle.task else fallback
        if key not in labels:
            key = fallback
        category_minutes[key] += cycle.duration_minutes or 0
    for task in completed_tasks:
        key = task.category if task.category in labels else fallback
        category_tasks[key] += 1

    settings = settings_for(user)
    goal = goal_range(settings)
    days = []
    by_day = {
        start + timedelta(days=index): {
            "focus_minutes": 0,
            "focus_sessions": 0,
            "tasks": 0,
            "water_ml": 0,
            "moods": [],
        }
        for index in range(7)
    }
    for cycle in cycles:
        local = to_local(cycle.ended_at)
        if local is not None and local.date() in by_day:
            by_day[local.date()]["focus_minutes"] += cycle.duration_minutes or 0
            by_day[local.date()]["focus_sessions"] += 1
    for task in completed_tasks:
        local = to_local(task.completed_at)
        if local is not None and local.date() in by_day:
            by_day[local.date()]["tasks"] += 1
    water_only_logs = [log for log in water_logs if log.kind == "water"]
    other_logs = [log for log in water_logs if log.kind != "water"]
    for log in water_only_logs:
        local = to_local(log.logged_at)
        if local is not None and local.date() in by_day:
            by_day[local.date()]["water_ml"] += log.amount_ml or 0
    for mood in moods:
        local = to_local(mood.created_at)
        if local is not None and local.date() in by_day:
            by_day[local.date()]["moods"].append(mood.mood)

    focus_max = max((item["focus_minutes"] for item in by_day.values()), default=0)
    task_max = max((item["tasks"] for item in by_day.values()), default=0)
    for index, (day, data) in enumerate(by_day.items()):
        mood_avg = (
            round(sum(data["moods"]) / len(data["moods"]), 1)
            if data["moods"]
            else 0
        )
        days.append(
            {
                "date": day,
                "label": DAY_LABELS[index],
                "label_full": DAY_LABELS_FULL[index],
                "is_today": day == local_today(),
                "focus_minutes": data["focus_minutes"],
                "focus_sessions": data["focus_sessions"],
                "focus_height": round(data["focus_minutes"] / focus_max * 100)
                if focus_max
                else 0,
                "tasks": data["tasks"],
                "task_height": round(data["tasks"] / task_max * 100)
                if task_max
                else 0,
                "water_ml": data["water_ml"],
                "mood_avg": mood_avg,
                "mood_count": len(data["moods"]),
            }
        )

    total_focus = sum(cycle.duration_minutes or 0 for cycle in cycles)
    total_water = sum(log.amount_ml or 0 for log in water_only_logs)
    other_total = sum(log.amount_ml or 0 for log in other_logs)
    balance = hydration_balance(water_logs, goal["target"])
    net_total = balance["net_ml"]
    compensation_total = balance["compensation_ml"]
    net_by_day = defaultdict(float)
    for log in water_logs:
        local = to_local(log.logged_at)
        if local is not None and local.date() in by_day:
            net_by_day[local.date()] += (log.amount_ml or 0) * BEVERAGE_COEFFICIENTS.get(
                log.kind, 1.0
            )
    net_days = sum(
        1
        for value in net_by_day.values()
        if goal["low"] <= value <= goal["high"]
    )
    other_by_kind: dict[str, dict] = {}
    for log in other_logs:
        row = other_by_kind.setdefault(
            log.kind,
            {"key": log.kind, "label": BEVERAGE_LABELS.get(log.kind, "Outro"), "ml": 0, "count": 0},
        )
        row["ml"] += log.amount_ml or 0
        row["count"] += 1
    other_summary = sorted(
        other_by_kind.values(), key=lambda item: item["ml"], reverse=True
    )
    mood_values = [mood.mood for mood in moods]
    mood_average = (
        round(sum(mood_values) / len(mood_values), 1) if mood_values else 0
    )
    water_days = sum(
        1 for item in days if item["water_ml"] >= goal["low"] and item["water_ml"] <= goal["high"]
    )
    category_rows = [
        {
            "key": category.key,
            "label": category.name,
            "icon": category.icon,
            "minutes": category_minutes.get(category.key, 0),
            "tasks": category_tasks.get(category.key, 0),
            "percent": round(
                category_minutes.get(category.key, 0) / total_focus * 100
            )
            if total_focus
            else 0,
        }
        for category in categories
    ]
    category_rows.sort(key=lambda row: row["minutes"], reverse=True)

    for item in days:
        minutes = item["focus_minutes"]
        item["focus_level"] = (
            0 if not minutes else 1 if minutes <= 30 else 2 if minutes <= 60 else 3 if minutes <= 90 else 4
        )
        item["task_level"] = min(4, item["tasks"])
        water = item["water_ml"]
        item["water_level"] = (
            0
            if not water
            else 1
            if water < goal["low"]
            else 2
            if water <= goal["high"]
            else 3
            if water < goal["high"] * 1.15
            else 4
        )
        mood = item["mood_avg"]
        item["mood_level"] = (
            0
            if not mood
            else 1
            if mood <= 2
            else 2
            if mood <= 3
            else 3
            if mood <= 4
            else 4
        )

    return {
        "start": start,
        "end": end - timedelta(days=1),
        "days": days,
        "cycles": len(cycles),
        "focus_minutes": total_focus,
        "tasks": len(completed_tasks),
        "water_total": total_water,
        "water_average": round(total_water / 7),
        "water_days": water_days,
        "other_total": other_total,
        "other_summary": other_summary,
        "net_total": net_total,
        "net_average": round(net_total / 7),
        "net_days": net_days,
        "compensation_total": compensation_total,
        "mood_average": mood_average,
        "mood_count": len(mood_values),
        "categories": category_rows,
        "categories_with_focus": [row for row in category_rows if row["minutes"]],
        "focus_max": focus_max,
        "task_max": task_max,
        "goal": goal,
    }


def report_for(user, raw_week: str | None = None) -> dict:
    current_start = week_start_for(local_today())
    start = normalize_week(raw_week)
    current = _collect(user, start)
    previous = _collect(user, start - timedelta(days=7))
    best_day = max(current["days"], key=lambda day: day["focus_minutes"])
    top_category = (
        current["categories_with_focus"][0]
        if current["categories_with_focus"]
        else None
    )
    focus_change = _pct_change(current["focus_minutes"], previous["focus_minutes"])
    water_change = _pct_change(current["water_average"], previous["water_average"])
    mood_change = round(current["mood_average"] - previous["mood_average"], 1)
    task_change = current["tasks"] - previous["tasks"]

    insights = []
    if current["focus_minutes"]:
        insights.append(
            {
                "kind": "focus",
                "title": f"Seu melhor dia foi {best_day['label_full']}.",
                "text": (
                    f"{best_day['focus_minutes']} minutos de foco em "
                    f"{best_day['focus_sessions']} "
                    f"{'sessão' if best_day['focus_sessions'] == 1 else 'sessões'}."
                ),
            }
        )
    if top_category:
        insights.append(
            {
                "kind": "category",
                "title": f"{top_category['label']} ganhou espaço.",
                "text": f"{top_category['percent']}% do tempo de foco ficou nessa categoria.",
            }
        )
    if current["water_total"] or current["other_total"]:
        water_avg = f"{current['water_average'] / 1000:.1f}".replace(".", ",")
        net_avg = f"{current['net_average'] / 1000:.1f}".replace(".", ",")
        insights.append(
            {
                "kind": "water",
                "title": f"Hidratação líquida média de {net_avg} L/dia.",
                "text": (
                    f"Água pura: {water_avg} L/dia; "
                    f"{current['water_days']}/7 dias na faixa de água. "
                    f"Compensação alcoólica estimada: {format_ml(current['compensation_total'])} ml."
                ),
            }
        )
    if current["other_total"]:
        parts = " · ".join(
            f"{item['label']} {item['ml']} ml" for item in current["other_summary"]
        )
        insights.append(
            {
                "kind": "water",
                "title": f"Outras bebidas: {parts}.",
                "text": "Entram no saldo com coeficientes próprios; álcool reduz a hidratação líquida.",
            }
        )
    if current["mood_count"]:
        insights.append(
            {
                "kind": "mood",
                "title": f"Humor médio de {current['mood_average']}/5.",
                "text": f"{current['mood_count']} check-in{'s' if current['mood_count'] != 1 else ''} na semana. São pistas, não diagnóstico.",
            }
        )
    if not insights:
        insights.append(
            {
                "kind": "empty",
                "title": "Ainda há pouco para comparar.",
                "text": "Registre foco, tarefas, água ou humor ao longo da semana para ver padrões aqui.",
            }
        )

    focus_total_style = ""
    if current["categories_with_focus"]:
        cursor = 0
        segments = []
        colors = ("var(--lav)", "var(--cyan)", "var(--amber)", "var(--green)", "var(--coral)")
        for index, row in enumerate(current["categories_with_focus"]):
            end = cursor + row["percent"]
            segments.append(f"{colors[index % len(colors)]} {cursor}% {end}%")
            cursor = end
        if cursor < 100:
            segments.append(f"var(--line) {cursor}% 100%")
        focus_total_style = "conic-gradient(" + ", ".join(segments) + ")"

    def level_width(value, other):
        maximum = max(value, other, 1)
        return round(value / maximum * 100)

    def change_text(value, percent=True):
        if value is None:
            return "sem base"
        if value == 0:
            return "estável"
        if percent:
            return f"{'+' if value > 0 else ''}{value}%"
        return f"{'+' if value > 0 else ''}{value}"

    focus_display = format_minutes(current["focus_minutes"])
    previous_focus_display = format_minutes(previous["focus_minutes"])
    water_display = f"{current['water_average'] / 1000:.1f}".replace(".", ",") + " L"
    previous_water_display = (
        f"{previous['water_average'] / 1000:.1f}".replace(".", ",") + " L"
    )
    mood_display = f"{current['mood_average']:.1f}".replace(".", ",")
    previous_mood_display = f"{previous['mood_average']:.1f}".replace(".", ",")

    return {
        "focus_display": focus_display,
        "previous_focus_display": previous_focus_display,
        "water_display": water_display,
        "previous_water_display": previous_water_display,
        "mood_display": mood_display,
        "previous_mood_display": previous_mood_display,
        "focus_change_text": change_text(focus_change),
        "task_change_text": change_text(task_change, percent=False),
        "water_change_text": change_text(water_change),
        "mood_change_text": (
            "estável"
            if mood_change == 0
            else f"{'+' if mood_change > 0 else ''}{str(mood_change).replace('.', ',')}"
        ),
        "comparison_rows": [
            {"label": "Foco", "current": current["focus_minutes"], "previous": previous["focus_minutes"], "width": level_width(current["focus_minutes"], previous["focus_minutes"]), "value": focus_display},
            {"label": "Tarefas", "current": current["tasks"], "previous": previous["tasks"], "width": level_width(current["tasks"], previous["tasks"]), "value": str(current["tasks"])},
            {"label": "Água", "current": current["water_average"], "previous": previous["water_average"], "width": level_width(current["water_average"], previous["water_average"]), "value": water_display},
            {"label": "Humor", "current": current["mood_average"], "previous": previous["mood_average"], "width": level_width(current["mood_average"], previous["mood_average"]), "value": mood_display},
        ],
        "week_start": start,
        "week_end": current["end"],
        "is_current": start == current_start,
        "previous_start": start - timedelta(days=7),
        "next_start": start + timedelta(days=7) if start < current_start else None,
        "current_start": current_start,
        "current": current,
        "previous": previous,
        "best_day": best_day,
        "top_category": top_category,
        "focus_change": focus_change,
        "task_change": task_change,
        "water_change": water_change,
        "mood_change": mood_change,
        "insights": insights,
        "donut_style": focus_total_style,
        "max_focus": max(current["focus_max"], previous["focus_max"], 1),
    }
