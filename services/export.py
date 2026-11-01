"""Exportação e portabilidade dos dados.

Dois formatos:
* **JSON estruturado** — legível, versionado, sem hashes de senha.
* **Snapshot SQLite** — cópia consistente do banco via API de backup do
  SQLite, porém *filtrada*: contém apenas as linhas do usuário autenticado e
  com ``password_hash`` esvaziado. Entregar o banco inteiro vazaria dados de
  outras contas — por isso nunca usamos o arquivo original diretamente.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import tempfile
from datetime import datetime, timezone

from flask import current_app
from extensions import db
from models import (
    BoardColumn,
    Category,
    Note,
    PomodoroCycle,
    Project,
    Scratchpad,
    Task,
    TaskColumnStay,
    User,
    WeeklyReview,
    utcnow,
)
from services.boards import ensure_default_project
from services.categories import ensure_categories


def build_user_export(user) -> bytes:
    tasks = (
        Task.query.filter_by(user_id=user.id).order_by(Task.created_at.asc()).all()
    )
    notes = (
        Note.query.filter_by(user_id=user.id).order_by(Note.created_at.asc()).all()
    )
    scratchpads = (
        Scratchpad.query.filter(
            Scratchpad.user_id == user.id,
            Scratchpad.converted_task_id.is_(None),
        )
        .order_by(Scratchpad.created_at.asc())
        .all()
    )
    cycles = (
        PomodoroCycle.query.filter_by(user_id=user.id)
        .order_by(PomodoroCycle.ended_at.asc())
        .all()
    )
    reviews = (
        WeeklyReview.query.filter_by(user_id=user.id)
        .order_by(WeeklyReview.week_start.asc())
        .all()
    )
    columns = (
        BoardColumn.query.filter_by(user_id=user.id)
        .order_by(BoardColumn.position.asc())
        .all()
    )
    ensure_default_project(user)
    categories = ensure_categories(user)
    stays = (
        TaskColumnStay.query.filter_by(user_id=user.id)
        .order_by(TaskColumnStay.entered_at.asc())
        .all()
    )
    projects = (
        Project.query.filter_by(user_id=user.id)
        .order_by(Project.position.asc(), Project.id.asc())
        .all()
    )

    payload = {
        "schema": "prodsuite.export.v1",
        "app": current_app.config.get("APP_NAME", "PRD//SUITE"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "UTC (datas em ISO-8601 sem offset)",
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": (
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
            "weekly_focus_goal": user.weekly_focus_goal,
        },
        "counts": {
            "tasks": len(tasks),
            "notes": len(notes),
            "scratchpads": len(scratchpads),
            "pomodoro_cycles": len(cycles),
            "weekly_reviews": len(reviews),
            "columns": len(columns),
            "categories": len(categories),
            "projects": len(projects),
            "column_stays": len(stays),
        },
        "projects": [project.to_export_dict() for project in projects],
        "column_stays": [stay.to_export_dict() for stay in stays],
        "columns": [column.to_export_dict() for column in columns],
        "categories": [category.to_export_dict() for category in categories],
        "tasks": [task.to_export_dict() for task in tasks],
        "notes": [note.to_export_dict() for note in notes],
        "scratchpads": [scratch.to_export_dict() for scratch in scratchpads],
        "pomodoro_cycles": [cycle.to_export_dict() for cycle in cycles],
        "weekly_reviews": [review.to_export_dict() for review in reviews],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _source_db_path() -> str:
    database = db.engine.url.database
    if not database or database == ":memory:":
        raise RuntimeError("Exportação .db exige um banco SQLite em arquivo.")
    return os.path.abspath(database)


def build_user_db_snapshot(user) -> str:
    """Cria um .db temporário, consistente e restrito ao usuário.

    Retorna o caminho do arquivo; o chamador é responsável por removê-lo.
    """
    source_path = _source_db_path()
    if not os.path.exists(source_path):
        raise RuntimeError("Arquivo do banco não encontrado.")

    # Garante que o backup enxergue transações pendentes da sessão.
    db.session.commit()

    fd, dest_path = tempfile.mkstemp(
        prefix=f"prodsuite-{user.username}-", suffix=".db"
    )
    os.close(fd)

    source = sqlite3.connect(source_path)
    dest = sqlite3.connect(dest_path)
    try:
        source.backup(dest)
        dest.execute("PRAGMA journal_mode=DELETE")
        dest.execute("PRAGMA foreign_keys=OFF")

        with dest:
            for table in (
                "pomodoro_cycles",
                "scratchpads",
                "notes",
                "weekly_reviews",
                "tasks",
                "board_columns",
                "categories",
                "projects",
                "task_column_stays",
            ):
                dest.execute(
                    f"DELETE FROM {table} WHERE user_id != ?",  # nome fixo allowlist
                    (user.id,),
                )
            dest.execute("DELETE FROM users WHERE id != ?", (user.id,))
            # Portabilidade sem vazar credenciais: o hash não vai no arquivo.
            dest.execute(
                "UPDATE users SET password_hash = '', session_nonce = ? WHERE id = ?",
                (secrets.token_hex(16), user.id),
            )
        # VACUUM precisa rodar fora de uma transação explícita.
        dest.execute("VACUUM")
    finally:
        dest.close()
        source.close()

    return dest_path


def backup_counts(user) -> dict:
    """Contagens usadas na tela de exportação."""
    return {
        "tasks": Task.query.filter_by(user_id=user.id).count(),
        "notes": Note.query.filter_by(user_id=user.id).count(),
        "scratchpads": Scratchpad.query.filter(
            Scratchpad.user_id == user.id,
            Scratchpad.converted_task_id.is_(None),
        ).count(),
        "pomodoro_cycles": PomodoroCycle.query.filter_by(user_id=user.id).count(),
        "weekly_reviews": WeeklyReview.query.filter_by(user_id=user.id).count(),
    }


def safe_filename(user: User, extension: str) -> str:
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    username = "".join(
        ch for ch in user.username if ch.isalnum() or ch in ("-", "_")
    ) or "usuario"
    return f"prodsuite-{username}-{stamp}.{extension}"
