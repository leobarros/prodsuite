"""Dashboard, busca global, PWA e healthcheck."""

from __future__ import annotations

from datetime import timedelta

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from flask_login import current_user, login_required
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Note, Scratchpad, Task, WeeklyReview
from services.planning import week_start_for, weekly_metrics
from services.pomodoro import focus_stats
from services.search import global_search
from services.timeutils import day_start_utc, local_today

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
@login_required
def dashboard():
    uid = current_user.id
    today_start = day_start_utc(local_today())

    status_counts = dict(
        db.session.query(Task.status, func.count(Task.id))
        .filter(Task.user_id == uid)
        .group_by(Task.status)
        .all()
    )

    open_tasks = (
        Task.query.filter(Task.user_id == uid, Task.status != "done")
        .order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.updated_at.desc())
        .limit(50)
        .all()
    )
    open_tasks.sort(
        key=lambda t: (
            not t.is_mit,
            t.quadrant_rank,
            t.due_date or local_today(),
            -t.id,
        )
    )
    mit_tasks = [task for task in open_tasks if task.is_mit][:3]
    planned_today = [
        task for task in open_tasks if task.planned_for == local_today()
    ]
    focus_task = (
        mit_tasks[0]
        if mit_tasks
        else next((t for t in open_tasks if t.status == "doing"), None)
    )
    focus_task = focus_task or (open_tasks[0] if open_tasks else None)
    current_week_start = week_start_for(local_today())
    previous_week_start = current_week_start - timedelta(days=7)
    previous_metrics = weekly_metrics(current_user, previous_week_start)
    previous_review = WeeklyReview.query.filter_by(
        user_id=uid, week_start=previous_week_start
    ).first()
    review_prompt = previous_review is None and bool(
        previous_metrics["sessions"]
        or previous_metrics["completed_tasks"]
        or previous_metrics["mit_total"]
    )
    week_metrics = weekly_metrics(current_user, local_today())

    upcoming = [
        t
        for t in open_tasks
        if t.due_date and t.due_date <= local_today() + timedelta(days=7)
    ][:20]
    overdue = [
        t for t in open_tasks if t.due_date and t.due_date < local_today()
    ]

    completed_today = Task.query.filter(
        Task.user_id == uid,
        Task.status == "done",
        Task.completed_at >= today_start,
    ).count()

    recent_notes = (
        Note.query.filter_by(user_id=uid)
        .order_by(Note.updated_at.desc())
        .limit(20)
        .all()
    )
    recent_scratch = (
        Scratchpad.query.filter(
            Scratchpad.user_id == uid,
            Scratchpad.converted_task_id.is_(None),
        )
        .order_by(Scratchpad.created_at.desc())
        .limit(20)
        .all()
    )

    stats = focus_stats(current_user, days=7)

    return render_template(
        "dashboard.html",
        status_counts=status_counts,
        counts={
            "todo": status_counts.get("todo", 0),
            "doing": status_counts.get("doing", 0),
            "done": status_counts.get("done", 0),
            "open": status_counts.get("todo", 0) + status_counts.get("doing", 0),
            "completed_today": completed_today,
            "overdue": len(overdue),
            "mit": len(mit_tasks),
            "planned_today": len(planned_today),
        },
        open_tasks=open_tasks[:5],
        mit_tasks=mit_tasks,
        planned_today=planned_today,
        focus_task=focus_task,
        upcoming=upcoming,
        recent_notes=recent_notes,
        recent_scratch=recent_scratch,
        stats=stats,
        week_metrics=week_metrics,
        review_prompt=review_prompt,
        previous_metrics=previous_metrics,
        previous_week_start=previous_week_start,
    )


@main_bp.get("/busca")
@login_required
def search():
    query = (request.args.get("q") or "").strip()[:120]
    results = global_search(current_user, query)
    return render_template("search.html", results=results, query=query)


@main_bp.get("/manifest.webmanifest")
def manifest():
    response = send_from_directory(
        current_app.static_folder,
        "manifest.json",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@main_bp.get("/sw.js")
def service_worker():
    """Service Worker na raiz para controlar todo o escopo do app."""
    response = send_from_directory(
        current_app.static_folder, "sw.js", mimetype="application/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@main_bp.get("/offline")
def offline():
    return render_template("offline.html")


@main_bp.get("/favicon.ico")
def favicon():
    return send_from_directory(current_app.static_folder, "icons/favicon.ico")


@main_bp.get("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        current_app.logger.exception("Healthcheck falhou")
        return jsonify(status="error"), 503
    return jsonify(status="ok"), 200
