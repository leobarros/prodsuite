"""Banco local da TUI, independente do app web."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .paths import database_path, ensure_data_dir

TASK_STATUSES = ("todo", "doing", "done")
TASK_PRIORITIES = ("low", "medium", "high")


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return date.today().isoformat()


class Store:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            ensure_data_dir()
            path = database_path()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._schema()

    def _schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT NOT NULL DEFAULT 'medium',
                due_date TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                minutes INTEGER NOT NULL,
                mode TEXT NOT NULL DEFAULT 'focus',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS water_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount_ml INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'water',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mood_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mood INTEGER NOT NULL,
                energy INTEGER NOT NULL DEFAULT 3,
                tension INTEGER NOT NULL DEFAULT 2,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start TEXT NOT NULL UNIQUE,
                wins TEXT NOT NULL DEFAULT '',
                challenges TEXT NOT NULL DEFAULT '',
                next_steps TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ tasks
    def list_tasks(self, include_done: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM tasks"
        args: list[Any] = []
        if not include_done:
            sql += " WHERE status != 'done'"
        sql += " ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1 ELSE 2 END, created_at"
        return list(self.conn.execute(sql, args))

    def add_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        due_date: str | None = None,
    ) -> int:
        title = title.strip()
        if not title:
            raise ValueError("A tarefa precisa de um título.")
        if priority not in TASK_PRIORITIES:
            priority = "medium"
        cur = self.conn.execute(
            "INSERT INTO tasks (title, description, priority, due_date, created_at) VALUES (?, ?, ?, ?, ?)",
            (title[:160], description.strip(), priority, due_date, utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def complete_task(self, task_id: int, complete: bool = True) -> None:
        self.conn.execute(
            "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
            ("done" if complete else "todo", utcnow() if complete else None, task_id),
        )
        self.conn.commit()

    def move_task(self, task_id: int, status: str) -> None:
        if status not in TASK_STATUSES:
            return
        self.conn.execute(
            "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
            (status, utcnow() if status == "done" else None, task_id),
        )
        self.conn.commit()

    def task(self, task_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    # ------------------------------------------------------------------ inbox
    def list_inbox(self, state: str = "open") -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM inbox WHERE state = ? ORDER BY created_at",
                (state,),
            )
        )

    def capture(self, content: str) -> int:
        content = content.strip()
        if not content:
            raise ValueError("Escreva algo antes de capturar.")
        cur = self.conn.execute(
            "INSERT INTO inbox (content, created_at) VALUES (?, ?)",
            (content[:5000], utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_inbox_state(self, item_id: int, state: str) -> None:
        if state not in {"open", "someday", "done"}:
            return
        self.conn.execute("UPDATE inbox SET state = ? WHERE id = ?", (state, item_id))
        self.conn.commit()

    def inbox_item(self, item_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM inbox WHERE id = ?", (item_id,)).fetchone()

    # ------------------------------------------------------------------ notes
    def list_notes(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute("SELECT * FROM notes ORDER BY updated_at DESC")
        )

    def save_note(
        self,
        title: str,
        body: str,
        tags: str = "",
        note_id: int | None = None,
    ) -> int:
        title = title.strip()
        if not title:
            raise ValueError("A nota precisa de um título.")
        if note_id is None:
            cur = self.conn.execute(
                "INSERT INTO notes (title, body, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (title[:160], body, tags.strip(), utcnow(), utcnow()),
            )
            note_id = int(cur.lastrowid)
        else:
            self.conn.execute(
                "UPDATE notes SET title = ?, body = ?, tags = ?, updated_at = ? WHERE id = ?",
                (title[:160], body, tags.strip(), utcnow(), note_id),
            )
        self.conn.commit()
        return note_id

    def note(self, note_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()

    # ------------------------------------------------------------------ focus
    def log_focus(self, task_id: int | None, minutes: int, mode: str = "focus") -> None:
        self.conn.execute(
            "INSERT INTO focus_sessions (task_id, minutes, mode, created_at) VALUES (?, ?, ?, ?)",
            (task_id, max(1, int(minutes)), mode, utcnow()),
        )
        self.conn.commit()

    def focus_last_days(self) -> list[tuple[str, int]]:
        labels = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
        values: list[tuple[str, int]] = []
        for offset in range(6, -1, -1):
            day = (date.today() - timedelta(days=offset)).isoformat()
            row = self.conn.execute(
                "SELECT COALESCE(SUM(minutes), 0) AS total FROM focus_sessions "
                "WHERE mode = 'focus' AND substr(created_at, 1, 10) = ?",
                (day,),
            ).fetchone()
            values.append((labels[(date.fromisoformat(day).weekday())], int(row["total"] or 0)))
        return values

    def focus_stats(self) -> dict[str, int]:
        start = (date.today() - timedelta(days=6)).isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(minutes), 0) AS minutes, COUNT(*) AS sessions FROM focus_sessions WHERE substr(created_at, 1, 10) >= ? AND mode = 'focus'",
            (start,),
        ).fetchone()
        return {"minutes": int(row["minutes"] or 0), "sessions": int(row["sessions"] or 0)}

    # ------------------------------------------------------------------ care
    def add_water(self, amount_ml: int, kind: str = "water") -> None:
        amount_ml = max(1, min(2000, int(amount_ml)))
        self.conn.execute(
            "INSERT INTO water_logs (amount_ml, kind, created_at) VALUES (?, ?, ?)",
            (amount_ml, kind, utcnow()),
        )
        self.conn.commit()

    def water_today(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_ml), 0) AS total FROM water_logs WHERE substr(created_at, 1, 10) = ? AND kind = 'water'",
            (today(),),
        ).fetchone()
        return int(row["total"] or 0)

    def add_mood(self, mood: int, energy: int, tension: int, note: str = "") -> None:
        self.conn.execute(
            "INSERT INTO mood_entries (mood, energy, tension, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (max(1, min(5, int(mood))), max(1, min(5, int(energy))), max(1, min(5, int(tension))), note.strip(), utcnow()),
        )
        self.conn.commit()

    def mood_stats(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT ROUND(AVG(mood), 1) AS mood, COUNT(*) AS entries FROM mood_entries WHERE substr(created_at, 1, 10) >= ?",
            ((date.today() - timedelta(days=6)).isoformat(),),
        ).fetchone()
        return {
            "mood": float(row["mood"] or 0),
            "entries": int(row["entries"] or 0),
        }

    # ------------------------------------------------------------------ review
    def current_week_start(self) -> str:
        today_date = date.today()
        return (today_date - timedelta(days=today_date.weekday())).isoformat()

    def save_review(self, wins: str, challenges: str, next_steps: str) -> None:
        self.conn.execute(
            """INSERT INTO reviews (week_start, wins, challenges, next_steps, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(week_start) DO UPDATE SET
                 wins = excluded.wins,
                 challenges = excluded.challenges,
                 next_steps = excluded.next_steps,
                 updated_at = excluded.updated_at""",
            (self.current_week_start(), wins, challenges, next_steps, utcnow()),
        )
        self.conn.commit()

    def current_review(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM reviews WHERE week_start = ?", (self.current_week_start(),)
        ).fetchone()

    # ------------------------------------------------------------------ stats
    def dashboard(self) -> dict[str, Any]:
        task_counts = {
            row["status"]: row["count"]
            for row in self.conn.execute(
                "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
            )
        }
        open_tasks = int(task_counts.get("todo", 0) + task_counts.get("doing", 0))
        next_task = self.conn.execute(
            "SELECT * FROM tasks WHERE status != 'done' ORDER BY CASE status WHEN 'doing' THEN 0 ELSE 1 END, created_at LIMIT 1"
        ).fetchone()
        inbox_open = self.conn.execute(
            "SELECT COUNT(*) AS n FROM inbox WHERE state = 'open'"
        ).fetchone()["n"]
        return {
            "open_tasks": open_tasks,
            "done_tasks": int(task_counts.get("done", 0)),
            "next_task": next_task,
            "inbox_open": int(inbox_open),
            "focus": self.focus_stats(),
            "water": self.water_today(),
            "mood": self.mood_stats(),
        }

    def report(self) -> dict[str, Any]:
        task_rows = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done FROM tasks"
        ).fetchone()
        focus = self.focus_stats()
        water = self.conn.execute(
            "SELECT COALESCE(SUM(amount_ml), 0) AS total FROM water_logs WHERE kind='water'"
        ).fetchone()
        mood = self.mood_stats()
        return {
            "tasks": int(task_rows["total"] or 0),
            "done": int(task_rows["done"] or 0),
            "focus_minutes": focus["minutes"],
            "focus_sessions": focus["sessions"],
            "water_ml": int(water["total"] or 0),
            "mood": mood["mood"],
            "mood_entries": mood["entries"],
        }
