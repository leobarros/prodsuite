"""Revisão semanal: fechamento do ciclo e ajuste de prioridades."""

from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from forms import WeeklyReviewForm
from models import PomodoroCycle, Task, WeeklyReview
from services.archive import archive_week, count_unarchived_week
from services.planning import week_start_for, weekly_metrics
from services.timeutils import day_start_utc, local_today, to_local

review_bp = Blueprint("review", __name__)


def _requested_week_start() -> date:
    raw = (request.args.get("semana") or request.form.get("week_start") or "").strip()
    current_start = week_start_for(local_today())
    if not raw:
        return current_start
    try:
        requested = week_start_for(date.fromisoformat(raw))
    except ValueError:
        return current_start
    # Não permite abrir uma semana futura por engano.
    return requested if requested <= current_start else current_start


@review_bp.route("/revisao", methods=["GET", "POST"])
@login_required
def weekly():
    today = local_today()
    current_week_start = week_start_for(today)
    week_start = _requested_week_start()
    metrics = weekly_metrics(current_user, week_start)
    review = WeeklyReview.query.filter_by(
        user_id=current_user.id, week_start=week_start
    ).first()
    is_current_week = week_start == current_week_start
    editing = is_current_week and request.args.get("editar") == "1"
    form = WeeklyReviewForm(obj=review)

    if request.method == "POST":
        if not is_current_week:
            flash("Semana encerrada é somente para consulta.", "warning")
            return redirect(url_for("review.weekly", semana=week_start.isoformat()))
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
        return redirect(url_for("review.weekly", semana=week_start.isoformat()))

    return render_template(
        "review.html",
        metrics=metrics,
        review=review,
        form=form,
        editing=editing,
        unarchived_completed=count_unarchived_week(
            current_user, metrics["week_start"]
        ),
        week_start=week_start,
        current_week_start=current_week_start,
        is_current_week=is_current_week,
        previous_week_start=week_start - timedelta(days=7),
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

@review_bp.post("/revisao/arquivar")
@login_required
def archive_completed():
    week_start = _requested_week_start()
    if week_start != week_start_for(local_today()):
        flash("Semana encerrada é somente para consulta.", "warning")
        return redirect(url_for("review.weekly", semana=week_start.isoformat()))
    count = archive_week(current_user, week_start)
    if count:
        flash(
            f"{count} tarefa{'s' if count != 1 else ''} concluída{'s' if count != 1 else ''} arquivada{'s' if count != 1 else ''}.",
            "success",
        )
    else:
        flash("Não há tarefas concluídas pendentes de arquivamento nesta semana.", "info")
    return redirect(url_for("review.weekly", semana=week_start.isoformat()))

@review_bp.get("/revisao/semanas")
@login_required
def weeks():
    """Histórico de semanas encerradas, com revisão e progresso."""
    current_start = week_start_for(local_today())
    cutoff = current_start - timedelta(weeks=26)
    reviews = {
        review.week_start: review
        for review in WeeklyReview.query.filter_by(user_id=current_user.id).all()
    }
    week_starts = {
        week for week in reviews if cutoff <= week < current_start
    }
    # A semana imediatamente anterior sempre aparece, mesmo sem atividade.
    week_starts.add(current_start - timedelta(days=7))

    completed = Task.query.filter(
        Task.user_id == current_user.id,
        Task.completed_at.isnot(None),
        Task.completed_at >= day_start_utc(cutoff),
    ).all()
    for task in completed:
        local = to_local(task.completed_at)
        if local is not None:
            week_starts.add(week_start_for(local.date()))

    cycles = PomodoroCycle.query.filter(
        PomodoroCycle.user_id == current_user.id,
        PomodoroCycle.mode == "focus",
        PomodoroCycle.ended_at >= day_start_utc(cutoff),
    ).all()
    for cycle in cycles:
        local = to_local(cycle.ended_at)
        if local is not None:
            week_starts.add(week_start_for(local.date()))

    entries = []
    for week_start in sorted(week_starts, reverse=True):
        if week_start >= current_start:
            continue
        metrics = weekly_metrics(current_user, week_start)
        entries.append(
            {
                "week_start": week_start,
                "week_end": metrics["week_end"],
                "metrics": metrics,
                "review": reviews.get(week_start),
                "archived": Task.query.filter(
                    Task.user_id == current_user.id,
                    Task.archived_week == week_start,
                ).count(),
            }
        )

    return render_template(
        "review_weeks.html",
        entries=entries,
        current_week_start=current_start,
        previous_week_start=current_start - timedelta(days=7),
    )
