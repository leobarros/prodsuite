"""Central de ajuda com o uso do app e os conceitos aplicados."""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

help_bp = Blueprint("help", __name__)


@help_bp.get("/ajuda")
@login_required
def help_page():
    return render_template("help.html")
