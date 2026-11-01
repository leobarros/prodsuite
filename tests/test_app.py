"""Testes de aceitação e de regras de negócio da PRD//SUITE.

Cobrem:
* modelos e transições de estado;
* autenticação, hash, timeout de sessão e invalidação por nonce;
* CSRF, headers de segurança e isolamento entre usuários;
* tarefas, rascunhos, notas/Markdown e busca;
* API de Pomodoro e regras de contagem;
* exportação JSON e snapshot SQLite por usuário;
* endpoints PWA (manifest, service worker, offline).
"""

from __future__ import annotations

import json
import re
import sqlite3
import struct
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from extensions import db
from models import (
    BoardColumn,
    Category,
    Project,
    TaskColumnStay,
    Note,
    PomodoroCycle,
    Scratchpad,
    Task,
    User,
    WeeklyReview,
    utcnow,
)
from services.categories import ensure_categories
from services.planning import weekly_metrics
from services.pomodoro import (
    InvalidCycle,
    TaskNotFound,
    focus_stats,
    record_cycle,
)
from tests.conftest import login

STATIC = Path(__file__).resolve().parent.parent / "static"


# ==========================================================================
# MODELOS E REGRAS DE NEGÓCIO
# ==========================================================================
class TestModels:
    def test_password_hashed_and_verified(self, app, make_user):
        user_id = make_user("alice", password="SenhaForte1!")
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.password_hash != "SenhaForte1!"
            assert "SenhaForte1!" not in user.password_hash
            assert user.check_password("SenhaForte1!") is True
            assert user.check_password("errada") is False

    def test_session_nonce_rotation(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            user = db.session.get(User, user_id)
            original = user.session_nonce
            rotated = user.rotate_session_nonce()
            assert rotated != original
            assert len(rotated) == 32

    def test_task_move_to_done_sets_and_clears_completed_at(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            task = Task(user_id=user_id, title="Fechar ciclo", estimate_pomodoros=2)
            db.session.add(task)
            db.session.commit()

            task.move_to("done")
            assert task.status == "done"
            assert task.completed_at is not None
            assert task.is_done is True

            first_completion = task.completed_at
            task.move_to("doing")
            assert task.completed_at is None
            assert task.status == "doing"
            assert task.is_done is False
            assert first_completion is not None

    def test_task_invalid_status_raises(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            task = Task(user_id=user_id, title="Inválida")
            with pytest.raises(ValueError):
                task.move_to("arquivada")

    def test_task_helpers(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            task = Task(
                user_id=user_id,
                title="Relatório",
                tags="Trabalho, foco, Trabalho ,,",
                priority="urgent",
                estimate_pomodoros=3,
                due_date=date.today() - timedelta(days=1),
            )
            db.session.add(task)
            db.session.commit()

            assert task.tag_list == ["Trabalho", "foco", "Trabalho"]
            assert task.priority_rank == 0
            assert task.is_overdue is True
            assert task.progress_percent == 0

            task.completed_pomodoros = 2
            assert task.progress_percent == 67

            task.completed_pomodoros = 99
            assert task.progress_percent == 100

    def test_record_focus_cycle_increments_task_only_for_focus(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            user = db.session.get(User, user_id)
            task = Task(user_id=user_id, title="Deep work", estimate_pomodoros=4)
            db.session.add(task)
            db.session.commit()

            focus = record_cycle(user, "focus", task.id, 25)
            assert focus.completed is True
            assert focus.duration_minutes == 25
            assert focus.task_id == task.id
            assert task.completed_pomodoros == 1

            short = record_cycle(user, "short_break", task.id, 5)
            assert short.mode == "short_break"
            assert task.completed_pomodoros == 1

            long = record_cycle(user, "long_break", None, 15)
            assert long.task_id is None
            assert task.completed_pomodoros == 1

    def test_record_cycle_validations(self, app, make_user):
        alice_id = make_user("alice")
        bob_id = make_user("bob")
        with app.app_context():
            alice = db.session.get(User, alice_id)
            bob_task = Task(user_id=bob_id, title="Do Bob")
            db.session.add(bob_task)
            db.session.commit()

            with pytest.raises(InvalidCycle):
                record_cycle(alice, "modo_estranho", None, 25)
            with pytest.raises(InvalidCycle):
                record_cycle(alice, "focus", None, 999)
            with pytest.raises(InvalidCycle):
                record_cycle(alice, "focus", None, 0)
            with pytest.raises(TaskNotFound):
                record_cycle(alice, "focus", bob_task.id, 25)

    def test_task_method_fields_and_labels(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            task = Task(
                user_id=user_id,
                title="Estudar para a prova",
                category="study",
                quadrant="schedule",
                is_mit=True,
                planned_for=date.today(),
                estimate_pomodoros=1,
            )
            db.session.add(task)
            db.session.commit()
            assert task.category_label == "Estudos"
            assert task.category_icon == "bi-mortarboard"
            assert task.quadrant_label == "Agendar"
            assert task.is_quick_win is True
            assert task.is_planned_today is True
            exported = task.to_export_dict()
            assert exported["category"] == "study"
            assert exported["quadrant"] == "schedule"
            assert exported["is_mit"] is True
            assert exported["planned_for"] == date.today().isoformat()

    def test_focus_stats_aggregation(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            user = db.session.get(User, user_id)
            record_cycle(user, "focus", None, 25)
            record_cycle(user, "focus", None, 25)
            record_cycle(user, "short_break", None, 5)

            stats = focus_stats(user, days=7)
            assert stats["today"]["cycles"] == 2
            assert stats["today"]["minutes"] == 50
            assert stats["today"]["label"] == "50m"
            assert len(stats["daily"]) == 7
            assert stats["streak"] >= 1
            assert stats["week"]["cycles"] == 2


# ==========================================================================
# AUTENTICAÇÃO E SESSÃO
# ==========================================================================
class TestAuth:
    def test_register_creates_user_and_authenticates(self, client, app):
        response = client.post(
            "/registrar",
            data={
                "display_name": "Nova",
                "username": "nova",
                "email": "nova@example.com",
                "password": "SenhaForte1!",
                "confirm": "SenhaForte1!",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Meu dia".encode() in response.data
        with app.app_context():
            user = User.query.filter_by(username="nova").one()
            assert user.display_name == "Nova"
            assert user.email == "nova@example.com"
            assert user.check_password("SenhaForte1!")

    def test_register_rejects_duplicate_username(self, client, make_user):
        make_user("alice")
        response = client.post(
            "/registrar",
            data={
                "display_name": "Outra Alice",
                "username": "alice",
                "email": "outra@example.com",
                "password": "SenhaForte1!",
                "confirm": "SenhaForte1!",
            },
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "já está em uso" in html

    def test_registration_can_be_disabled(self, client, app):
        app.config["ALLOW_REGISTRATION"] = False
        response = client.get("/registrar")
        assert response.status_code == 403
        assert "Acesso restrito" in response.get_data(as_text=True)

    def test_password_minimum_is_four_characters(self, client, app):
        short = client.post(
            "/registrar",
            data={
                "display_name": "Curta",
                "username": "curta",
                "email": "curta@example.com",
                "password": "123",
                "confirm": "123",
            },
        )
        assert short.status_code == 200
        assert "no mínimo 4 caracteres" in short.get_data(as_text=True)
        with app.app_context():
            assert User.query.filter_by(username="curta").first() is None

        accepted = client.post(
            "/registrar",
            data={
                "display_name": "Curta",
                "username": "curta",
                "email": "curta@example.com",
                "password": "1234",
                "confirm": "1234",
            },
            follow_redirects=True,
        )
        assert accepted.status_code == 200
        assert "Meu dia".encode() in accepted.data
        with app.app_context():
            user = User.query.filter_by(username="curta").one()
            assert user.check_password("1234") is True

    def test_new_account_enters_app_and_receives_tutorial_popup(self, client, app):
        response = client.post(
            "/registrar",
            data={
                "display_name": "Novata",
                "username": "novata",
                "email": "novata@example.com",
                "password": "1234",
                "confirm": "1234",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        html = dashboard.get_data(as_text=True)
        assert 'id="onboardingModal"' in html
        assert "Bem-vindo, Novata." in html
        assert "Planeje o essencial" in html
        assert "Regra 1-3-5" in html

        # A rota antiga abre o tutorial sobre o app, sem tirar a pessoa do fluxo.
        reentry = client.get("/bem-vindo", follow_redirects=False)
        assert reentry.status_code == 302
        assert "tour=1" in reentry.headers["Location"]

        # A ajuda pode ser consultada sem bloquear o app.
        help_page = client.get("/ajuda")
        assert help_page.status_code == 200
        assert "Matriz de prioridades" in help_page.get_data(as_text=True)

        finished = client.post(
            "/bem-vindo/concluir",
            json={},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert finished.status_code == 200
        assert finished.get_json()["ok"] is True
        with app.app_context():
            user = User.query.filter_by(username="novata").one()
            assert user.onboarding_completed is True

        assert 'id="onboardingModal"' not in client.get("/").get_data(as_text=True)

    def test_existing_account_does_not_see_tutorial_again(self, client, make_user):
        make_user()
        login(client)
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 200

    def test_help_page_explains_usage_and_concepts(self, client, make_user):
        make_user()
        login(client)
        response = client.get("/ajuda")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Como usar o ProdSuite" in html
        assert "Planejar o dia" in html
        assert "Matriz de prioridades" in html
        assert "Tarefas rápidas" in html
        assert "Pomodoro e pausas" in html
        assert "Dúvidas frequentes" in html

    def test_account_survives_logout_and_a_new_local_app(self, tmp_path):
        """O banco local não pode ser confundido com estado de sessão."""
        from app import create_app

        database = tmp_path / "local-persistence.db"
        config = {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-for-persistence",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
            "WTF_CSRF_ENABLED": False,
            "CREATE_DB_ON_START": True,
        }
        first_app = create_app(config)
        first_client = first_app.test_client()
        response = first_client.post(
            "/registrar",
            data={
                "display_name": "Persistente",
                "username": "persistente",
                "email": "persistente@example.com",
                "password": "1234",
                "confirm": "1234",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")
        with first_app.app_context():
            assert User.query.filter_by(username="persistente").count() == 1

        # Sair limpa a sessão, não a conta.
        assert first_client.post("/sair").status_code == 302
        with first_app.app_context():
            assert User.query.filter_by(username="persistente").count() == 1

        # Uma nova instância da aplicação, usando o mesmo arquivo, encontra a conta.
        second_app = create_app(config)
        second_client = second_app.test_client()
        login_response = second_client.post(
            "/entrar",
            data={"identifier": "persistente", "password": "1234"},
            follow_redirects=False,
        )
        assert login_response.status_code == 302
        assert login_response.headers["Location"].endswith("/")
        with second_app.app_context():
            user = User.query.filter_by(username="persistente").one()
            assert user.display_name == "Persistente"

    def test_login_and_logout(self, client, make_user):
        make_user()
        response = login(client)
        assert response.status_code == 200
        assert "Meu dia".encode() in response.data

        response = client.post("/sair", follow_redirects=True)
        assert response.status_code == 200
        assert "Você saiu".encode() in response.data
        assert client.get("/").status_code == 302

    def test_login_failure_does_not_reveal_user_existence(self, client, make_user):
        make_user()
        wrong_password = login(client, password="ErradaForte1!", follow_redirects=True)
        unknown_user = login(client, username="fantasma", follow_redirects=True)
        assert wrong_password.status_code == 200
        assert unknown_user.status_code == 200
        assert "inválidos" in wrong_password.get_data(as_text=True)
        assert "inválidos" in unknown_user.get_data(as_text=True)

    def test_protected_routes_redirect_anonymous(self, client):
        for path in ["/", "/tarefas", "/foco", "/rascunhos", "/notas", "/exportar"]:
            response = client.get(path)
            assert response.status_code == 302, path
            assert "/entrar" in response.headers["Location"], path

    def test_session_expires_after_inactivity(self, client, make_user):
        make_user()
        login(client)
        with client.session_transaction() as session:
            session["last_activity"] = time.time() - (31 * 60)
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/entrar" in response.headers["Location"]
        with client.session_transaction() as session:
            assert "_user_id" not in session
            assert "last_activity" not in session

    def test_session_nonce_revokes_old_session(self, client, make_user, app):
        user_id = make_user()
        login(client)
        assert client.get("/").status_code == 200

        with app.app_context():
            user = db.session.get(User, user_id)
            user.rotate_session_nonce()
            db.session.commit()

        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/entrar" in response.headers["Location"]

    def test_password_change_invalidates_other_sessions(self, app, make_user):
        make_user()
        first = app.test_client()
        second = app.test_client()
        login(first)
        login(second)
        assert first.get("/").status_code == 200
        assert second.get("/").status_code == 200

        response = first.post(
            "/perfil",
            data={
                "current_password": "SenhaForte1!",
                "new_password": "NovaSenhaForte2!",
                "confirm": "NovaSenhaForte2!",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert first.get("/").status_code == 200
        stale = second.get("/", follow_redirects=False)
        assert stale.status_code == 302
        assert "/entrar" in stale.headers["Location"]

    def test_login_rate_limit(self, client, make_user, app):
        make_user()
        app.config["LOGIN_ATTEMPT_LIMIT"] = 3
        for _ in range(3):
            login(client, password="ErradaForte1!", follow_redirects=False)
        blocked = login(client, password="SenhaForte1!", follow_redirects=False)
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

    def test_open_redirect_is_blocked(self, client, make_user):
        make_user()
        response = client.post(
            "/entrar?next=https://evil.example/steal",
            data={"identifier": "alice", "password": "SenhaForte1!"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/"


# ==========================================================================
# SEGURANÇA / CSRF / HEADERS
# ==========================================================================
class TestSecurity:
    def test_security_headers_present(self, client, make_user):
        make_user()
        login(client)
        response = client.get("/")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert "script-src 'self'" in response.headers["Content-Security-Policy"]
        assert "object-src 'none'" in response.headers["Content-Security-Policy"]
        assert response.headers["Referrer-Policy"] == "same-origin"

    def test_session_cookie_flags(self, client, make_user):
        make_user()
        response = login(client, follow_redirects=False)
        cookie = response.headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie
        assert "SameSite=Lax" in cookie

    def test_csrf_blocks_post_without_token(self, client, app, make_user):
        make_user()
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            response = client.post(
                "/entrar",
                data={"identifier": "alice", "password": "SenhaForte1!"},
            )
        finally:
            app.config["WTF_CSRF_ENABLED"] = False
        assert response.status_code == 400
        assert "sua página expirou" in response.get_data(as_text=True).lower()

    def test_csrf_blocks_json_cycle_without_token(self, client, app, make_user):
        make_user()
        login(client)
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            response = client.post(
                "/foco/ciclos",
                json={"mode": "focus", "duration_minutes": 25},
                headers={"Accept": "application/json"},
            )
        finally:
            app.config["WTF_CSRF_ENABLED"] = False
        assert response.status_code == 400
        assert response.is_json
        assert response.get_json()["ok"] is False


# ==========================================================================
# TAREFAS
# ==========================================================================
class TestTasks:
    def test_create_task_normalizes_tags_and_persists(self, client, app, make_user):
        make_user()
        login(client)
        response = client.post(
            "/tarefas",
            data={
                "title": "Escrever testes",
                "description": "Cobrir fluxos críticos",
                "status": "todo",
                "priority": "high",
                "estimate_pomodoros": "3",
                "due_date": "2026-11-05",
                "tags": "Dev, TESTES, dev",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            task = Task.query.filter_by(title="Escrever testes").one()
            assert task.tags == "dev, testes"
            assert task.tag_list == ["dev", "testes"]
            assert task.priority == "medium"
            assert task.estimate_pomodoros == 3
            assert task.due_date.isoformat() == "2026-11-05"

    def test_task_detail_shows_status_and_no_duplicate_priority_field(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.post(
            "/tarefas",
            data={
                "title": "Detalhe consistente",
                "status": "todo",
                "estimate_pomodoros": "1",
            },
        )
        with app.app_context():
            task_id = Task.query.filter_by(title="Detalhe consistente").one().id
        html = client.get(f"/tarefas/{task_id}/editar").get_data(as_text=True)
        assert "A fazer" in html
        assert 'name="priority"' not in html
        assert "Quadrante da matriz" in html

    def test_completed_task_does_not_offer_focus_button(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.post(
            "/tarefas",
            data={
                "title": "Concluída sem foco",
                "status": "todo",
                "estimate_pomodoros": "1",
            },
        )
        with app.app_context():
            task = Task.query.filter_by(title="Concluída sem foco").one()
            task.move_to("done")
            db.session.commit()
            task_id = task.id
        html = client.get(f"/tarefas/{task_id}/editar").get_data(as_text=True)
        assert "Reabra a tarefa para voltar a focar nela." in html
        assert "Começar foco nesta tarefa" not in html

    def test_create_task_defaults_deadline_to_creation_date(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.post(
            "/tarefas",
            data={
                "title": "Prazo de criação",
                "estimate_pomodoros": "1",
            },
            follow_redirects=True,
        )
        with app.app_context():
            task = Task.query.filter_by(title="Prazo de criação").one()
            assert task.due_date == date.today()

    def test_create_task_validation_error_keeps_modal(self, client, app, make_user):
        make_user()
        login(client)
        response = client.post(
            "/tarefas",
            data={
                "title": "",
                "status": "todo",
                "priority": "medium",
                "estimate_pomodoros": "1",
            },
        )
        assert response.status_code == 200
        assert 'data-auto-open="#taskModal"' in response.get_data(as_text=True)
        with app.app_context():
            assert Task.query.count() == 0

    def test_update_task_and_status(self, client, app, make_user):
        make_user()
        login(client)
        client.post(
            "/tarefas",
            data={
                "title": "Original",
                "status": "todo",
                "priority": "low",
                "estimate_pomodoros": "1",
            },
        )
        with app.app_context():
            task_id = Task.query.one().id

        response = client.post(
            f"/tarefas/{task_id}/editar",
            data={
                "title": "Atualizada",
                "description": "novo contexto",
                "status": "doing",
                "priority": "urgent",
                "estimate_pomodoros": "5",
                "due_date": "",
                "tags": "foco",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.title == "Atualizada"
            assert task.status == "doing"
            assert task.priority == "medium"
            assert task.estimate_pomodoros == 5

        response = client.post(
            f"/tarefas/{task_id}/status",
            json={"status": "done"},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["task"]["status"] == "done"
        assert payload["counts"]["done"] == 1
        with app.app_context():
            assert db.session.get(Task, task_id).completed_at is not None

    def test_custom_column_create_rename_and_reorder(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")

        response = client.post(
            "/tarefas/colunas",
            data={"title": "Ideias"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Ideias" in response.get_data(as_text=True)

        with app.app_context():
            column = BoardColumn.query.filter_by(title="Ideias").one()
            column_id = column.id
            assert column.kind == "todo"

        response = client.post(
            f"/tarefas/colunas/{column_id}/editar",
            data={"title": "Ideias soltas"},
            follow_redirects=True,
        )
        assert "Ideias soltas" in response.get_data(as_text=True)
        with app.app_context():
            column = db.session.get(BoardColumn, column_id)
            assert column.title == "Ideias soltas"
            assert column.kind == "todo"

        response = client.post(
            f"/tarefas/colunas/{column_id}/mover",
            data={"direction": "up"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            assert db.session.get(BoardColumn, column_id).position == 2

    def test_task_moves_between_columns_without_changing_completion(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.get("/tarefas")
        with app.app_context():
            todo_column = BoardColumn.query.filter_by(kind="todo").first()
            todo_column_id = todo_column.id

        client.post(
            "/tarefas",
            data={
                "title": "Entregar relatório",
                "priority": "high",
                "estimate_pomodoros": "2",
                "column_id": str(todo_column_id),
            },
        )
        client.post("/tarefas/colunas", data={"title": "Entregues"})

        with app.app_context():
            task = Task.query.filter_by(title="Entregar relatório").one()
            task_id = task.id
            done_column = BoardColumn.query.filter_by(title="Entregues").one()
            done_column_id = done_column.id

        response = client.post(
            f"/tarefas/{task_id}/coluna",
            json={"column_id": done_column_id},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert response.status_code == 200
        assert response.get_json()["task"]["column_id"] == done_column_id
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.column_id == done_column_id
            assert task.status == "todo"
            assert task.completed_at is None

        # Completion is a task action, not a column type.
        done = client.post(
            f"/tarefas/{task_id}/status",
            json={"status": "done"},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert done.status_code == 200
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.status == "done"
            assert task.completed_at is not None

    def test_delete_column_reassigns_its_tasks(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")
        client.post(
            "/tarefas/colunas",
            data={"title": "Temporária", "kind": "todo"},
        )
        with app.app_context():
            column = BoardColumn.query.filter_by(title="Temporária").one()
            column_id = column.id
            task = Task(
                user_id=db.session.get(User, 1).id,
                title="Tarefa temporária",
                column_id=column.id,
                status="todo",
            )
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        response = client.post(
            f"/tarefas/colunas/{column_id}/excluir",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Coluna removida" in response.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(BoardColumn, column_id) is None
            task = db.session.get(Task, task_id)
            assert task.column_id is not None
            assert task.column_id != column_id

    def test_board_has_default_columns_and_assigns_existing_tasks(
        self, client, app, make_user
    ):
        user_id = make_user()
        with app.app_context():
            task = Task(user_id=user_id, title="Em andamento", status="doing")
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        login(client)
        response = client.get("/tarefas")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "A fazer" in html
        assert "Em andamento" in html
        assert "Concluídas" in html
        with app.app_context():
            task = db.session.get(Task, task_id)
            column = db.session.get(BoardColumn, task.column_id)
            assert column.kind == "doing"

    def test_custom_category_create_rename_and_filter(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")

        response = client.post(
            "/tarefas/categorias",
            data={"name": "Saúde", "icon": "bi-heart"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Saúde" in response.get_data(as_text=True)
        with app.app_context():
            category = Category.query.filter_by(name="Saúde").one()
            category_id = category.id
            category_key = category.key
            assert category.icon == "bi-heart"

        response = client.post(
            f"/tarefas/categorias/{category_id}/editar",
            data={"name": "Bem-estar", "icon": "bi-activity"},
            follow_redirects=True,
        )
        assert "Bem-estar" in response.get_data(as_text=True)
        with app.app_context():
            category = db.session.get(Category, category_id)
            assert category.name == "Bem-estar"
            assert category.icon == "bi-activity"

        response = client.post(
            "/tarefas",
            data={
                "title": "Caminhar 30 minutos",
                "priority": "medium",
                "estimate_pomodoros": "1",
                "category": category_key,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        filtered = client.get(f"/tarefas?categoria={category_key}")
        html = filtered.get_data(as_text=True)
        assert "Caminhar 30 minutos" in html
        assert "Bem-estar" in html

    def test_delete_category_reassigns_its_tasks(self, client, app, make_user):
        user_id = make_user()
        login(client)
        client.get("/tarefas")
        client.post(
            "/tarefas/categorias",
            data={"name": "Temporária", "icon": "bi-star"},
        )
        with app.app_context():
            category = Category.query.filter_by(name="Temporária").one()
            category_id = category.id
            category_key = category.key
            task = Task(
                user_id=user_id,
                title="Tarefa da categoria",
                category=category_key,
            )
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        response = client.post(
            f"/tarefas/categorias/{category_id}/excluir",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Categoria removida" in response.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(Category, category_id) is None
            task = db.session.get(Task, task_id)
            assert task.category != category_key
            assert Category.query.filter_by(key=task.category).one()

    def test_category_labels_reach_weekly_metrics(self, app, make_user):
        user_id = make_user()
        with app.app_context():
            user = db.session.get(User, user_id)
            categories = ensure_categories(user)
            category = Category(
                user_id=user.id,
                key="custom-health",
                name="Saúde",
                icon="bi-heart",
                position=len(categories),
            )
            db.session.add(category)
            task = Task(
                user_id=user.id,
                title="Consulta",
                status="done",
                category=category.key,
                completed_at=utcnow(),
            )
            db.session.add(task)
            db.session.commit()
            metrics = weekly_metrics(user)
            item = next(
                entry for entry in metrics["categories"] if entry["key"] == "custom-health"
            )
            assert item["label"] == "Saúde"
            assert item["icon"] == "bi-heart"
            assert item["tasks"] == 1

    def test_create_blank_project_and_its_own_columns(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")

        response = client.post(
            "/tarefas/quadros",
            data={"name": "Projeto novo"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Projeto novo" in html
        assert "Nova coluna" in html
        assert 'class="kanban-col"' not in html
        with app.app_context():
            project = Project.query.filter_by(name="Projeto novo").one()
            project_id = project.id
            assert BoardColumn.query.filter_by(project_id=project.id).count() == 0

        response = client.post(
            "/tarefas/colunas",
            data={"project_id": str(project_id), "title": "Ideias"},
            follow_redirects=True,
        )
        assert "Ideias" in response.get_data(as_text=True)
        with app.app_context():
            column = BoardColumn.query.filter_by(
                project_id=project_id, title="Ideias"
            ).one()
            column_id = column.id

        response = client.post(
            "/tarefas",
            data={
                "title": "Rascunhar o projeto",
                "priority": "medium",
                "estimate_pomodoros": "1",
                "column_id": str(column_id),
            },
            follow_redirects=True,
        )
        assert "Rascunhar o projeto" in response.get_data(as_text=True)
        with app.app_context():
            task = Task.query.filter_by(title="Rascunhar o projeto").one()
            assert task.project_id == project_id
            assert task.column_id == column_id

    def test_second_project_does_not_show_tasks_from_another(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")
        client.post(
            "/tarefas",
            data={
                "title": "Tarefa do quadro padrão",
                "priority": "medium",
                "estimate_pomodoros": "1",
            },
            follow_redirects=True,
        )
        client.post("/tarefas/quadros", data={"name": "Outro quadro"})
        response = client.get("/tarefas")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Outro quadro" in html
        assert "Tarefa do quadro padrão</a>" not in html

    def test_deleting_project_moves_or_removes_its_tasks(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.get("/tarefas")
        client.post("/tarefas/quadros", data={"name": "Com tarefas"})
        with app.app_context():
            project = Project.query.filter_by(name="Com tarefas").one()
            project_id = project.id
            task = Task(
                user_id=db.session.get(User, 1).id,
                title="Não posso perder",
                project_id=project.id,
            )
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        response = client.post(
            f"/tarefas/quadros/{project_id}/excluir",
            follow_redirects=True,
        )
        assert "tarefas foram movidas" in response.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(Project, project_id) is None
            task = db.session.get(Task, task_id)
            assert task is not None
            assert task.project_id is not None
            assert task.column_id is not None

    def test_new_account_starts_with_a_completely_blank_project(
        self, client, app
    ):
        response = client.post(
            "/registrar",
            data={
                "display_name": "Nova",
                "username": "nova.projeto",
                "email": "nova.projeto@example.com",
                "password": "1234",
                "confirm": "1234",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        client.post("/bem-vindo/concluir", json={})

        tasks = client.get("/tarefas")
        html = tasks.get_data(as_text=True)
        assert "Crie seu primeiro projeto" in html
        assert 'class="kanban-col"' not in html
        assert "Criar projeto" in html

        client.post("/tarefas/quadros", data={"name": "Meu projeto"})
        project_page = client.get("/tarefas")
        project_html = project_page.get_data(as_text=True)
        assert "Meu projeto" in project_html
        assert "Nova coluna" in project_html
        assert "Todo, Doing, Validation, Block, Done" not in project_html
        assert "Tipo" not in project_html
        with app.app_context():
            project = Project.query.filter_by(name="Meu projeto").one()
            assert BoardColumn.query.filter_by(project_id=project.id).count() == 0

    def test_project_can_be_renamed_and_removed(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")
        client.post("/tarefas/quadros", data={"name": "Estudos"})
        with app.app_context():
            project = Project.query.filter_by(name="Estudos").one()
            project_id = project.id

        response = client.post(
            f"/tarefas/quadros/{project_id}/editar",
            data={"name": "Estudos e leituras"},
            follow_redirects=True,
        )
        assert "Estudos e leituras" in response.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(Project, project_id).name == "Estudos e leituras"

        response = client.post(
            f"/tarefas/quadros/{project_id}/excluir",
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            assert db.session.get(Project, project_id) is None

    def test_done_column_completes_task_and_records_column_time(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.get("/tarefas")
        client.post("/tarefas/quadros", data={"name": "Fluxo de conclusão"})
        client.post("/tarefas/colunas", data={"title": "Todo"})
        client.post(
            "/tarefas/colunas",
            data={"title": "Done", "is_done": "y"},
        )
        with app.app_context():
            done_column = BoardColumn.query.filter_by(title="Done").one()
            done_column_id = done_column.id
            todo_column = BoardColumn.query.filter_by(title="Todo").one()
            todo_column_id = todo_column.id

        client.post(
            "/tarefas",
            data={
                "title": "Fechar KR",
                "priority": "high",
                "estimate_pomodoros": "1",
                "column_id": str(todo_column_id),
            },
        )
        with app.app_context():
            task = Task.query.filter_by(title="Fechar KR").one()
            task_id = task.id
            task.column_entered_at = utcnow() - timedelta(minutes=90)
            db.session.commit()

        moved = client.post(
            f"/tarefas/{task_id}/coluna",
            json={"column_id": done_column_id},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert moved.status_code == 200
        payload = moved.get_json()
        assert payload["task"]["column_id"] == done_column_id
        assert payload["task"]["status"] == "done"
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.status == "done"
            assert task.completed_at is not None
            stay = TaskColumnStay.query.filter_by(task_id=task_id).one()
            assert stay.column_title == "Todo"
            assert stay.duration_seconds >= 89 * 60

        reopened = client.post(
            f"/tarefas/{task_id}/coluna",
            json={"column_id": todo_column_id},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert reopened.status_code == 200
        assert reopened.get_json()["task"]["status"] == "todo"
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.status == "todo"
            assert task.completed_at is None

    def test_only_one_completion_column_per_project(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")
        client.post("/tarefas/quadros", data={"name": "Um done só"})
        client.post("/tarefas/colunas", data={"title": "Done", "is_done": "y"})
        response = client.post(
            "/tarefas/colunas",
            data={"title": "Também Done", "is_done": "y"},
            follow_redirects=True,
        )
        assert "já tem uma coluna de conclusão" in response.get_data(as_text=True)
        with app.app_context():
            assert BoardColumn.query.filter_by(
                title="Também Done", kind="done"
            ).first() is None

    def test_task_page_shows_column_time(self, client, app, make_user):
        make_user()
        login(client)
        client.get("/tarefas")
        client.post("/tarefas/quadros", data={"name": "Tempo de fluxo"})
        client.post("/tarefas/colunas", data={"title": "Todo"})
        client.post("/tarefas/colunas", data={"title": "Done", "is_done": "y"})
        with app.app_context():
            done_column = BoardColumn.query.filter_by(title="Done").one()
            done_column_id = done_column.id
            todo_column = BoardColumn.query.filter_by(title="Todo").one()
            todo_column_id = todo_column.id

        client.post(
            "/tarefas",
            data={
                "title": "Tempo de KR",
                "priority": "medium",
                "estimate_pomodoros": "1",
                "column_id": str(todo_column_id),
            },
        )
        with app.app_context():
            task = Task.query.filter_by(title="Tempo de KR").one()
            task_id = task.id
            task.column_entered_at = utcnow() - timedelta(minutes=30)
            db.session.commit()
        client.post(
            f"/tarefas/{task_id}/coluna",
            json={"column_id": done_column_id},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        page = client.get(f"/tarefas/{task_id}/editar").get_data(as_text=True)
        assert "Tempo por coluna" in page
        assert "Todo" in page
        assert "30 min" in page

    def test_task_filters_match_their_labels(self, client, app, make_user):
        user_id = make_user()
        login(client)
        client.get("/tarefas")
        with app.app_context():
            project = Project.query.filter_by(name="Projeto de teste").one()
            column = BoardColumn.query.filter_by(
                project_id=project.id, kind="todo"
            ).first()
            tasks = [
                Task(
                    user_id=user_id,
                    project_id=project.id,
                    column_id=column.id,
                    title="Vence hoje",
                    due_date=date.today(),
                    status="todo",
                    estimate_pomodoros=2,
                ),
                Task(
                    user_id=user_id,
                    project_id=project.id,
                    column_id=column.id,
                    title="Vence amanhã",
                    due_date=date.today() + timedelta(days=1),
                    status="todo",
                    estimate_pomodoros=2,
                ),
                Task(
                    user_id=user_id,
                    project_id=project.id,
                    column_id=column.id,
                    title="Prioridade marcada",
                    is_mit=True,
                    status="todo",
                    estimate_pomodoros=3,
                ),
                Task(
                    user_id=user_id,
                    project_id=project.id,
                    column_id=column.id,
                    title="Tarefa rápida",
                    status="todo",
                    estimate_pomodoros=1,
                ),
                Task(
                    user_id=user_id,
                    project_id=project.id,
                    column_id=column.id,
                    title="Hoje já concluída",
                    due_date=date.today(),
                    status="done",
                ),
            ]
            db.session.add_all(tasks)
            db.session.commit()
            priority_id = next(
                task.id for task in tasks if task.title == "Prioridade marcada"
            )

        def card_titles(path):
            html = client.get(path).get_data(as_text=True)
            return {
                title
                for title in [
                    "Vence hoje",
                    "Vence amanhã",
                    "Prioridade marcada",
                    "Tarefa rápida",
                    "Hoje já concluída",
                ]
                if f">{title}</a>" in html
            }

        assert card_titles("/tarefas?filtro=hoje") == {"Vence hoje"}
        assert card_titles("/tarefas?filtro=mit") == {"Prioridade marcada"}
        assert card_titles("/tarefas?filtro=rapidas") == {"Tarefa rápida"}

        # A estrela do card alterna a prioridade do dia.
        client.post(
            f"/tarefas/{priority_id}/prioridade",
            data={"next": "/tarefas?filtro=mit"},
            follow_redirects=True,
        )
        with app.app_context():
            assert db.session.get(Task, priority_id).is_mit is False

    def test_status_invalid_is_rejected(self, client, app, make_user):
        make_user()
        login(client)
        client.post(
            "/tarefas",
            data={
                "title": "X",
                "status": "todo",
                "priority": "low",
                "estimate_pomodoros": "1",
            },
        )
        with app.app_context():
            task_id = Task.query.one().id
        response = client.post(
            f"/tarefas/{task_id}/status",
            json={"status": "arquivada"},
            headers={"X-Requested-With": "fetch"},
        )
        assert response.status_code == 400

    def test_user_cannot_access_other_users_task(self, client, app, make_user):
        make_user("alice")
        bob_id = make_user("bob")
        with app.app_context():
            task = Task(user_id=bob_id, title="Privada")
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        login(client, "alice")
        assert client.get(f"/tarefas/{task_id}/editar").status_code == 404
        response = client.post(
            f"/tarefas/{task_id}/status",
            json={"status": "done"},
            headers={"X-Requested-With": "fetch"},
        )
        assert response.status_code == 404

    def test_delete_task_unlinks_cycle_and_scratchpad(self, client, app, make_user):
        user_id = make_user()
        with app.app_context():
            task = Task(user_id=user_id, title="Temporária")
            db.session.add(task)
            db.session.flush()
            scratch = Scratchpad(
                user_id=user_id, content="nota", converted_task_id=task.id
            )
            cycle = PomodoroCycle(
                user_id=user_id,
                task_id=task.id,
                mode="focus",
                duration_minutes=25,
                started_at=utcnow(),
                ended_at=utcnow(),
            )
            db.session.add_all([scratch, cycle])
            db.session.commit()
            task_id, cycle_id, scratch_id = task.id, cycle.id, scratch.id

        login(client)
        response = client.post(f"/tarefas/{task_id}/excluir", follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            assert db.session.get(Task, task_id) is None
            assert db.session.get(PomodoroCycle, cycle_id).task_id is None
            assert db.session.get(Scratchpad, scratch_id).converted_task_id is None


# ==========================================================================
# CAPTURA RÁPIDA
# ==========================================================================
class TestScratchpad:
    def test_ajax_capture_returns_json(self, client, app, make_user):
        make_user()
        login(client)
        response = client.post(
            "/rascunhos",
            data={"content": "Ideia bruta"},
            headers={
                "X-Requested-With": "fetch",
                "Accept": "application/json",
            },
        )
        assert response.status_code == 201
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["scratchpad"]["content"] == "Ideia bruta"
        with app.app_context():
            assert Scratchpad.query.count() == 1

    def test_empty_capture_is_rejected(self, client, make_user):
        make_user()
        login(client)
        response = client.post(
            "/rascunhos",
            data={"content": "   "},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert response.status_code == 400
        assert response.get_json()["ok"] is False

    def test_scratchpad_detail_can_be_edited_and_uses_task_form(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.post("/rascunhos", data={"content": "Texto original"})
        with app.app_context():
            item_id = Scratchpad.query.one().id

        detail = client.get(f"/rascunhos/{item_id}")
        assert detail.status_code == 200
        html = detail.get_data(as_text=True)
        assert "Texto original" in html
        assert "Transformar em tarefa" in html
        assert "Quadrante da matriz" in html
        assert "Prazo final" in html
        assert "Sessões de foco (estimativa)" in html
        assert "Etiquetas" in html

        saved = client.post(
            f"/rascunhos/{item_id}/editar",
            data={"content": "Texto revisado"},
            follow_redirects=True,
        )
        assert saved.status_code == 200
        assert "Texto revisado" in saved.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(Scratchpad, item_id).content == "Texto revisado"

    def test_convert_scratchpad_to_task(self, client, app, make_user):
        make_user()
        login(client)
        client.post("/rascunhos", data={"content": "Comprar cafe"})
        with app.app_context():
            item_id = Scratchpad.query.one().id

        response = client.post(
            f"/rascunhos/{item_id}/converter",
            data={
                "title": "Comprar café",
                "priority": "high",
                "estimate_pomodoros": "2",
                "keep_note": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Scratchpad, item_id) is None
            task = Task.query.filter_by(title="Comprar café").one()
            assert task.description == "Comprar cafe"

        again = client.post(
            f"/rascunhos/{item_id}/converter",
            data={"title": "Outra", "priority": "low", "estimate_pomodoros": "1"},
        )
        assert again.status_code == 404

    def test_other_user_cannot_convert_scratchpad(self, client, app, make_user):
        make_user("alice")
        bob_id = make_user("bob")
        with app.app_context():
            item = Scratchpad(user_id=bob_id, content="segredo")
            db.session.add(item)
            db.session.commit()
            item_id = item.id
        login(client, "alice")
        response = client.post(
            f"/rascunhos/{item_id}/converter",
            data={"title": "x", "priority": "low", "estimate_pomodoros": "1"},
        )
        assert response.status_code == 404


# ==========================================================================
# NOTAS / MARKDOWN / BUSCA
# ==========================================================================
class TestNotes:
    def test_note_renders_markdown_and_wiki_links(self, client, app, make_user):
        make_user()
        login(client)
        client.post(
            "/notas/nova",
            data={"title": "Nota B", "body": "Conteúdo B", "tags": ""},
        )
        with app.app_context():
            note_b = Note.query.filter_by(title="Nota B").one()
            note_b_id = note_b.id

        response = client.post(
            "/notas/nova",
            data={
                "title": "Nota A",
                "body": "# Título\n\nVeja [[Nota B]], **negrito** e [globo](https://globo.com).",
                "tags": "pkm",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "<h1>Título</h1>" in html
        assert "<strong>negrito</strong>" in html
        assert f'href="/notas/{note_b_id}"' in html
        assert 'href="https://globo.com"' in html
        assert 'target="_blank"' in html
        assert 'rel="noopener noreferrer"' in html

    def test_markdown_sanitizes_xss(self, client, app, make_user):
        make_user()
        login(client)
        client.post(
            "/notas/nova",
            data={
                "title": "XSS",
                "body": (
                    '<script>alert("xss")</script>'
                    '<img src=x onerror="alert(1)">'
                    "[link](javascript:alert(1))"
                ),
                "tags": "",
            },
        )
        with app.app_context():
            note_id = Note.query.one().id
        html = client.get(f"/notas/{note_id}").get_data(as_text=True)
        assert "<script>alert" not in html
        assert "<img src=x" not in html
        assert "javascript:" not in html
        assert "onerror" not in html

    def test_duplicate_note_title_is_rejected(self, client, app, make_user):
        make_user()
        login(client)
        payload = {"title": "Mesmo título", "body": "A", "tags": ""}
        client.post("/notas/nova", data=payload)
        response = client.post(
            "/notas/nova", data={**payload, "body": "B"}, follow_redirects=True
        )
        assert "ambíguos" in response.get_data(as_text=True)
        with app.app_context():
            assert Note.query.count() == 1

    def test_preview_is_sanitized_and_requires_auth(self, app, make_user):
        make_user()
        anonymous = app.test_client()
        assert anonymous.post("/notas/preview", json={"body": "x"}).status_code == 401

        client = app.test_client()
        login(client)
        response = client.post(
            "/notas/preview",
            json={"body": "<script>alert(1)</script>**ok**"},
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert "<script>" not in payload["html"]
        assert "<strong>ok</strong>" in payload["html"]

    def test_search_finds_and_isolates_users(self, client, app, make_user):
        make_user("alice")
        bob_id = make_user("bob")
        with app.app_context():
            db.session.add(
                Task(user_id=bob_id, title="Projeto secreto do bob")
            )
            db.session.commit()

        login(client, "alice")
        client.post(
            "/tarefas",
            data={
                "title": "Projeto Alpha",
                "description": "documento alfa",
                "status": "todo",
                "priority": "medium",
                "estimate_pomodoros": "1",
            },
        )
        response = client.get("/busca?q=Alpha")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Projeto Alpha" in html
        assert "secreto do bob" not in html


# ==========================================================================
# MÉTODO: PLANEJAMENTO, MIT, 1-3-5 E REVISÃO
# ==========================================================================
class TestPlanning:
    def _add_task(self, app, user_id, title, **kwargs):
        with app.app_context():
            task = Task(user_id=user_id, title=title, **kwargs)
            db.session.add(task)
            db.session.commit()
            return task.id

    def test_planner_shows_methods(self, client, app, make_user):
        user_id = make_user()
        self._add_task(
            app,
            user_id,
            "Prioridade da semana",
            category="study",
            quadrant="schedule",
            is_mit=True,
            planned_for=date.today(),
            estimate_pomodoros=3,
            priority="high",
        )
        self._add_task(
            app,
            user_id,
            "Responder e-mail",
            category="work",
            quadrant="do",
            estimate_pomodoros=1,
        )
        login(client)
        html = client.get("/planejar").get_data(as_text=True)
        assert "Prioridades do dia" in html
        assert "Matriz de prioridades" in html
        assert "Tarefas rápidas" in html
        assert "Blocos de hoje" in html
        assert "Fazer agora" in html
        assert "Agendar" in html
        assert "Prioridade da semana" in html
        assert "Responder e-mail" in html

    def test_weekly_goal_update(self, client, app, make_user):
        user_id = make_user()
        login(client)
        response = client.post(
            "/planejar/meta",
            data={"weekly_focus_goal": "20"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            assert db.session.get(User, user_id).weekly_focus_goal == 20

    def test_mit_limit_of_three(self, client, app, make_user):
        user_id = make_user()
        first = self._add_task(app, user_id, "MIT 1", is_mit=True)
        second = self._add_task(app, user_id, "MIT 2", is_mit=True)
        third = self._add_task(app, user_id, "MIT 3", is_mit=True)
        fourth = self._add_task(app, user_id, "MIT 4")
        login(client)
        response = client.post(
            f"/tarefas/{fourth}/prioridade", follow_redirects=True
        )
        assert response.status_code == 200
        assert "3 prioridades" in response.get_data(as_text=True)
        with app.app_context():
            assert sum(
                1
                for task_id in (first, second, third, fourth)
                if db.session.get(Task, task_id).is_mit
            ) == 3

    def test_plan_today_toggle(self, client, app, make_user):
        user_id = make_user()
        task_id = self._add_task(app, user_id, "Tarefa para hoje")
        login(client)
        client.post(
            f"/tarefas/{task_id}/planejar",
            data={"next": "/planejar"},
            follow_redirects=True,
        )
        with app.app_context():
            assert db.session.get(Task, task_id).planned_for == date.today()
        client.post(
            f"/tarefas/{task_id}/planejar",
            data={"next": "/planejar"},
            follow_redirects=True,
        )
        with app.app_context():
            assert db.session.get(Task, task_id).planned_for is None

    def test_task_creation_with_method_fields(self, client, app, make_user):
        make_user()
        login(client)
        response = client.post(
            "/tarefas",
            data={
                "title": "Estudar cálculo",
                "description": "",
                "status": "todo",
                "priority": "high",
                "estimate_pomodoros": "2",
                "category": "study",
                "quadrant": "schedule",
                "is_mit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            task = Task.query.filter_by(title="Estudar cálculo").one()
            assert task.category == "study"
            assert task.quadrant == "schedule"
            assert task.is_mit is True
            assert task.planned_for is None

    def test_moving_to_completion_column_does_not_archive_immediately(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        client.get("/tarefas")
        with app.app_context():
            done_column = BoardColumn.query.filter_by(kind="done").first()
            done_id = done_column.id
            todo = BoardColumn.query.filter_by(kind="todo").first()
            todo_id = todo.id
        client.post(
            "/tarefas",
            data={
                "title": "Arquivar ao concluir",
                "estimate_pomodoros": "1",
                "column_id": str(todo_id),
            },
        )
        with app.app_context():
            task = Task.query.filter_by(title="Arquivar ao concluir").one()
            task_id = task.id
        response = client.post(
            f"/tarefas/{task_id}/coluna",
            json={"column_id": done_id},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        assert response.status_code == 200
        payload = response.get_json()["task"]
        assert payload["status"] == "done"
        assert payload["is_archived"] is False
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.archived_at is None
            assert task.archived_week is None
        board = client.get("/tarefas").get_data(as_text=True)
        assert "Arquivar ao concluir" in board
        archive = client.get("/tarefas/arquivadas").get_data(as_text=True)
        assert "Arquivar ao concluir" not in archive

    def test_completed_week_can_be_archived_and_restored(
        self, client, app, make_user
    ):
        user_id = make_user()
        login(client)
        with app.app_context():
            project = Project.query.filter_by(name="Projeto de teste").one()
            column = BoardColumn.query.filter_by(
                project_id=project.id, kind="done"
            ).first()
            task = Task(
                user_id=user_id,
                project_id=project.id,
                column_id=column.id,
                title="Concluída para arquivar",
                status="done",
                completed_at=utcnow(),
                estimate_pomodoros=1,
            )
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        response = client.post("/revisao/arquivar", follow_redirects=True)
        assert response.status_code == 200
        assert "arquivada" in response.get_data(as_text=True)
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.archived_at is not None
            assert task.archived_week is not None

        board = client.get("/tarefas").get_data(as_text=True)
        assert "Concluída para arquivar" not in board
        archive = client.get("/tarefas/arquivadas").get_data(as_text=True)
        assert "Concluída para arquivar" in archive
        assert "Restaurar" in archive

        restored = client.post(
            f"/tarefas/{task_id}/restaurar", follow_redirects=True
        )
        assert restored.status_code == 200
        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.archived_at is None
            assert task.archived_week is None

    def test_review_lists_ended_weeks(self, client, make_user):
        make_user()
        login(client)
        response = client.get("/revisao/semanas")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Semanas encerradas" in html
        assert "/revisao?semana=" in html

    def test_dashboard_prompts_for_previous_week_review(
        self, client, app, make_user
    ):
        from services.planning import week_start_for
        from services.timeutils import day_start_utc

        user_id = make_user()
        login(client)
        previous_start = week_start_for(date.today()) - timedelta(days=7)
        with app.app_context():
            project = Project.query.filter_by(name="Projeto de teste").one()
            column = BoardColumn.query.filter_by(
                project_id=project.id, kind="done"
            ).first()
            task = Task(
                user_id=user_id,
                project_id=project.id,
                column_id=column.id,
                title="Progresso da semana passada",
                status="done",
                completed_at=day_start_utc(previous_start + timedelta(days=1)),
                estimate_pomodoros=1,
            )
            db.session.add(task)
            db.session.commit()

        dashboard = client.get("/").get_data(as_text=True)
        assert "A semana passada terminou" in dashboard
        assert f"semana={previous_start.isoformat()}" in dashboard

        review = client.get(
            f"/revisao?semana={previous_start.isoformat()}"
        ).get_data(as_text=True)
        assert "semana encerrada" in review
        assert "Progresso da semana passada" in review
        assert "somente para leitura" in review
        assert "Escrever revisão" not in review
        assert "Editar" not in review

        client.post(
            f"/revisao?semana={previous_start.isoformat()}",
            data={
                "wins": "Tentativa indevida",
                "challenges": "Foi corrida",
                "next_steps": "Proteger a manhã",
            },
        )
        with app.app_context():
            assert WeeklyReview.query.count() == 0
        dashboard_after = client.get("/").get_data(as_text=True)
        assert "A semana passada terminou" in dashboard_after

    def test_weekly_review_is_read_only_until_edit_is_requested(
        self, client, app, make_user
    ):
        make_user()
        login(client)
        page = client.get("/revisao").get_data(as_text=True)
        assert "Você ainda não escreveu a revisão desta semana." in page
        assert 'name="wins"' not in page

        client.post(
            "/revisao",
            data={
                "wins": "Entreguei o KR",
                "challenges": "Semana cheia",
                "next_steps": "Proteger a manhã",
            },
        )
        read_page = client.get("/revisao").get_data(as_text=True)
        assert "Entreguei o KR" in read_page
        assert "Semana cheia" in read_page
        assert "Proteger a manhã" in read_page
        assert 'name="wins"' not in read_page
        assert "Editar" in read_page

        edit_page = client.get("/revisao?editar=1").get_data(as_text=True)
        assert 'name="wins"' in edit_page
        assert "Entreguei o KR" in edit_page
        assert "Cancelar" in edit_page

    def test_weekly_review_lists_tasks_completed_this_week(
        self, client, app, make_user
    ):
        user_id = make_user()
        login(client)
        with app.app_context():
            project = Project.query.filter_by(name="Projeto de teste").one()
            column = BoardColumn.query.filter_by(
                project_id=project.id, kind="done"
            ).first()
            task = Task(
                user_id=user_id,
                project_id=project.id,
                column_id=column.id,
                title="KR concluído na semana",
                status="done",
                completed_at=utcnow(),
                estimate_pomodoros=1,
            )
            db.session.add(task)
            db.session.commit()
        page = client.get("/revisao").get_data(as_text=True)
        assert "KR concluído na semana" in page
        assert "O que ficou pronto" in page
        assert "Ainda não há tarefas concluídas" not in page

    def test_legacy_done_column_is_migrated_only_once(self, tmp_path):
        from app import create_app, ensure_schema
        from sqlalchemy import text

        application = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'legacy.db'}",
                "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",
                "CREATE_DB_ON_START": True,
            }
        )
        with application.app_context():
            db.drop_all()
            db.create_all()
            user = User(
                username="legacy",
                display_name="Legacy",
                email="legacy@example.com",
                legacy_done_migrated=False,
            )
            user.set_password("SenhaForte1!")
            db.session.add(user)
            db.session.commit()
            project = Project(user_id=user.id, name="Quadro antigo", position=0)
            db.session.add(project)
            db.session.flush()
            column = BoardColumn(
                user_id=user.id,
                project_id=project.id,
                title="Done",
                kind="todo",
                position=0,
            )
            db.session.add(column)
            db.session.flush()
            task = Task(
                user_id=user.id,
                project_id=project.id,
                column_id=column.id,
                title="Tarefa antiga concluída",
                status="todo",
                estimate_pomodoros=1,
            )
            db.session.add(task)
            db.session.commit()
            column_id = column.id
            task_id = task.id

            ensure_schema()
            db.session.expire_all()
            column = db.session.get(BoardColumn, column_id)
            task = db.session.get(Task, task_id)
            assert column.kind == "done"
            assert task.status == "done"
            assert task.completed_at is not None
            assert db.session.get(User, user.id).legacy_done_migrated is True

            column.kind = "todo"
            task.move_to("todo")
            db.session.commit()
            ensure_schema()
            db.session.expire_all()
            assert db.session.get(BoardColumn, column_id).kind == "todo"
            assert db.session.get(Task, task_id).status == "todo"
            db.session.remove()
            db.drop_all()

    def test_weekly_review_saves_and_updates(self, client, app, make_user):
        make_user()
        login(client)
        first = client.post(
            "/revisao",
            data={
                "wins": "Consegui terminar o relatório",
                "challenges": "Reuniões demais",
                "next_steps": "Proteger a manhã",
            },
            follow_redirects=True,
        )
        assert first.status_code == 200
        assert "Revisão da semana salva" in first.get_data(as_text=True)

        second = client.post(
            "/revisao",
            data={
                "wins": "Atualizado",
                "challenges": "",
                "next_steps": "",
            },
            follow_redirects=True,
        )
        assert second.status_code == 200
        with app.app_context():
            reviews = WeeklyReview.query.all()
            assert len(reviews) == 1
            assert reviews[0].wins == "Atualizado"


# ==========================================================================
# POMODORO API
# ==========================================================================
class TestPomodoroAPI:
    def test_cycle_endpoint_records_focus_and_returns_stats(self, client, app, make_user):
        make_user()
        login(client)
        client.post(
            "/tarefas",
            data={
                "title": "Tarefa foco",
                "status": "todo",
                "priority": "high",
                "estimate_pomodoros": "4",
            },
        )
        with app.app_context():
            task_id = Task.query.one().id

        response = client.post(
            "/foco/ciclos",
            json={"mode": "focus", "task_id": task_id, "duration_minutes": 25},
        )
        assert response.status_code == 201
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["cycle"]["mode"] == "focus"
        assert payload["cycle"]["task_id"] == task_id
        assert payload["stats"]["today"]["cycles"] == 1
        assert payload["suggested_next"] == "short_break"
        with app.app_context():
            assert db.session.get(Task, task_id).completed_pomodoros == 1

    def test_fourth_focus_suggests_long_break(self, client, app, make_user):
        user_id = make_user()
        login(client)
        with app.app_context():
            user = db.session.get(User, user_id)
            for _ in range(3):
                record_cycle(user, "focus", None, 25)
        response = client.post(
            "/foco/ciclos", json={"mode": "focus", "duration_minutes": 25}
        )
        assert response.status_code == 201
        assert response.get_json()["suggested_next"] == "long_break"

    def test_invalid_cycle_returns_400(self, client, make_user):
        make_user()
        login(client)
        response = client.post(
            "/foco/ciclos", json={"mode": "invalido", "duration_minutes": 25}
        )
        assert response.status_code == 400
        assert response.get_json()["ok"] is False

    def test_cycle_with_foreign_task_returns_404(self, client, app, make_user):
        make_user("alice")
        bob_id = make_user("bob")
        with app.app_context():
            bob_task = Task(user_id=bob_id, title="do bob")
            db.session.add(bob_task)
            db.session.commit()
            bob_task_id = bob_task.id
        login(client, "alice")
        response = client.post(
            "/foco/ciclos",
            json={"mode": "focus", "task_id": bob_task_id, "duration_minutes": 25},
        )
        assert response.status_code == 404

    def test_cycle_requires_auth_json(self, app):
        response = app.test_client().post(
            "/foco/ciclos",
            json={"mode": "focus", "duration_minutes": 25},
        )
        assert response.status_code == 401
        assert response.is_json


# ==========================================================================
# EXPORTAÇÃO
# ==========================================================================
class TestExport:
    def test_json_export_is_scoped_and_has_no_hash(self, client, app, make_user):
        alice_id = make_user("alice")
        bob_id = make_user("bob")
        with app.app_context():
            db.session.add_all(
                [
                    Task(user_id=alice_id, title="Tarefa Alice", tags="a"),
                    Task(user_id=bob_id, title="Tarefa Bob"),
                    Note(user_id=alice_id, title="Nota Alice", body="conteudo"),
                    Note(user_id=bob_id, title="Nota Bob", body="segredo"),
                    Scratchpad(user_id=alice_id, content="rascunho alice"),
                    PomodoroCycle(
                        user_id=alice_id,
                        mode="focus",
                        duration_minutes=25,
                        started_at=utcnow(),
                        ended_at=utcnow(),
                    ),
                    WeeklyReview(
                        user_id=alice_id,
                        week_start=date.today(),
                        wins="Semana boa",
                        challenges="",
                        next_steps="Continuar",
                    ),
                ]
            )
            db.session.commit()

        login(client, "alice")
        response = client.get("/exportar/json")
        assert response.status_code == 200
        assert "attachment" in response.headers["Content-Disposition"]
        assert "prodsuite-alice" in response.headers["Content-Disposition"]
        payload = json.loads(response.data)
        assert payload["schema"] == "prodsuite.export.v1"
        assert payload["counts"]["tasks"] == 1
        assert payload["counts"]["notes"] == 1
        assert payload["counts"]["weekly_reviews"] == 1
        assert payload["weekly_reviews"][0]["wins"] == "Semana boa"
        assert payload["tasks"][0]["title"] == "Tarefa Alice"
        assert payload["notes"][0]["title"] == "Nota Alice"
        serialized = response.data.decode()
        assert "Tarefa Bob" not in serialized
        assert "Nota Bob" not in serialized
        assert "password_hash" not in serialized
        assert "segredo" not in serialized

    def test_db_snapshot_contains_only_current_user(self, client, app, make_user, tmp_path):
        alice_id = make_user("alice")
        bob_id = make_user("bob")
        with app.app_context():
            db.session.add_all(
                [
                    Task(user_id=alice_id, title="Tarefa Alice"),
                    Task(user_id=bob_id, title="Tarefa Bob"),
                    Note(user_id=bob_id, title="Nota Bob", body="x"),
                    WeeklyReview(
                        user_id=alice_id,
                        week_start=date.today(),
                        wins="Alice",
                        challenges="",
                        next_steps="",
                    ),
                    WeeklyReview(
                        user_id=bob_id,
                        week_start=date.today(),
                        wins="Bob",
                        challenges="",
                        next_steps="",
                    ),
                ]
            )
            db.session.commit()

        login(client, "alice")
        response = client.get("/exportar/banco.db")
        assert response.status_code == 200
        assert response.headers["Content-Type"].startswith("application/vnd.sqlite3")

        snapshot = tmp_path / "snapshot.db"
        snapshot.write_bytes(response.data)
        connection = sqlite3.connect(snapshot)
        try:
            users = connection.execute("SELECT username, password_hash FROM users").fetchall()
            tasks = connection.execute("SELECT title FROM tasks ORDER BY title").fetchall()
            notes = connection.execute("SELECT title FROM notes").fetchall()
            reviews = connection.execute(
                "SELECT wins FROM weekly_reviews"
            ).fetchall()
        finally:
            connection.close()

        assert users == [("alice", "")]
        assert [row[0] for row in tasks] == ["Tarefa Alice"]
        assert notes == []
        assert reviews == [("Alice",)]

    def test_export_requires_auth(self, client):
        assert client.get("/exportar/json").status_code == 302
        assert client.get("/exportar/banco.db").status_code == 302


# ==========================================================================
# PWA / INFRA
# ==========================================================================
class TestPWA:
    def test_manifest_is_local_and_standalone(self, client):
        response = client.get("/manifest.webmanifest")
        assert response.status_code == 200
        assert response.content_type.startswith("application/manifest+json")
        payload = response.get_json()
        assert payload["display"] == "standalone"
        assert payload["start_url"] == "/"
        assert payload["scope"] == "/"
        sizes = {icon["sizes"] for icon in payload["icons"]}
        assert {"192x192", "512x512"} <= sizes
        for icon in payload["icons"]:
            path = icon["src"].lstrip("/")
            assert (Path(__file__).resolve().parent.parent / path).exists()

    def test_service_worker_is_served_at_root_scope(self, client):
        import re

        response = client.get("/sw.js")
        assert response.status_code == 200
        assert response.headers["Service-Worker-Allowed"] == "/"
        assert "no-cache" in response.headers["Cache-Control"]
        body = response.get_data(as_text=True)
        assert "CACHE_VERSION" in body
        assert 'request.method !== "GET"' in body

        # Todo asset pré-cacheado precisa existir (um 404 silencioso degrada
        # o offline sem quebrar a instalação do SW).
        assets = set(re.findall(r'"(/[^" ]+)"', body))
        checked = 0
        for asset in assets:
            if (
                asset.startswith("/static/")
                and not asset.endswith("/")
                or asset in {"/offline", "/manifest.webmanifest"}
            ):
                assert client.get(asset).status_code == 200, asset
                checked += 1
        assert checked >= 10

    def test_pomodoro_sound_asset_and_controls(self, client, make_user):
        make_user()
        login(client)
        focus = client.get("/foco").get_data(as_text=True)
        assert "data-test-sound" in focus
        assert "pomodoro-completion-alert" in focus
        audio = client.get("/static/audio/pomodoro-alert.wav")
        assert audio.status_code == 200
        assert audio.data[:4] == b"RIFF"
        assert audio.data[8:12] == b"WAVE"
        assert len(audio.data) > 300_000

    def test_offline_shell_and_icons_exist(self, client):
        response = client.get("/offline")
        assert response.status_code == 200
        assert "sem conexão" in response.get_data(as_text=True).lower()

        required = {
            "apple-touch-icon-180.png": (180, 180),
            "icon-192.png": (192, 192),
            "icon-512.png": (512, 512),
            "icon-maskable-512.png": (512, 512),
            "icon-32.png": (32, 32),
            "icon-16.png": (16, 16),
        }
        for name, (width, height) in required.items():
            path = STATIC / "icons" / name
            assert path.exists(), name
            with path.open("rb") as handle:
                header = handle.read(24)
            assert header[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack(">II", header[16:24]) == (width, height)

    def test_manifest_link_and_ios_meta_in_base(self, client, make_user):
        make_user()
        login(client)
        html = client.get("/").get_data(as_text=True)
        assert 'rel="manifest"' in html
        assert 'apple-mobile-web-app-capable" content="yes"' in html
        assert 'apple-mobile-web-app-status-bar-style" content="default"' in html
        assert 'apple-touch-icon' in html
        assert "viewport-fit=cover" in html
        assert "bottom-nav" in html
        assert "pomodoro-hud" not in html
        assert "theme-init.js" in html
        assert "css/theme.css" in html
        assert "data-theme-toggle" in html
        assert 'rel="preload"' in html
        assert "icons/icon.svg" in html
        static_asset = client.get("/static/icons/icon.svg")
        assert static_asset.status_code == 200
        assert "max-age=3600" in static_asset.headers.get("Cache-Control", "")
        assert 'id="pomodoro-sound"' in html
        assert "/static/audio/pomodoro-alert.wav" in html

    def test_user_can_change_profile_name(self, client, app, make_user):
        user_id = make_user()
        login(client)
        response = client.post(
            "/perfil/nome",
            data={"display_name": "Ana"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Nome de perfil atualizado" in response.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(User, user_id).display_name == "Ana"

    def test_profile_has_theme_choice_without_technical_session_data(
        self, client, make_user
    ):
        make_user()
        login(client)
        html = client.get("/perfil").get_data(as_text=True)
        assert "Aparência" in html
        assert "Claro" in html
        assert "Escuro" in html
        assert "30 min" not in html
        assert "pbkdf2" not in html.lower()
        assert "Expiração de sessão" not in html

    def test_request_id_is_echoed_and_invalid_values_are_replaced(self, client):
        valid = client.get(
            "/healthz", headers={"X-Request-ID": "request-1234"}
        )
        assert valid.status_code == 200
        assert valid.headers["X-Request-ID"] == "request-1234"

        invalid = client.get(
            "/healthz", headers={"X-Request-ID": "not valid!"}
        )
        generated = invalid.headers["X-Request-ID"]
        assert generated != "not valid!"
        assert re.fullmatch(r"[0-9a-f]{16}", generated)

    def test_healthcheck_and_favicon(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"
        favicon = client.get("/favicon.ico")
        assert favicon.status_code == 200
        assert favicon.data[:4] == b"\x00\x00\x01\x00"


# ==========================================================================
# INTEGRAÇÃO DE PÁGINAS
# ==========================================================================
class TestPages:
    @pytest.mark.parametrize(
        "path,marker",
        [
            ("/", "Meu dia"),
            ("/planejar", "Planeje o seu dia"),
            ("/revisao", "Sua semana"),
            ("/tarefas", "kanban"),
            ("/foco", "Pomodoro"),
            ("/rascunhos", "Rascunhos"),
            ("/notas", "Notas"),
            ("/exportar", "Meus dados"),
            ("/perfil", "Perfil"),
        ],
    )
    def test_main_pages_render(self, client, make_user, path, marker):
        make_user()
        login(client)
        response = client.get(path)
        assert response.status_code == 200
        assert marker.lower() in response.get_data(as_text=True).lower()

    def test_visible_copy_avoids_internal_jargon(self, client, make_user):
        make_user()
        login(client)
        pages = ["/", "/exportar", "/ajuda", "/perfil"]
        forbidden = [
            "sqlite",
            "json",
            "docker",
            "container",
            "volume",
            "banco de dados",
            "servidor",
            "tailnet",
            "markdown",
            "csrf",
            "pwa",
            "service worker",
            "snapshot",
            "portabilidade",
        ]
        for path in pages:
            html = client.get(path).get_data(as_text=True)
            # Remove scripts, styles and markup: o teste olha só o texto visível.
            visible = re.sub(
                r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I
            )
            visible = re.sub(r"<[^>]+>", " ", visible).lower()
            for term in forbidden:
                assert term not in visible, f"{term!r} appears in {path}"

    def test_dashboard_contains_bento_and_weekly_chart(self, client, make_user):
        make_user()
        login(client)
        html = client.get("/").get_data(as_text=True)
        assert "bento-grid" in html
        assert "bento-hero" in html
        assert "data-timer-toggle" not in html
        assert "weekly-chart" in html
        assert "weekly-chart-line" in html
        assert "weekly-chart-grid" in html
        assert "/sw.js" not in html  # registro fica no app.js
