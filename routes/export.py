"""Backup e portabilidade: JSON estruturado e snapshot SQLite por usuário."""

from __future__ import annotations

import os
from io import BytesIO

from flask import (
    Blueprint,
    after_this_request,
    current_app,
    flash,
    redirect,
    render_template,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from services.export import (
    backup_counts,
    build_user_db_snapshot,
    build_user_export,
    safe_filename,
)

export_bp = Blueprint("export", __name__)


@export_bp.get("/exportar")
@login_required
def index():
    return render_template("export.html", counts=backup_counts(current_user))


@export_bp.get("/exportar/json")
@login_required
def export_json():
    payload = build_user_export(current_user)
    return send_file(
        BytesIO(payload),
        mimetype="application/json",
        as_attachment=True,
        download_name=safe_filename(current_user, "json"),
        max_age=0,
    )


@export_bp.get("/exportar/banco.db")
@login_required
def export_db():
    try:
        path = build_user_db_snapshot(current_user)
    except Exception:
        current_app.logger.exception("Falha ao gerar snapshot do banco")
        flash("Não foi possível preparar sua cópia. Tente novamente.", "danger")
        return redirect(url_for("export.index"))

    @after_this_request
    def _cleanup(response):
        try:
            os.unlink(path)
        except OSError:
            pass
        return response

    return send_file(
        path,
        mimetype="application/vnd.sqlite3",
        as_attachment=True,
        download_name=safe_filename(current_user, "db"),
        max_age=0,
    )
