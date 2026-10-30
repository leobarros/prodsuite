"""Conversão de datas entre UTC (banco) e o fuso de exibição."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app

_UTC = timezone.utc


def app_timezone() -> ZoneInfo:
    name = current_app.config.get("APP_TIMEZONE", "America/Sao_Paulo")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:  # pragma: no cover - ambiente sem tzdata
        return ZoneInfo("UTC")


def to_local(value: datetime | None) -> datetime | None:
    """Assume que datetimes do banco são UTC naive e devolve aware local."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=_UTC)
    return value.astimezone(app_timezone())


def local_today() -> date:
    return datetime.now(_UTC).astimezone(app_timezone()).date()


def day_start_utc(day: date) -> datetime:
    """Meia-noite local de ``day`` convertida para UTC naive."""
    local_midnight = datetime.combine(day, time.min, tzinfo=app_timezone())
    return local_midnight.astimezone(_UTC).replace(tzinfo=None)


def format_minutes(minutes: int | float | None) -> str:
    """Formata 85 -> '1h 25m' (usado em métricas de foco)."""
    total = max(0, int(minutes or 0))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}h {mins:02d}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def seconds_to_clock(seconds: int | float | None) -> str:
    total = max(0, int(seconds or 0))
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


def local_date_bounds(days: int = 1) -> tuple[datetime, date]:
    """Início UTC para os últimos ``days`` dias (inclui hoje) e a data local."""
    today = local_today()
    return day_start_utc(today - timedelta(days=days - 1)), today
