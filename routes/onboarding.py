"""Tour de boas-vindas para contas novas e página de ajuda."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import Blueprint, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from extensions import db

onboarding_bp = Blueprint("onboarding", __name__)


def _safe_next(target: str | None) -> str:
    if not target:
        return url_for("main.dashboard")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/"):
        return url_for("main.dashboard")
    if target.startswith("//") or "\\" in target:
        return url_for("main.dashboard")
    return target


@onboarding_bp.get("/bem-vindo")
@login_required
def welcome():
    """Abre o tutorial como pop-up no Meu dia, sem tirar a pessoa do app."""
    return redirect(url_for("main.dashboard", tour=1))


@onboarding_bp.post("/bem-vindo/concluir")
@login_required
def complete():
    current_user.onboarding_completed = True
    db.session.commit()
    if request.is_json or request.headers.get("X-Requested-With"):
        return jsonify(ok=True)
    flash("Tutorial concluído. Bom trabalho!", "success")
    return redirect(_safe_next(request.form.get("next")))
