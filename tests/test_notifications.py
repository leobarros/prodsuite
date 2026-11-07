"""Testes das preferências, central e agendamento de notificações."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from extensions import db
from models import (
    MoodEntry,
    Notification,
    NotificationSettings,
    PushSubscription,
    Task,
    User,
    WeeklyReview,
)
from tests.conftest import login

from services.notifications import (
    checkin_time,
    is_quiet,
    run_due_notifications,
    settings_for,
    user_timezone,
)


def _settings(app, user_id, **values):
    with app.app_context():
        settings = NotificationSettings(user_id=user_id, **values)
        db.session.add(settings)
        db.session.commit()
        return settings


def test_notification_page_requires_login(client):
    response = client.get("/notificacoes/")
    assert response.status_code == 302
    assert "/entrar" in response.headers["Location"]


def test_notification_settings_live_in_profile_not_in_menu(client, make_user):
    make_user()
    login(client)
    profile = client.get("/perfil").get_data(as_text=True)
    assert 'id="notificacoes"' in profile
    assert 'action="/notificacoes/configurar"' in profile
    assert "Meia hora antes do fim do expediente" in profile
    assert "Notificações</span>" in profile
    central = client.get("/notificacoes/").get_data(as_text=True)
    assert "Configurar no perfil" in central
    assert 'action="/notificacoes/configurar"' not in central

def test_notification_settings_are_per_user_and_derive_checkin(
    client, app, make_user
):
    user_id = make_user()
    login(client)
    response = client.post(
        "/notificacoes/configurar",
        data={
            "timezone": "America/Manaus",
            "workdays": ["0", "1", "2", "3", "4"],
            "work_start": "09:00",
            "work_end": "18:00",
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "mood_enabled": "on",
            "weekly_enabled": "on",
            "weekly_day": "6",
            "weekly_time": "18:00",
            "task_enabled": "on",
            "task_time": "09:00",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, user_id)
        settings = NotificationSettings.query.filter_by(user_id=user_id).one()
        assert user.timezone == "America/Manaus"
        assert settings.workday_set() == {0, 1, 2, 3, 4}
        assert checkin_time(settings) == time(17, 30)


def test_checkin_time_crosses_midnight_safely():
    settings = NotificationSettings(
        user_id=1, work_end=time(0, 10), mood_lead_minutes=30
    )
    assert checkin_time(settings) == time(23, 40)


def test_scheduler_creates_mood_notification_once_and_respects_existing_checkin(
    app, make_user
):
    user_id = make_user()
    _settings(app, user_id, mood_enabled=True, mood_rest_enabled=False)
    # Sexta, 06/11/2026, 16:30 em São Paulo (UTC-3) = 19:30 UTC.
    now = datetime(2026, 11, 6, 19, 31)
    with app.app_context():
        assert run_due_notifications(now) == 1
        assert run_due_notifications(now) == 0
        assert Notification.query.filter_by(user_id=user_id).count() == 1
        # Um check-in no mesmo dia impede novo lembrete em outra execução.
        db.session.add(
            MoodEntry(
                user_id=user_id,
                mood=4,
                energy=3,
                tension=2,
                created_at=now,
            )
        )
        db.session.commit()
        assert run_due_notifications(now + timedelta(minutes=10)) == 0


def test_scheduler_creates_weekly_and_task_notifications(app, make_user):
    user_id = make_user()
    _settings(
        app,
        user_id,
        weekly_enabled=True,
        weekly_day=6,
        weekly_time=time(18, 0),
        mood_enabled=False,
        task_enabled=True,
        task_time=time(9, 0),
    )
    with app.app_context():
        db.session.add(
            Task(
                user_id=user_id,
                title="Tarefa com prazo",
                status="todo",
                due_date=date(2026, 11, 9),
            )
        )
        db.session.commit()
    # Domingo, 08/11/2026, 18:05 em São Paulo = 21:05 UTC.
    weekly_now = datetime(2026, 11, 8, 21, 5)
    with app.app_context():
        assert run_due_notifications(weekly_now) == 1
        assert Notification.query.filter_by(user_id=user_id, category="weekly").count() == 1

    # Segunda, 09/11/2026, 09:05 em São Paulo = 12:05 UTC.
    task_now = datetime(2026, 11, 9, 12, 5)
    with app.app_context():
        assert run_due_notifications(task_now) == 1
        assert Notification.query.filter_by(user_id=user_id, category="task").count() == 1


def test_weekly_notification_skips_saved_review(app, make_user):
    user_id = make_user()
    _settings(
        app,
        user_id,
        weekly_enabled=True,
        weekly_day=6,
        weekly_time=time(18, 0),
        mood_enabled=False,
        task_enabled=False,
    )
    with app.app_context():
        db.session.add(
            WeeklyReview(
                user_id=user_id, week_start=date(2026, 11, 2), wins="ok"
            )
        )
        db.session.commit()
    with app.app_context():
        assert run_due_notifications(datetime(2026, 11, 8, 21, 5)) == 0


def test_quiet_hours_are_detected_across_midnight():
    settings = NotificationSettings(
        user_id=1,
        quiet_start=time(22, 0),
        quiet_end=time(7, 0),
    )
    assert is_quiet(settings, datetime(2026, 11, 8, 23, 0)) is True
    assert is_quiet(settings, datetime(2026, 11, 8, 6, 30)) is True
    assert is_quiet(settings, datetime(2026, 11, 8, 12, 0)) is False


def test_push_subscription_is_owned_by_current_user(client, app, make_user):
    user_id = make_user()
    login(client)
    response = client.post(
        "/notificacoes/assinar",
        json={
            "endpoint": "https://push.example.test/sub",
            "keys": {"p256dh": "abc", "auth": "def"},
        },
    )
    assert response.status_code == 200
    with app.app_context():
        sub = PushSubscription.query.filter_by(user_id=user_id).one()
        assert sub.endpoint.endswith("/sub")


def test_service_worker_contains_push_handlers(app):
    with app.app_context():
        from pathlib import Path

        source = (
            Path(app.static_folder) / ".." / "static" / "sw.js"
        ).resolve().read_text()
        assert 'addEventListener("push"' in source
        assert 'addEventListener("notificationclick"' in source
