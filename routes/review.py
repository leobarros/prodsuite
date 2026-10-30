"""Revisão semanal: fechamento do ciclo e ajuste de prioridades."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from forms import WeeklyReviewForm
from models import WeeklyReview
from services.planning import weekly_metrics
from services.timeutils import local_today

review_bp = Blueprint("review", __name__)


@review_bp.route("/revisao", methods=["GET", "POST"])
@login_required
def weekly():
    today = local_today()
    metrics = weekly_metrics(current_user, today)
    review = WeeklyReview.query.filter_by(
        user_id=current_user.id, week_start=metrics["week_start"]
    ).first()
    editing = request.args.get("editar") == "1"
    form = WeeklyReviewForm(obj=review)

    if request.method == "POST":
        editing = True

    if form.validate_on_submit():
        if review is None:
            review = WeeklyReview(
                user_id=current_user.id, week_start=metrics["week_start"]
            )
            db.session.add(review)
        review.wins = form.wins.data or ""
        review.challenges = form.challenges.data or ""
        review.next_steps = form.next_steps.data or ""
        db.session.commit()
        flash("Revisão da semana salva.", "success")
        return redirect(url_for("review.weekly"))

    return render_template(
        "review.html",
        metrics=metrics,
        review=review,
        form=form,
        editing=editing,
        review_notes=(
            [
                ("O que funcionou bem?", review.wins),
                ("O que foi difícil?", review.challenges),
                ("Foco da próxima semana", review.next_steps),
            ]
            if review
            else []
        ),
    )
