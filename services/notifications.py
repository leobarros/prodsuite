"""Notificações: rotina, preferências, central e agendamento local."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app
from sqlalchemy import and_

from extensions import db
from models import (
    MoodEntry,
    Notification,
    NotificationDelivery,
    NotificationSettings,
    PushSubscription,
    Task,
    User,
    WeeklyReview,
    utcnow,
)
from services.planning import week_start_for

logger = logging.getLogger(__name__)
UTC = timezone.utc
DELIVERY_WINDOW = timedelta(minutes=15)

WORKDAY_LABELS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
CATEGORY_LABELS = {
    "mood": "Check-in de humor",
    "weekly": "Revisão semanal",
    "task": "Prazo de tarefa",
}


def user_timezone(user: User) -> ZoneInfo:
    name = getattr(user, "timezone", None) or current_app.config.get(
        "APP_TIMEZONE", "America/Sao_Paulo"
    )
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def settings_for(user: User, create: bool = True) -> NotificationSettings | None:
    settings = db.session.get(NotificationSettings, user.id)
    if settings is None and create:
        settings = NotificationSettings(user_id=user.id)
        db.session.add(settings)
        db.session.flush()
    return settings


def checkin_time(settings: NotificationSettings) -> time:
    anchor = datetime.combine(date.today(), settings.work_end)
    return (anchor - timedelta(minutes=settings.mood_lead_minutes)).time()


def is_workday(settings: NotificationSettings, day: date) -> bool:
    return day.weekday() in settings.workday_set()


def is_quiet(settings: NotificationSettings, local_now: datetime) -> bool:
    current = local_now.time()
    start, end = settings.quiet_start, settings.quiet_end
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _local_midnight_utc(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC).replace(
        tzinfo=None
    )


def _in_window(local_now: datetime, scheduled: time, window=DELIVERY_WINDOW) -> bool:
    target = datetime.combine(local_now.date(), scheduled, tzinfo=local_now.tzinfo)
    return target <= local_now < target + window


def _dedupe(user_id: int, category: str, key: str) -> bool:
    exists = NotificationDelivery.query.filter_by(
        user_id=user_id, category=category, dedupe_key=key
    ).first()
    return exists is not None


def _create_notification(
    user: User,
    *,
    category: str,
    title: str,
    body: str,
    url: str,
    dedupe_key: str,
    push: bool,
) -> bool:
    if _dedupe(user.id, category, dedupe_key):
        return False
    db.session.add(
        NotificationDelivery(
            user_id=user.id,
            category=category,
            dedupe_key=dedupe_key,
        )
    )
    db.session.add(
        Notification(
            user_id=user.id,
            category=category,
            title=title,
            body=body,
            url=url,
        )
    )
    db.session.commit()
    if push:
        send_push(user, title=title, body=body, url=url)
    return True


def _mood_checked_in(user: User, day: date, tz: ZoneInfo) -> bool:
    start = _local_midnight_utc(day, tz)
    end = _local_midnight_utc(day + timedelta(days=1), tz)
    return (
        MoodEntry.query.filter(
            MoodEntry.user_id == user.id,
            MoodEntry.created_at >= start,
            MoodEntry.created_at < end,
        ).first()
        is not None
    )


def _weekly_reviewed(user: User, day: date) -> bool:
    return (
        WeeklyReview.query.filter_by(
            user_id=user.id, week_start=week_start_for(day)
        ).first()
        is not None
    )


def _due_tasks(user: User, day: date):
    return Task.query.filter(
        and_(
            Task.user_id == user.id,
            Task.due_date == day,
            Task.status != "done",
            Task.archived_at.is_(None),
        )
    ).all()


def run_due_notifications(now_utc: datetime | None = None) -> int:
    """Cria notificações e envia push para o que estiver na janela atual.

    O comando deve rodar a cada 5 ou 15 minutos. A chave de entrega impede
    duplicidade mesmo se o processo for repetido.
    """
    now_utc = now_utc or utcnow()
    sent = 0
    users = User.query.all()
    for user in users:
        settings = settings_for(user, create=False)
        if settings is None:
            continue
        tz = user_timezone(user)
        local_now = now_utc.replace(tzinfo=UTC).astimezone(tz)
        local_day = local_now.date()
        quiet = is_quiet(settings, local_now)
        workday = is_workday(settings, local_day)

        if settings.mood_enabled and (
            workday or settings.mood_rest_enabled
        ):
            scheduled = (
                checkin_time(settings) if workday else settings.mood_rest_time
            )
            if _in_window(local_now, scheduled) and not _mood_checked_in(
                user, local_day, tz
            ):
                sent += _create_notification(
                    user,
                    category="mood",
                    title="Um instante para você",
                    body="Como foi o seu dia? Registre seu check-in quando fizer sentido.",
                    url="/humor/",
                    dedupe_key=f"mood:{local_day.isoformat()}",
                    push=not quiet,
                )

        if (
            settings.weekly_enabled
            and local_day.weekday() == settings.weekly_day
            and _in_window(local_now, settings.weekly_time)
            and not _weekly_reviewed(user, local_day)
        ):
            sent += _create_notification(
                user,
                category="weekly",
                title="Sua semana está pronta para revisão",
                body="Reserve alguns minutos para olhar o que funcionou e definir o próximo passo.",
                url="/revisao",
                dedupe_key=f"weekly:{week_start_for(local_day).isoformat()}",
                push=not quiet,
            )

        if settings.task_enabled and _in_window(local_now, settings.task_time):
            for task in _due_tasks(user, local_day):
                sent += _create_notification(
                    user,
                    category="task",
                    title="Tarefa com prazo hoje",
                    body="Você tem uma tarefa com prazo para hoje.",
                    url=f"/tarefas/{task.id}",
                    dedupe_key=f"task:{task.id}:{local_day.isoformat()}",
                    push=not quiet,
                )

    return sent


def notifications_for(user: User, limit: int = 30):
    return (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


def recent_notifications(user: User, hours: int = 2):
    since = utcnow() - timedelta(hours=hours)
    return (
        Notification.query.filter(
            Notification.user_id == user.id,
            Notification.created_at >= since,
        )
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )


def unread_count(user: User) -> int:
    return Notification.query.filter_by(
        user_id=user.id, read_at=None
    ).count()


def mark_read(user: User, notification_id: int) -> bool:
    item = Notification.query.filter_by(
        id=notification_id, user_id=user.id
    ).first()
    if item is None:
        return False
    if item.read_at is None:
        item.read_at = utcnow()
        db.session.commit()
    return True


def vapid_public_key() -> str:
    return current_app.config.get("VAPID_PUBLIC_KEY", "")


def send_push(user: User, *, title: str, body: str, url: str = "/") -> int:
    """Envia para todos os dispositivos; falhas removem subscriptions mortas."""
    private_key = current_app.config.get("VAPID_PRIVATE_KEY", "")
    public_key = current_app.config.get("VAPID_PUBLIC_KEY", "")
    if not private_key or not public_key:
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # ambiente sem dependência opcional
        logger.warning("pywebpush indisponível; push ignorado")
        return 0

    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    sent = 0
    for subscription in subscriptions:
        payload = json.dumps(
            {"title": title, "body": body, "url": url},
            ensure_ascii=False,
        )
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh,
                        "auth": subscription.auth,
                    },
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": current_app.config.get("VAPID_SUBJECT", "mailto:admin@localhost")},
            )
            subscription.last_seen_at = utcnow()
            sent += 1
        except WebPushException:
            db.session.delete(subscription)
        except Exception:  # pragma: no cover - defesa contra provedores instáveis
            logger.exception("Falha ao enviar push para usuário %s", user.id)
    db.session.commit()
    return sent
