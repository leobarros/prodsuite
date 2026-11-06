"""Hidratação: água, outras bebidas, faixa pessoal e resumo diário."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from extensions import db
from models import WaterLog, WaterSettings, utcnow
from services.timeutils import day_start_utc, local_today, to_local

DEFAULT_LOW_ML = 1800
DEFAULT_HIGH_ML = 2200
MAX_AMOUNT_ML = 1000
MAX_HOURLY_ML = 1000

# Coeficientes de saldo líquido definidos no algoritmo de hidratação.
BEVERAGE_TYPES = (
    {"key": "water", "label": "Água", "icon": "bi-droplet", "coefficient": 1.0},
    {"key": "coffee", "label": "Café coado", "icon": "bi-cup-hot", "coefficient": 0.8},
    {"key": "tea", "label": "Chá", "icon": "bi-cup-straw", "coefficient": 0.9},
    {"key": "espresso", "label": "Café espresso", "icon": "bi-cup-hot", "coefficient": 0.6},
    {"key": "beer", "label": "Cerveja", "icon": "bi-cup", "coefficient": -0.5},
    {"key": "wine", "label": "Vinho", "icon": "bi-cup", "coefficient": -1.2},
    {"key": "spirits", "label": "Destilado", "icon": "bi-cup", "coefficient": -1.2},
    {"key": "other", "label": "Outro", "icon": "bi-cup", "coefficient": 1.0},
)
BEVERAGE_KEYS = {item["key"] for item in BEVERAGE_TYPES}
BEVERAGE_LABELS = {item["key"]: item["label"] for item in BEVERAGE_TYPES}
BEVERAGE_ICONS = {item["key"]: item["icon"] for item in BEVERAGE_TYPES}
BEVERAGE_COEFFICIENTS = {
    item["key"]: item["coefficient"] for item in BEVERAGE_TYPES
}
ALCOHOL_KEYS = {"beer", "wine", "spirits"}


def settings_for(user, create: bool = False) -> WaterSettings | None:
    settings = db.session.get(WaterSettings, user.id)
    if settings is None and create:
        settings = WaterSettings(user_id=user.id)
        db.session.add(settings)
        db.session.flush()
    return settings


def goal_range(settings: WaterSettings | None) -> dict:
    """Faixa de água em ml. A fórmula é referência inicial, não prescrição."""
    low = DEFAULT_LOW_ML
    high = DEFAULT_HIGH_ML
    extra = 0
    if settings is not None and settings.weight_kg:
        weight = float(settings.weight_kg)
        low = round(weight * 30 / 50) * 50
        high = round(weight * 35 / 50) * 50
        extra = max(0, min(int(settings.extra_ml or 0), 1000))
    low += extra
    high += extra
    return {
        "low": low,
        "high": high,
        "target": high,
        "extra": extra,
        "personalized": bool(settings and settings.weight_kg),
    }


def format_ml(amount_ml: float) -> str:
    value = float(amount_ml or 0)
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def format_liters(amount_ml: int) -> str:
    liters = max(0, int(amount_ml or 0)) / 1000
    if abs(liters - round(liters)) < 0.05:
        return f"{int(round(liters))} L"
    return f"{liters:.2f}".replace(".", ",") + " L"


def today_logs(user, day=None):
    day = day or local_today()
    start = day_start_utc(day)
    end = start + timedelta(days=1)
    return (
        WaterLog.query.filter(
            WaterLog.user_id == user.id,
            WaterLog.logged_at >= start,
            WaterLog.logged_at < end,
        )
        .order_by(WaterLog.logged_at.asc())
        .all()
    )


def valid_kind(kind: str | None) -> str:
    value = (kind or "water").strip().casefold()
    return value if value in BEVERAGE_KEYS else "water"


def add_log(user, amount_ml: int, kind: str = "water") -> WaterLog:
    amount = int(amount_ml)
    if amount < 10 or amount > MAX_AMOUNT_ML:
        raise ValueError("Informe entre 10 e 1000 ml.")
    kind = valid_kind(kind)
    log = WaterLog(
        user_id=user.id,
        amount_ml=amount,
        kind=kind,
        logged_at=utcnow(),
    )
    db.session.add(log)
    db.session.commit()
    return log


def hydration_balance(logs, target_ml: int) -> dict:
    """Saldo líquido e compensação, conforme coeficientes do algoritmo."""
    net = 0.0
    water_total = 0
    compensation = 0.0
    for log in logs:
        coefficient = BEVERAGE_COEFFICIENTS.get(log.kind, 1.0)
        net += (log.amount_ml or 0) * coefficient
        if log.kind == "water":
            water_total += log.amount_ml or 0
        if coefficient < 0:
            compensation += (log.amount_ml or 0) * (1 + abs(coefficient))
    progress = (net / target_ml * 100) if target_ml else 0
    return {
        "net_ml": round(net, 1),
        "water_ml": water_total,
        "compensation_ml": round(compensation, 1),
        "percent": round(max(0.0, progress), 1),
        "percent_capped": min(100, max(0, round(progress))),
    }


def summary_for(user, day=None):
    day = day or local_today()
    settings = settings_for(user)
    logs = today_logs(user, day)
    water_logs = [log for log in logs if log.kind == "water"]
    other_logs = [log for log in logs if log.kind != "water"]
    total = sum(log.amount_ml for log in water_logs)
    other_total = sum(log.amount_ml for log in other_logs)
    goal = goal_range(settings)
    target = goal["target"]
    low = goal["low"]
    high = goal["high"]
    balance = hydration_balance(logs, target)
    net_hydration = balance["net_ml"]
    percent = balance["percent_capped"]
    net_percent = balance["percent"]

    if net_hydration > high:
        status_key, status_label = "above", "acima da faixa"
    elif net_hydration >= low:
        status_key, status_label = "in_range", "na faixa"
    else:
        status_key, status_label = "below", "abaixo da faixa"

    recent = (
        WaterLog.query.filter_by(user_id=user.id)
        .order_by(WaterLog.logged_at.desc(), WaterLog.id.desc())
        .limit(8)
        .all()
    )

    now = utcnow()
    last_hour = sum(
        log.amount_ml
        for log in WaterLog.query.filter(
            WaterLog.user_id == user.id,
            WaterLog.kind == "water",
            WaterLog.logged_at >= now - timedelta(hours=1),
        ).all()
    )

    week_start = day - timedelta(days=6)
    week_start_utc = day_start_utc(week_start)
    week_logs = (
        WaterLog.query.filter(
            WaterLog.user_id == user.id,
            WaterLog.kind == "water",
            WaterLog.logged_at >= week_start_utc,
        )
        .order_by(WaterLog.logged_at.asc())
        .all()
    )
    daily_map = {
        (week_start + timedelta(days=index)): 0 for index in range(7)
    }
    for log in week_logs:
        local = to_local(log.logged_at)
        if local is not None and local.date() in daily_map:
            daily_map[local.date()] += log.amount_ml
    week_days = [
        {
            "date": current.isoformat(),
            "label": ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")[
                current.weekday()
            ],
            "ml": amount,
            "is_today": current == day,
        }
        for current, amount in daily_map.items()
    ]
    week_total = sum(item["ml"] for item in week_days)
    week_average = round(week_total / 7) if week_days else 0
    in_range_days = sum(
        1 for item in week_days if item["ml"] >= low and item["ml"] <= high
    )

    other_by_kind = defaultdict(lambda: {"count": 0, "ml": 0})
    for log in other_logs:
        data = other_by_kind[log.kind]
        data["count"] += 1
        data["ml"] += log.amount_ml
    other_summary = []
    for item in BEVERAGE_TYPES:
        key = item["key"]
        if key == "water" or key not in other_by_kind:
            continue
        data = other_by_kind[key]
        other_summary.append(
            {
                "key": key,
                "label": item["label"],
                "icon": item["icon"],
                "count": data["count"],
                "ml": data["ml"],
                "is_alcohol": key in ALCOHOL_KEYS,
                "coefficient": BEVERAGE_COEFFICIENTS.get(key, 1.0),
                "net_ml": round(data["ml"] * BEVERAGE_COEFFICIENTS.get(key, 1.0), 1),
                "compensation_ml": round(
                    data["ml"] * (1 + abs(BEVERAGE_COEFFICIENTS.get(key, 1.0))),
                    1,
                )
                if key in ALCOHOL_KEYS
                else 0,
            }
        )

    other_week_logs = (
        WaterLog.query.filter(
            WaterLog.user_id == user.id,
            WaterLog.kind != "water",
            WaterLog.logged_at >= week_start_utc,
        )
        .all()
    )
    other_week_total = sum(log.amount_ml for log in other_week_logs)

    return {
        "day": day,
        "settings": settings,
        "goal": goal,
        "total": total,
        "other_total": other_total,
        "other_summary": other_summary,
        "other_week_total": other_week_total,
        "percent": percent,
        "net_hydration": net_hydration,
        "net_hydration_display": format_ml(net_hydration),
        "net_percent": net_percent,
        "water_percent": round(total / target * 100, 1) if target else 0,
        "water_display": format_ml(total),
        "other_display": format_ml(other_total),
        "compensation_ml": balance["compensation_ml"],
        "compensation_display": format_ml(balance["compensation_ml"]),
        "remaining": max(0, target - net_hydration),
        "remaining_display": format_ml(max(0, target - net_hydration)),
        "status_key": status_key,
        "status_label": status_label,
        "recent": recent,
        "last_hour": last_hour,
        "hourly_warning": last_hour > MAX_HOURLY_ML,
        "week_days": week_days,
        "week_total": week_total,
        "week_average": week_average,
        "in_range_days": in_range_days,
        "kind_labels": BEVERAGE_LABELS,
        "kind_icons": BEVERAGE_ICONS,
        "kind_coefficients": BEVERAGE_COEFFICIENTS,
        "beverage_types": BEVERAGE_TYPES,
        "water_log_count": len(water_logs),
        "other_log_count": len(other_logs),
    }
