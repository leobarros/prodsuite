"""Fixtures compartilhadas da suíte de testes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# O módulo app.py instancia um app no import. Em testes, evitamos criar o
# SQLite local em instance/ (que conteria dados). O app de teste sobrescreve
# a URI para um arquivo temporário em tmp_path.
os.environ.setdefault("CREATE_DB_ON_START", "false")
os.environ.setdefault("SECRET_KEY", "test-import-only-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Permite executar pytest sem instalar o projeto como pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import BoardColumn, Project, User  # noqa: E402
from security import reset_login_limiter  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    database = tmp_path / "test.db"
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
            "WTF_CSRF_ENABLED": False,
            "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",
            "CREATE_DB_ON_START": True,
            "APP_TIMEZONE": "America/Sao_Paulo",
            "LOGIN_ATTEMPT_LIMIT": 5,
            "LOGIN_ATTEMPT_WINDOW_SECONDS": 300,
            "SERVER_NAME": None,
        }
    )
    with application.app_context():
        db.drop_all()
        db.create_all()
    reset_login_limiter()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
    reset_login_limiter()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(app):
    """Cria usuários com senha forte e devolve o id (sessão encerrada)."""

    def _factory(
        username="alice", email=None, password="SenhaForte1!", display_name=None
    ):
        with app.app_context():
            user = User(
                username=username,
                display_name=display_name or username,
                email=(email or f"{username}@example.com").lower(),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            # O app novo não cria colunas automaticamente. Alguns testes de
            # fluxo precisam de um quadro inicial; montamos esse cenário aqui.
            project = Project(
                user_id=user.id, name="Projeto de teste", position=0
            )
            db.session.add(project)
            db.session.flush()
            for position, (title, kind) in enumerate(
                (("A fazer", "todo"), ("Em andamento", "doing"), ("Concluídas", "done"))
            ):
                db.session.add(
                    BoardColumn(
                        user_id=user.id,
                        project_id=project.id,
                        title=title,
                        kind=kind,
                        position=position,
                    )
                )
            db.session.commit()
            return user.id

    return _factory


def login(client, username="alice", password="SenhaForte1!", follow_redirects=True):
    return client.post(
        "/entrar",
        data={"identifier": username, "password": password},
        follow_redirects=follow_redirects,
    )
