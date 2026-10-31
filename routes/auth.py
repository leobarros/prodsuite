"""Autenticação: registro, login, logout e perfil."""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from forms import ChangePasswordForm, DisplayNameForm, LoginForm, RegisterForm
from models import User, utcnow
from security import (
    clear_login_failures,
    login_retry_after,
    register_login_failure,
)

auth_bp = Blueprint("auth", __name__)

# Hash descartável para igualar o custo de verificação quando o usuário não
# existe (mitiga enumeração por timing).
_DUMMY_HASH = generate_password_hash("nao-e-uma-senha-valida")


def _safe_next(target: str | None) -> str:
    """Aceita apenas caminhos internos, evitando open redirect."""
    if not target:
        return url_for("main.dashboard")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/"):
        return url_for("main.dashboard")
    if target.startswith("//") or "\\" in target:
        return url_for("main.dashboard")
    return target


def _complete_login(user: User) -> None:
    """Limpa a sessão (fixation), autentica e grava os marcadores de guarda."""
    session.clear()
    login_user(user, remember=False)
    session.permanent = True
    session["last_activity"] = time.time()
    session["user_nonce"] = user.session_nonce
    user.last_login_at = utcnow()
    db.session.commit()


@auth_bp.route("/registrar", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if not current_app.config.get("ALLOW_REGISTRATION", True):
        abort(403)

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            display_name=form.display_name.data,
            email=form.email.data.lower(),
            onboarding_completed=False,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Usuário ou e-mail já cadastrado.", "danger")
            return render_template("auth/register.html", form=form), 409

        _complete_login(user)
        current_app.logger.info("auth.register.success user_id=%s", user.id)
        flash("Conta criada. Vamos começar?", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/entrar", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        retry_after = login_retry_after(identifier)
        if retry_after:
            current_app.logger.warning(
                "auth.login.rate_limited retry_after_s=%s", retry_after
            )
            flash(
                f"Muitas tentativas. Tente novamente em {retry_after}s.",
                "danger",
            )
            response = make_response(
                render_template("auth/login.html", form=form), 429
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

        user = User.query.filter(
            or_(
                func.lower(User.username) == identifier.lower(),
                func.lower(User.email) == identifier.lower(),
            )
        ).first()

        password = form.password.data or ""
        if user is not None:
            valid = user.check_password(password)
        else:
            # Custo constante mesmo sem usuário.
            check_password_hash(_DUMMY_HASH, password)
            valid = False

        if user is not None and valid:
            clear_login_failures(identifier)
            _complete_login(user)
            current_app.logger.info("auth.login.success user_id=%s", user.id)
            flash("Que bom ter você de volta!", "success")
            return redirect(_safe_next(request.form.get("next") or request.args.get("next")))

        current_app.logger.warning(
            "auth.login.failure user_id=%s",
            user.id if user is not None else "-",
        )
        register_login_failure(identifier)
        flash("Usuário/e-mail ou senha inválidos.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.post("/sair")
@login_required
def logout():
    user_id = current_user.id
    logout_user()
    session.clear()
    current_app.logger.info("auth.logout user_id=%s", user_id)
    flash("Você saiu. Até logo!", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def profile():
    form = ChangePasswordForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("Senha atual incorreta.")
        else:
            current_user.set_password(form.new_password.data)
            # Trocar a senha invalida todas as outras sessões.
            nonce = current_user.rotate_session_nonce()
            db.session.commit()
            session["user_nonce"] = nonce
            session["last_activity"] = time.time()
            current_app.logger.info(
                "auth.password_changed user_id=%s", current_user.id
            )
            flash("Senha atualizada. Os outros aparelhos foram desconectados.", "success")
            return redirect(url_for("auth.profile"))

    return render_template(
        "auth/profile.html",
        form=form,
        name_form=DisplayNameForm(display_name=current_user.display_name),
    )


@auth_bp.post("/perfil/nome")
@login_required
def update_display_name():
    form = DisplayNameForm()
    if form.validate_on_submit():
        current_user.display_name = form.display_name.data
        db.session.commit()
        flash("Nome de perfil atualizado.", "success")
    else:
        for error in form.display_name.errors:
            flash(error, "danger")
    return redirect(url_for("auth.profile"))


@auth_bp.post("/perfil/sessoes/encerrar")
@login_required
def revoke_other_sessions():
    nonce = current_user.rotate_session_nonce()
    db.session.commit()
    session["user_nonce"] = nonce
    session["last_activity"] = time.time()
    flash("Os outros aparelhos foram desconectados.", "success")
    return redirect(url_for("auth.profile"))
