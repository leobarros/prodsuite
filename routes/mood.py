"""Menu de humor: check-in breve, contexto e histórico pessoal."""

from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from extensions import db
from models import MoodEntry
from services.mood import (
    CONTEXT_LABELS,
    MOOD_COLORS,
    MOOD_LABELS,
    context_list,
    create_entry,
    summary_for,
)

mood_bp = Blueprint("mood", __name__, url_prefix="/humor")


def _render(summary, *, values=None, errors=None, status=200):
    return (
        render_template(
            "mood.html",
            summary=summary,
            values=values or {},
            errors=errors or [],
            mood_labels=MOOD_LABELS,
            mood_colors=MOOD_COLORS,
            context_labels=CONTEXT_LABELS,
        ),
        status,
    )


def _entry_values(entry):
    return {
        "mood": entry.mood,
        "energy": entry.energy,
        "tension": entry.tension,
        "contexts": (entry.contexts or "").split(","),
        "note": entry.note,
    }


@mood_bp.get("/")
@login_required
def index():
    return _render(
        summary_for(current_user),
        values={
            "mood": 4,
            "energy": 3,
            "tension": 2,
            "contexts": [],
            "note": "",
        },
    )


@mood_bp.post("/registrar")
@login_required
def register():
    raw_mood = request.form.get("mood")
    raw_energy = request.form.get("energy")
    raw_tension = request.form.get("tension")
    note = (request.form.get("note") or "").strip()
    context_keys = request.form.getlist("contexts")
    values = {
        "mood": raw_mood,
        "energy": raw_energy,
        "tension": raw_tension,
        "contexts": context_keys,
        "note": note,
    }
    errors = []
    scales = {}
    for name, raw in (
        ("humor", raw_mood),
        ("energia", raw_energy),
        ("tensão", raw_tension),
    ):
        try:
            scale = int(raw)
        except (TypeError, ValueError):
            errors.append(f"Escolha um valor de {name} entre 1 e 5.")
            continue
        if scale < 1 or scale > 5:
            errors.append(f"Escolha um valor de {name} entre 1 e 5.")
        scales[name] = scale
    if len(note) > 500:
        errors.append("A nota pode ter no máximo 500 caracteres.")

    if errors:
        return _render(
            summary_for(current_user),
            values=values,
            errors=errors,
            status=400,
        )

    entry = create_entry(
        current_user,
        mood=scales["humor"],
        energy=scales["energia"],
        tension=scales["tensão"],
        contexts=context_keys,
        note=note,
    )
    flash("Check-in de humor salvo. Obrigado por pausar.", "success")
    return redirect(url_for("mood.index"))


@mood_bp.post("/<int:entry_id>/excluir")
@login_required
def delete(entry_id: int):
    entry = MoodEntry.query.filter_by(
        id=entry_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash("Registro de humor removido.", "info")
    return redirect(url_for("mood.index"))
