"""Configuração central da PRD//SUITE.

Todos os valores podem ser sobrescritos por variáveis de ambiente, o que
facilita o deploy em Docker sem alterar código. O arquivo é intencionalmente
explicito: nenhum segredo fica hardcoded em produção (o compose exige
``SECRET_KEY``).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _as_bool(name: str, default: bool = False) -> bool:
    """Lê booleanos de ambiente aceitando 1/true/yes/on (case-insensitive)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _as_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _default_database_uri() -> str:
    """SQLite local em ``instance/``; no container o volume fica em ``/data``."""
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    return f"sqlite:///{BASE_DIR / 'instance' / 'prodsuite.db'}"


class Config:
    # ------------------------------------------------------------------ core
    APP_NAME = "ProdSuite"
    APP_VERSION = os.environ.get("APP_VERSION", "1.0")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
    ENV = os.environ.get("FLASK_ENV", "production")

    # Sessão: expira após 30 minutos de inatividade (RF01.2). O refresh do
    # cookie a cada request é combinado com uma checagem server-side em
    # ``app.enforce_session_timeout`` para não depender apenas do navegador.
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=_as_int("SESSION_LIFETIME_MINUTES", 30)
    )
    SESSION_COOKIE_NAME = "prodsuite_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Em produção atrás de HTTPS (tailscale serve) habilite COOKIE_SECURE=true.
    SESSION_COOKIE_SECURE = _as_bool("COOKIE_SECURE", False)
    SESSION_REFRESH_EACH_REQUEST = True
    REMEMBER_COOKIE_DURATION = None

    # ------------------------------------------------------------------- db
    SQLALCHEMY_DATABASE_URI = _default_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"timeout": 15},
    }
    # Cria as tabelas no boot (idempotente). No Docker o entrypoint roda o
    # comando ``flask init-db`` antes do Gunicorn.
    CREATE_DB_ON_START = _as_bool("CREATE_DB_ON_START", True)

    # --------------------------------------------------------------- csrf
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # o token vive enquanto a sessão viver
    WTF_CSRF_SSL_STRICT = False  # compatível com tailnet em HTTP/HTTPS
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB por request

    # ------------------------------------------------------------- domínio
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "America/Sao_Paulo")
    PASSWORD_HASH_METHOD = os.environ.get(
        "PASSWORD_HASH_METHOD", "pbkdf2:sha256:600000"
    )
    # Requisito do projeto: mínimo de 4 caracteres. Pode ser elevado em
    # produção via PASSWORD_MIN_LENGTH (ex.: 12) sem alterar o código.
    PASSWORD_MIN_LENGTH = max(4, min(_as_int("PASSWORD_MIN_LENGTH", 4), 128))
    LOGIN_ATTEMPT_LIMIT = _as_int("LOGIN_ATTEMPT_LIMIT", 5)
    LOGIN_ATTEMPT_WINDOW_SECONDS = _as_int("LOGIN_ATTEMPT_WINDOW_SECONDS", 300)
    # Registro aberto é conveniente no primeiro acesso, mas em uma tailnet
    # pessoal deve ser desligado depois da criação da conta.
    ALLOW_REGISTRATION = _as_bool("ALLOW_REGISTRATION", True)
    NOTE_MAX_LENGTH = 40_000
    SCRATCHPAD_MAX_LENGTH = 5_000

    # ------------------------------------------------------------- server
    JSON_SORT_KEYS = False
    TEMPLATES_AUTO_RELOAD = _as_bool("TEMPLATES_AUTO_RELOAD", False)
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")
    # Estáticos sem fingerprint: cache curto o suficiente para evitar
    # revalidação a cada navegação, sem deixar CSS/JS antigos por muito tempo.
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(hours=1)
