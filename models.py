"""Modelos de domínio (SQLAlchemy).

Convenções:
* Datas são persistidas em **UTC naive** (SQLite não guarda timezone). A
  conversão para o fuso configurado acontece na camada de apresentação.
* Toda consulta feita nas rotas filtra por ``user_id``: o isolamento entre
  contas é uma regra de negócio, não uma cortesia da UI.
* Regras de transição de estado ficam nos métodos do modelo para poderem ser
  testadas sem HTTP.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

# --------------------------------------------------------------------------
# Constantes de domínio
# --------------------------------------------------------------------------
TASK_STATUSES = ("todo", "doing", "done")
TASK_STATUS_LABELS = {
    "todo": "A fazer",
    "doing": "Em andamento",
    "done": "Concluídas",
}
TASK_PRIORITIES = ("low", "medium", "high", "urgent")
TASK_PRIORITY_LABELS = {
    "low": "Baixa",
    "medium": "Média",
    "high": "Alta",
    "urgent": "Urgente",
}
# Matriz de Eisenhower: o que fazer com cada combinação de urgência/importância.
TASK_QUADRANTS = ("do", "schedule", "delegate", "eliminate")
TASK_QUADRANT_LABELS = {
    "do": "Fazer agora",
    "schedule": "Agendar",
    "delegate": "Delegar",
    "eliminate": "Deixar de lado",
}
TASK_QUADRANT_HINTS = {
    "do": "Urgente e importante",
    "schedule": "Importante, não urgente",
    "delegate": "Urgente, não importante",
    "eliminate": "Nem urgente, nem importante",
}
TASK_CATEGORIES = ("work", "study", "personal")
TASK_CATEGORY_LABELS = {
    "work": "Trabalho",
    "study": "Estudos",
    "personal": "Pessoal",
}
TASK_CATEGORY_ICONS = {
    "work": "bi-briefcase",
    "study": "bi-mortarboard",
    "personal": "bi-house-heart",
}
POMODORO_MODES = ("focus", "short_break", "long_break")
POMODORO_MODE_LABELS = {
    "focus": "Foco",
    "short_break": "Pausa curta",
    "long_break": "Pausa longa",
}
POMODORO_DURATIONS = {"focus": 25, "short_break": 5, "long_break": 20}


def utcnow() -> datetime:
    """UTC sem tzinfo, formato seguro para colunas DateTime no SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_tags(raw: str | None) -> str:
    """Normaliza tags: minúsculas, sem duplicatas, separadas por vírgula.

    A normalização evita que "Foco" e "foco" virem tags diferentes e limita o
    tamanho total para caber na coluna.
    """
    if not raw:
        return ""
    seen: set[str] = set()
    cleaned: list[str] = []
    for part in raw.replace(";", ",").split(","):
        tag = " ".join(part.strip().lower().split())
        tag = tag.lstrip("#")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag[:30])
        if len(", ".join(cleaned)) > 240:
            break
    return ", ".join(cleaned)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False, default="")
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # Nonce de sessão: rotacioná-lo invalida todas as sessões antigas.
    session_nonce = db.Column(
        db.String(64), nullable=False, default=lambda: secrets.token_hex(16)
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    last_login_at = db.Column(db.DateTime, nullable=True)

    tasks = db.relationship(
        "Task",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    notes = db.relationship(
        "Note",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    scratchpads = db.relationship(
        "Scratchpad",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    cycles = db.relationship(
        "PomodoroCycle",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    weekly_reviews = db.relationship(
        "WeeklyReview",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    board_columns = db.relationship(
        "BoardColumn",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="BoardColumn.position",
    )
    categories = db.relationship(
        "Category",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="Category.position",
    )
    projects = db.relationship(
        "Project",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="Project.position",
    )
    # Meta semanal de sessões de foco (SMART: mensurável e com prazo).
    weekly_focus_goal = db.Column(db.Integer, nullable=False, default=12)
    # Migração única de quadros antigos que usavam "Done" sem marcar o tipo.
    legacy_done_migrated = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.true()
    )
    # Contas antigas não são surpreendidas pelo tutorial; novas contas
    # recebem False explicitamente no registro.
    onboarding_completed = db.Column(db.Boolean, nullable=False, default=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Contas antigas e usuários criados por ferramentas internas ganham
        # um nome de perfil utilizável, sem exibir o nome de acesso na saudação.
        if not self.display_name:
            self.display_name = self.username or ""

    # ----------------------------------------------------------- credenciais
    def set_password(self, password: str) -> None:
        method = current_app.config.get(
            "PASSWORD_HASH_METHOD", "pbkdf2:sha256:600000"
        )
        self.password_hash = generate_password_hash(password, method=method)

    def check_password(self, password: str) -> bool:
        if not self.password_hash or not password:
            return False
        return check_password_hash(self.password_hash, password)

    def rotate_session_nonce(self) -> str:
        """Invalida sessões existentes (usado em troca de senha/logout global)."""
        self.session_nonce = secrets.token_hex(16)
        return self.session_nonce

    @property
    def initials(self) -> str:
        base = (self.display_name or self.username or "?").strip()
        parts = [p for p in base.replace("_", " ").replace("-", " ").split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return base[:2].upper()

    def __repr__(self) -> str:  # pragma: no cover - depuração
        return f"<User {self.username}>"


class Project(db.Model):
    """Um quadro/projeto com as suas próprias colunas e tarefas."""

    __tablename__ = "projects"
    __table_args__ = (
        db.Index("ix_projects_user_position", "user_id", "position"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(60), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    owner = db.relationship("User", back_populates="projects")
    columns = db.relationship(
        "BoardColumn",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="BoardColumn.position",
    )
    tasks = db.relationship("Task", back_populates="project", lazy="dynamic")

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "position": self.position,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.id} {self.name!r}>"


class BoardColumn(db.Model):
    """Uma coluna personalizada do quadro de tarefas."""

    __tablename__ = "board_columns"
    __table_args__ = (
        db.CheckConstraint(
            "kind IN ('todo', 'doing', 'done')", name="ck_board_columns_kind"
        ),
        db.Index("ix_board_columns_user_position", "user_id", "position"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(50), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="todo")
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    owner = db.relationship("User", back_populates="board_columns")
    project = db.relationship("Project", back_populates="columns")
    tasks = db.relationship("Task", back_populates="column", lazy="dynamic")

    @property
    def kind_label(self) -> str:
        return TASK_STATUS_LABELS.get(self.kind, self.kind)

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "kind_label": self.kind_label,
            "position": self.position,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BoardColumn {self.id} {self.title!r}>"


class Category(db.Model):
    """Categoria personalizada de tarefas, com chave estável e nome editável."""

    __tablename__ = "categories"
    __table_args__ = (
        db.UniqueConstraint("user_id", "key", name="uq_categories_user_key"),
        db.Index("ix_categories_user_position", "user_id", "position"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(40), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="bi-tag")
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    owner = db.relationship("User", back_populates="categories")

    def to_export_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "icon": self.icon,
            "position": self.position,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.key} {self.name!r}>"


class Task(db.Model):
    __tablename__ = "tasks"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('todo', 'doing', 'done')", name="ck_tasks_status"
        ),
        db.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="ck_tasks_priority",
        ),
        db.Index("ix_tasks_user_status", "user_id", "status"),
        db.Index("ix_tasks_user_column", "user_id", "column_id"),
        db.Index("ix_tasks_user_due", "user_id", "due_date"),
        db.Index("ix_tasks_user_planned", "user_id", "planned_for"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="todo", index=True)
    column_id = db.Column(
        db.Integer,
        db.ForeignKey("board_columns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    column_entered_at = db.Column(db.DateTime, nullable=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    priority = db.Column(db.String(20), nullable=False, default="medium")
    estimate_pomodoros = db.Column(db.Integer, nullable=False, default=1)
    completed_pomodoros = db.Column(db.Integer, nullable=False, default=0)
    due_date = db.Column(db.Date, nullable=True)
    # Planejamento do dia (time blocking leve) e classificação do método.
    planned_for = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(20), nullable=False, default="work")
    quadrant = db.Column(db.String(20), nullable=True)
    is_mit = db.Column(db.Boolean, nullable=False, default=False, index=True)
    tags = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    owner = db.relationship("User", back_populates="tasks")
    column = db.relationship("BoardColumn", back_populates="tasks")
    column_stays = db.relationship(
        "TaskColumnStay",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    project = db.relationship("Project", back_populates="tasks")
    category_ref = db.relationship(
        "Category",
        primaryjoin=(
            "and_(foreign(Task.category) == Category.key, "
            "Task.user_id == Category.user_id)"
        ),
        viewonly=True,
        uselist=False,
    )
    cycles = db.relationship(
        "PomodoroCycle",
        back_populates="task",
        passive_deletes=True,
        lazy="dynamic",
    )

    # ------------------------------------------------------------- transições
    def move_to(self, status: str, when: datetime | None = None) -> None:
        """Move a tarefa e mantém ``completed_at`` coerente.

        Reabrir uma tarefa concluída limpa a data de conclusão; concluir de
        novo registra um novo instante.
        """
        if status not in TASK_STATUSES:
            raise ValueError(f"status inválido: {status!r}")
        if status == "done":
            if self.completed_at is None:
                self.completed_at = when or utcnow()
        else:
            self.completed_at = None
        self.status = status
        self.updated_at = utcnow()

    @property
    def is_done(self) -> bool:
        return self.status == "done"

    @property
    def status_label(self) -> str:
        return TASK_STATUS_LABELS.get(self.status, self.status)

    @property
    def is_overdue(self) -> bool:
        if not self.due_date or self.is_done:
            return False
        try:
            tz = ZoneInfo(current_app.config.get("APP_TIMEZONE", "UTC"))
        except ZoneInfoNotFoundError:  # pragma: no cover
            tz = timezone.utc
        today = datetime.now(timezone.utc).astimezone(tz).date()
        return self.due_date < today

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def priority_rank(self) -> int:
        return {"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(self.priority, 4)

    @property
    def quadrant_rank(self) -> int:
        return {"do": 0, "schedule": 1, "delegate": 2, "eliminate": 3}.get(
            self.quadrant, 4
        )

    @property
    def estimate_label(self) -> str:
        n = self.estimate_pomodoros or 0
        return f"{n} sessão de foco" if n == 1 else f"{n} sessões de foco"

    @property
    def category_label(self) -> str:
        if self.category_ref:
            return self.category_ref.name
        return TASK_CATEGORY_LABELS.get(self.category, "Geral")

    @property
    def category_icon(self) -> str:
        if self.category_ref:
            return self.category_ref.icon
        return TASK_CATEGORY_ICONS.get(self.category, "bi-grid")

    @property
    def quadrant_label(self) -> str:
        return TASK_QUADRANT_LABELS.get(self.quadrant, "Sem classificação")

    @property
    def quadrant_hint(self) -> str:
        return TASK_QUADRANT_HINTS.get(self.quadrant, "Classifique na matriz")

    @property
    def is_quick_win(self) -> bool:
        """Tarefa curta: estimativa de até uma sessão de foco."""
        return (self.estimate_pomodoros or 0) <= 1

    @property
    def is_planned_today(self) -> bool:
        from services.timeutils import local_today

        return self.planned_for == local_today()

    @property
    def progress_percent(self) -> int:
        estimate = max(self.estimate_pomodoros or 0, 1)
        return min(100, round((self.completed_pomodoros or 0) / estimate * 100))

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "status_label": TASK_STATUS_LABELS[self.status],
            "column_id": self.column_id,
            "column_title": self.column.title if self.column else None,
            "project_id": self.project_id,
            "project_title": self.project.name if self.project else None,
            "column_entered_at": (
                self.column_entered_at.isoformat()
                if self.column_entered_at
                else None
            ),
            "priority": self.priority,
            "priority_label": TASK_PRIORITY_LABELS[self.priority],
            "estimate_pomodoros": self.estimate_pomodoros,
            "completed_pomodoros": self.completed_pomodoros,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "planned_for": self.planned_for.isoformat() if self.planned_for else None,
            "category": self.category,
            "category_label": self.category_label,
            "quadrant": self.quadrant,
            "quadrant_label": self.quadrant_label,
            "is_mit": self.is_mit,
            "is_quick_win": self.is_quick_win,
            "tags": self.tag_list,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Task {self.id} {self.title!r} [{self.status}]>"


class TaskColumnStay(db.Model):
    """Tempo histórico de uma tarefa em uma coluna do kanban."""

    __tablename__ = "task_column_stays"
    __table_args__ = (
        db.Index("ix_task_column_stays_user_task", "user_id", "task_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    project_id = db.Column(db.Integer, nullable=True)
    column_id = db.Column(db.Integer, nullable=True)
    column_title = db.Column(db.String(50), nullable=False)
    entered_at = db.Column(db.DateTime, nullable=False)
    left_at = db.Column(db.DateTime, nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False, default=0)

    task = db.relationship("Task", back_populates="column_stays")

    @property
    def duration_label(self) -> str:
        total = max(0, int(self.duration_seconds or 0))
        hours, remainder = divmod(total, 3600)
        minutes = remainder // 60
        if hours:
            return f"{hours}h {minutes:02d}min"
        if minutes:
            return f"{minutes} min"
        return f"{total}s"

    def to_export_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "column_id": self.column_id,
            "column_title": self.column_title,
            "entered_at": self.entered_at.isoformat() if self.entered_at else None,
            "left_at": self.left_at.isoformat() if self.left_at else None,
            "duration_seconds": self.duration_seconds,
        }


class PomodoroCycle(db.Model):
    __tablename__ = "pomodoro_cycles"
    __table_args__ = (
        db.CheckConstraint(
            "mode IN ('focus', 'short_break', 'long_break')",
            name="ck_cycles_mode",
        ),
        db.Index("ix_cycles_user_ended", "user_id", "ended_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode = db.Column(db.String(20), nullable=False, default="focus")
    duration_minutes = db.Column(db.Integer, nullable=False, default=25)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    completed = db.Column(db.Boolean, nullable=False, default=True)

    owner = db.relationship("User", back_populates="cycles")
    task = db.relationship("Task", back_populates="cycles")

    @property
    def mode_label(self) -> str:
        return POMODORO_MODE_LABELS.get(self.mode, self.mode)

    @property
    def icon(self) -> str:
        return {
            "focus": "bi-lightning-charge",
            "short_break": "bi-cup-hot",
            "long_break": "bi-moon-stars",
        }.get(self.mode, "bi-clock")

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "mode": self.mode,
            "mode_label": self.mode_label,
            "duration_minutes": self.duration_minutes,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "completed": self.completed,
            "task_id": self.task_id,
            "task_title": self.task.title if self.task else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cycle {self.id} {self.mode} {self.duration_minutes}min>"


class Scratchpad(db.Model):
    __tablename__ = "scratchpads"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content = db.Column(db.Text, nullable=False)
    converted_task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    owner = db.relationship("User", back_populates="scratchpads")
    converted_task = db.relationship("Task", foreign_keys=[converted_task_id])

    @property
    def is_converted(self) -> bool:
        return self.converted_task_id is not None

    @property
    def preview(self) -> str:
        text = " ".join((self.content or "").split())
        return text[:160] + ("…" if len(text) > 160 else "")

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "converted_task_id": self.converted_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Scratchpad {self.id}>"


class Note(db.Model):
    __tablename__ = "notes"
    __table_args__ = (db.Index("ix_notes_user_updated", "user_id", "updated_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    tags = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow, index=True
    )

    owner = db.relationship("User", back_populates="notes")

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def excerpt(self) -> str:
        import re

        text = re.sub(r"[#*_>`\[\]()!-]+", " ", self.body or "")
        text = " ".join(text.split())
        return text[:180] + ("…" if len(text) > 180 else "")

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "tags": self.tag_list,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Note {self.id} {self.title!r}>"


class WeeklyReview(db.Model):
    """Revisão semanal leve: o que funcionou, o que pesou e o próximo foco."""

    __tablename__ = "weekly_reviews"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "week_start", name="uq_weekly_review_user_week"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    week_start = db.Column(db.Date, nullable=False, index=True)
    wins = db.Column(db.Text, nullable=False, default="")
    challenges = db.Column(db.Text, nullable=False, default="")
    next_steps = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    owner = db.relationship("User", back_populates="weekly_reviews")

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "week_start": self.week_start.isoformat(),
            "wins": self.wins,
            "challenges": self.challenges,
            "next_steps": self.next_steps,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WeeklyReview {self.week_start}>"
