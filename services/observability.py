"""Logs operacionais estruturados, sem corpo de requisição ou credenciais."""

from __future__ import annotations

import logging
import os
import re
import secrets
import time
from typing import Any

from flask import Flask, g, has_request_context, request
from flask_login import current_user

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_SKIP_SUCCESS_ENDPOINTS = {
    "static",
    "main.service_worker",
    "main.manifest",
    "main.offline",
    "main.favicon",
    "main.healthz",
}
_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s %(context)s%(message)s"


def _safe_path(path: str | None) -> str:
    # Não registra query string, que pode conter tokens ou parâmetros
    # pessoais; limita também caracteres de controle.
    clean = re.sub(r"[\x00-\x1f\x7f]", "", path or "")[:180]
    return clean or "-"


def _current_request_id() -> str:
    try:
        return getattr(g, "request_id", "-") or "-"
    except RuntimeError:
        return "-"


class RequestContextFilter(logging.Filter):
    """Acrescenta contexto seguro da requisição a qualquer log."""

    def filter(self, record: logging.LogRecord) -> bool:
        # O access log do Werkzeug duplica as requisições e não tem o
        # request_id do app; o app já registra as rotas dinâmicas abaixo.
        if record.name == "werkzeug" and " - - [" in record.getMessage():
            return False

        request_id = ""
        method = ""
        path = ""
        user_id = ""
        ip = ""
        if has_request_context():
            request_id = _current_request_id()
            method = request.method
            path = _safe_path(request.path)
            ip = request.remote_addr or "-"
            try:
                if current_user.is_authenticated:
                    user_id = str(current_user.id)
            except (RuntimeError, AttributeError):
                user_id = "-"

        if has_request_context():
            record.context = (
                f"[{request_id}] {method} {path} "
                f"user={user_id or '-'} ip={ip or '-'} | "
            )
        else:
            record.context = ""
        return True


def configure_app_logging(app: Flask) -> None:
    """Configura um único handler para app e módulos de segurança."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()

    # create_app pode ser chamado em testes; não duplica handlers.
    for handler in list(root.handlers):
        if getattr(handler, "_prodsuite_handler", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler._prodsuite_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    handler.addFilter(RequestContextFilter())
    root.addHandler(handler)
    root.setLevel(level)

    # O logger do Flask passa a propagar para o handler raiz, mantendo
    # também os logs de `security` e de outros módulos.
    app.logger.handlers.clear()
    app.logger.setLevel(level)
    app.logger.propagate = True


def init_request_logging(app: Flask) -> None:
    @app.before_request
    def _start_request_log() -> None:
        incoming = request.headers.get("X-Request-ID", "").strip()
        g.request_id = (
            incoming if _REQUEST_ID_RE.fullmatch(incoming) else secrets.token_hex(8)
        )
        g.request_started_at = time.perf_counter()

    @app.after_request
    def _finish_request_log(response):
        request_id = _current_request_id()
        response.headers["X-Request-ID"] = request_id

        endpoint = request.endpoint or "-"
        if (
            endpoint in _SKIP_SUCCESS_ENDPOINTS
            and response.status_code < 400
        ):
            return response

        started = getattr(g, "request_started_at", None)
        duration_ms = (
            (time.perf_counter() - started) * 1000 if started is not None else 0
        )
        length = response.calculate_content_length()
        byte_label = str(length) if length is not None else "-"
        status = response.status_code

        if status >= 500:
            level = logging.ERROR
        elif status >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO

        app.logger.log(
            level,
            "request_complete status=%s duration_ms=%.1f endpoint=%s bytes=%s",
            status,
            duration_ms,
            endpoint,
            byte_label,
        )
        return response


def log_startup(app: Flask) -> None:
    """Resumo útil e sem segredos para diagnosticar o boot."""
    database_uri = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    backend = database_uri.split(":", 1)[0] if ":" in database_uri else database_uri
    app.logger.info(
        "startup app=%s env=%s db_backend=%s timezone=%s debug=%s",
        app.config.get("APP_NAME", "ProdSuite"),
        app.config.get("ENV", "production"),
        backend or "-",
        app.config.get("APP_TIMEZONE", "-"),
        bool(app.debug),
    )
