"""Preferências de notificação, assinatura Web Push e central interna."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import PushSubscription, utcnow
from services.notifications import (
    CATEGORY_LABELS,
    WORKDAY_LABELS,
    checkin_time,
    mark_read,
    notifications_for,
    settings_for,
    unread_count,
    vapid_public_key,
)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notificacoes")


def _parse_time(raw: str | None, default):
    try:
        return datetime.strptime((raw or "").strip(), "%H:%M").time()
    except ValueError:
        return default


@notifications_bp.get("/")
@login_required
def index():
    settings = settings_for(current_user)
    db.session.commit()
    return render_template(
        "notifications.html",
        settings=settings,
        notifications=notifications_for(current_user),
        unread=unread_count(current_user),
        public_key=vapid_public_key(),
        workday_labels=WORKDAY_LABELS,
        category_labels=CATEGORY_LABELS,
        checkin=checkin_time(settings),
    )


@notifications_bp.post("/configurar")
@login_required
def configure():
    settings = settings_for(current_user)
    tz_name = (request.form.get("timezone") or "").strip()
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        flash("Informe um fuso horário IANA válido.", "danger")
        return redirect(url_for("notifications.index"))
    if tz_name:
        current_user.timezone = tz_name

    workdays = sorted(
        int(value)
        for value in request.form.getlist("workdays")
        if value.isdigit() and 0 <= int(value) <= 6
    )
    settings.workdays = ",".join(str(value) for value in workdays)
    settings.work_start = _parse_time(
        request.form.get("work_start"), settings.work_start
    )
    settings.work_end = _parse_time(request.form.get("work_end"), settings.work_end)
    settings.quiet_start = _parse_time(
        request.form.get("quiet_start"), settings.quiet_start
    )
    settings.quiet_end = _parse_time(
        request.form.get("quiet_end"), settings.quiet_end
    )
    settings.mood_enabled = bool(request.form.get("mood_enabled"))
    settings.mood_rest_enabled = bool(request.form.get("mood_rest_enabled"))
    settings.mood_rest_time = _parse_time(
        request.form.get("mood_rest_time"), settings.mood_rest_time
    )
    settings.weekly_enabled = bool(request.form.get("weekly_enabled"))
    day = request.form.get("weekly_day", "6")
    settings.weekly_day = int(day) if day.isdigit() and 0 <= int(day) <= 6 else 6
    settings.weekly_time = _parse_time(
        request.form.get("weekly_time"), settings.weekly_time
    )
    settings.task_enabled = bool(request.form.get("task_enabled"))
    settings.task_time = _parse_time(
        request.form.get("task_time"), settings.task_time
    )
    db.session.commit()
    flash("Preferências de notificação atualizadas.", "success")
    return redirect(url_for("notifications.index"))


@notifications_bp.post("/assinar")
@login_required
def subscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify(ok=False, error="Assinatura inválida."), 400
    subscription = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if subscription is None:
        subscription = PushSubscription(
            user_id=current_user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=request.user_agent.string[:255],
        )
        db.session.add(subscription)
    else:
        subscription.user_id = current_user.id
        subscription.p256dh = p256dh
        subscription.auth = auth
        subscription.last_seen_at = utcnow()
    db.session.commit()
    return jsonify(ok=True)


@notifications_bp.post("/cancelar")
@login_required
def unsubscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get("endpoint") or "").strip()
    PushSubscription.query.filter_by(
        user_id=current_user.id, endpoint=endpoint
    ).delete()
    db.session.commit()
    return jsonify(ok=True)


@notifications_bp.post("/ler/<int:notification_id>")
@login_required
def read(notification_id: int):
    if not mark_read(current_user, notification_id):
        return jsonify(ok=False), 404
    if request.is_json or request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    return redirect(url_for("notifications.index"))


@notifications_bp.post("/ler-tudo")
@login_required
def read_all():
    from models import Notification

    Notification.query.filter_by(user_id=current_user.id, read_at=None).update(
        {"read_at": utcnow()}
    )
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    return redirect(url_for("notifications.index"))
