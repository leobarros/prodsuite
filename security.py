"""Serviços de infraestrutura e segurança (fora das views)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from flask import (
    Flask,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Timeout de sessão e invalidação por nonce
# --------------------------------------------------------------------------
_SKIP_ENDPOINTS = {"static", "main.service_worker", "main.manifest", "main.offline"}


def init_session_guard(app: Flask) -> None:
    """Aplica expiração de 30 min de inatividade e invalida sessões antigas."""

    @app.before_request
    def _enforce_session() -> Response | None:
        if request.endpoint in _SKIP_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            return None

        # Uma sessão é "permanente" para que o cookie carregue Max-Age; o
        # refresh deslizante só acontece porque atualizamos last_activity.
        session.permanent = True
        now = time.time()
        last = session.get("last_activity")
        lifetime = app.permanent_session_lifetime.total_seconds()

        if last is not None and now - float(last) > lifetime:
            logout_user()
            session.clear()
            flash("Sessão expirada por inatividade. Entre novamente.", "warning")
            return redirect(url_for("auth.login", next=request.path))

        # Rotação de nonce (troca de senha / "sair de todos os dispositivos")
        # invalida sessões emitidas antes da rotação.
        nonce = session.get("user_nonce")
        if not nonce or nonce != current_user.session_nonce:
            logout_user()
            session.clear()
            flash("Por segurança, entre novamente.", "warning")
            return redirect(url_for("auth.login", next=request.path))

        session["last_activity"] = now
        return None


# --------------------------------------------------------------------------
# Rate limit simples de login (em memória, por processo)
# --------------------------------------------------------------------------
_attempts: dict[str, list[float]] = defaultdict(list)
_attempts_lock = Lock()


def _throttle_key(identifier: str) -> str:
    return f"{request.remote_addr or '?'}|{(identifier or '').strip().lower()}"


def login_retry_after(identifier: str) -> int:
    """Retorna segundos de bloqueio restantes (0 se liberado)."""
    limit = current_app.config["LOGIN_ATTEMPT_LIMIT"]
    window = current_app.config["LOGIN_ATTEMPT_WINDOW_SECONDS"]
    now = time.monotonic()
    with _attempts_lock:
        bucket = _attempts.get(_throttle_key(identifier))
        if not bucket:
            return 0
        bucket[:] = [ts for ts in bucket if now - ts < window]
        if not bucket:
            _attempts.pop(_throttle_key(identifier), None)
            return 0
        if len(bucket) < limit:
            return 0
        return max(1, int(window - (now - bucket[0])))

# Nota: o contador de tentativas é por processo do Gunicorn; com 2 workers
# o limite efetivo pode chegar ao dobro. É uma mitigação, não um WAF.


def register_login_failure(identifier: str) -> None:
    limit = current_app.config["LOGIN_ATTEMPT_LIMIT"]
    window = current_app.config["LOGIN_ATTEMPT_WINDOW_SECONDS"]
    now = time.monotonic()
    with _attempts_lock:
        # Poda global para impedir crescimento ilimitado de memória.
        if len(_attempts) > 10_000:
            stale = [
                key
                for key, values in _attempts.items()
                if not values or now - values[-1] > window
            ]
            for key in stale:
                _attempts.pop(key, None)
        bucket = _attempts[_throttle_key(identifier)]
        bucket.append(now)
        if len(bucket) > limit * 2:
            del bucket[: len(bucket) - limit * 2]


def clear_login_failures(identifier: str) -> None:
    with _attempts_lock:
        _attempts.pop(_throttle_key(identifier), None)


def reset_login_limiter() -> None:
    """Usado pela suíte de testes."""
    with _attempts_lock:
        _attempts.clear()


# --------------------------------------------------------------------------
# Cabeçalhos de segurança
# --------------------------------------------------------------------------
_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'self'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "manifest-src 'self'; "
    "worker-src 'self'"
)


def init_security_headers(app: Flask) -> None:
    @app.after_request
    def _headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", _CSP)
        # HSTS só faz sentido quando a conexão já é HTTPS.
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if request.endpoint not in {"static"} and response.mimetype == "text/html":
            response.headers.setdefault("Cache-Control", "no-store")
        return response


# --------------------------------------------------------------------------
# Tratamento de erros
# --------------------------------------------------------------------------
def _wants_json() -> bool:
    return (
        request.path.startswith("/foco/ciclos")
        or request.path.startswith("/notas/preview")
        or request.accept_mimetypes.best == "application/json"
    )


def init_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def _csrf_error(error: CSRFError):
        if _wants_json():
            return jsonify(ok=False, error="Sua página expirou. Recarregue e tente novamente."), 400
        return render_template("errors/csrf.html", reason=error.description), 400

    @app.errorhandler(400)
    def _bad_request(error):
        if _wants_json():
            return jsonify(ok=False, error="Requisição inválida."), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def _forbidden(error):
        if _wants_json():
            return jsonify(ok=False, error="Acesso negado."), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def _not_found(error):
        if _wants_json():
            return jsonify(ok=False, error="Recurso não encontrado."), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def _too_large(error):
        if _wants_json():
            return jsonify(ok=False, error="Conteúdo muito grande."), 413
        flash("Conteúdo muito grande (limite de 2 MB).", "danger")
        return redirect(url_for("main.dashboard"))

    @app.errorhandler(429)
    def _rate_limited(error):
        if _wants_json():
            return jsonify(ok=False, error="Muitas tentativas. Aguarde."), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def _internal(error):
        logger.exception("Erro interno não tratado")
        if _wants_json():
            return jsonify(ok=False, error="Erro interno."), 500
        return render_template("errors/500.html"), 500
