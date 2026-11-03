"""Menu de hidratação: faixa pessoal, registros e lembretes."""

from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from extensions import db
from models import WaterLog
from services.water import (
    add_log,
    goal_range,
    settings_for,
    summary_for,
    today_logs,
)

water_bp = Blueprint("water", __name__, url_prefix="/agua")


def _wants_json() -> bool:
    return bool(
        request.is_json
        or request.headers.get("X-Requested-With")
        in {"fetch", "XMLHttpRequest"}
        or request.accept_mimetypes.best == "application/json"
    )


def _payload():
    return request.get_json(silent=True) or request.form


def _recent_html():
    summary = summary_for(current_user)
    return render_template(
        "_water_recent.html", recent=summary["recent"], today=summary["day"]
    )


def _json_summary(extra=None):
    summary = summary_for(current_user)
    payload = {
        "ok": True,
        "total": summary["total"],
        "target": summary["goal"]["target"],
        "low": summary["goal"]["low"],
        "high": summary["goal"]["high"],
        "percent": summary["percent"],
        "remaining": summary["remaining"],
        "status_key": summary["status_key"],
        "status_label": summary["status_label"],
        "hourly_warning": summary["hourly_warning"],
        "last_hour": summary["last_hour"],
        "recent_html": _recent_html(),
        "week_days": summary["week_days"],
        "week_average": summary["week_average"],
        "in_range_days": summary["in_range_days"],
    }
    if extra:
        payload.update(extra)
    return jsonify(payload)


@water_bp.get("/")
@login_required
def index():
    summary = summary_for(current_user)
    return render_template(
        "water.html",
        summary=summary,
        settings=summary["settings"],
    )


@water_bp.post("/registrar")
@login_required
def register():
    payload = _payload()
    raw_amount = payload.get("amount_ml") or payload.get("amount") or 200
    try:
        amount = int(raw_amount)
        add_log(current_user, amount)
    except (TypeError, ValueError) as exc:
        if _wants_json():
            return jsonify(ok=False, error=str(exc)), 400
        flash(str(exc), "danger")
        return redirect(url_for("water.index"))

    if _wants_json():
        return _json_summary({"amount": amount})
    flash(f"{amount} ml registrados.", "success")
    return redirect(url_for("water.index"))


@water_bp.post("/desfazer/<int:log_id>")
@login_required
def undo(log_id: int):
    log = WaterLog.query.filter_by(
        id=log_id, user_id=current_user.id
    ).first_or_404()
    log_id = log.id
    db.session.delete(log)
    db.session.commit()
    if _wants_json():
        return _json_summary({"removed": log_id})
    flash("Registro removido.", "info")
    return redirect(url_for("water.index"))


@water_bp.post("/configurar")
@login_required
def configure():
    settings = settings_for(current_user, create=True)
    raw_weight = (request.form.get("weight_kg") or "").strip().replace(",", ".")
    weight = None
    if raw_weight:
        try:
            weight = float(raw_weight)
        except ValueError:
            flash("Informe um peso válido em kg.", "danger")
            return redirect(url_for("water.index"))
        if weight < 30 or weight > 250:
            flash("O peso deve ficar entre 30 e 250 kg.", "danger")
            return redirect(url_for("water.index"))

    extra = request.form.get("extra_ml", "0")
    extra = int(extra) if extra in {"0", "300", "600"} else 0
    interval = request.form.get("reminder_interval_minutes", "90")
    interval = int(interval) if interval in {"60", "90", "120"} else 90

    settings.weight_kg = weight
    settings.extra_ml = extra
    settings.reminders_enabled = bool(request.form.get("reminders_enabled"))
    settings.reminder_interval_minutes = interval
    db.session.commit()
    flash("Meta de hidratação atualizada.", "success")
    return redirect(url_for("water.index"))
