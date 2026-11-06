"""Relatório semanal integrado do ProdSuite."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from flask import Blueprint, make_response, render_template, request
from flask_login import current_user, login_required
from weasyprint import HTML

from services.reports import report_for
from services.timeutils import app_timezone

reports_bp = Blueprint("reports", __name__, url_prefix="/relatorio")


@reports_bp.get("/")
@login_required
def weekly():
    report = report_for(current_user, request.args.get("semana"))
    return render_template("report.html", report=report)


@reports_bp.get("/pdf")
@login_required
def pdf():
    report = report_for(current_user, request.args.get("semana"))
    logo_path = Path(request.root_path) / "static" / "icons" / "icon-192.png"
    logo_data = "data:image/png;base64," + base64.b64encode(
        logo_path.read_bytes()
    ).decode("ascii")
    html = render_template(
        "report_pdf.html",
        report=report,
        logo_data=logo_data,
        generated_at=datetime.now(app_timezone()),
    )
    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()
    filename = (
        f"prodsuite-relatorio-{report['week_start'].strftime('%d-%m-%Y')}.pdf"
    )
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "private, no-store"
    return response
