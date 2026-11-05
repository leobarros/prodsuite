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
    position = db.Column(db.Integer, nullable=False, default=0, index=True)
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
    # Rotina diária: aparece em Blocos de hoje enquanto estiver aberta.
    repeat_daily = db.Column(db.Boolean, nullable=False, default=False, index=True)
    daily_target_pomodoros = db.Column(db.Integer, nullable=False, default=1)
    category = db.Column(db.String(20), nullable=False, default="work")
    quadrant = db.Column(db.String(20), nullable=True)
    is_mit = db.Column(db.Boolean, nullable=False, default=False, index=True)
    tags = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    completed_at = db.Column(db.DateTime, nullable=True)
    archived_at = db.Column(db.DateTime, nullable=True, index=True)
    archived_week = db.Column(db.Date, nullable=True, index=True)

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
    comments = db.relationship(
        "TaskComment",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="dynamic",
    )
    attachments = db.relationship(
        "TaskAttachment",
        back_populates="task",
        cascade="all, delete-orphan",
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
    def is_archived(self) -> bool:
        return self.archived_at is not None

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
    def daily_target(self) -> int:
        return max(1, min(8, int(self.daily_target_pomodoros or 1)))

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
            "position": self.position,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "archived_week": (
                self.archived_week.isoformat() if self.archived_week else None
            ),
            "priority": self.priority,
            "priority_label": TASK_PRIORITY_LABELS[self.priority],
            "estimate_pomodoros": self.estimate_pomodoros,
            "completed_pomodoros": self.completed_pomodoros,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "planned_for": self.planned_for.isoformat() if self.planned_for else None,
            "repeat_daily": self.repeat_daily,
            "daily_target_pomodoros": self.daily_target,
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


class MoodEntry(db.Model):
    """Um check-in pessoal de humor e contexto."""

    __tablename__ = "mood_entries"
    __table_args__ = (
        db.CheckConstraint("mood BETWEEN 1 AND 5", name="ck_mood_mood"),
        db.CheckConstraint("energy BETWEEN 1 AND 5", name="ck_mood_energy"),
        db.CheckConstraint("tension BETWEEN 1 AND 5", name="ck_mood_tension"),
        db.Index("ix_mood_entries_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mood = db.Column(db.Integer, nullable=False, default=3)
    energy = db.Column(db.Integer, nullable=False, default=3)
    tension = db.Column(db.Integer, nullable=False, default=2)
    contexts = db.Column(db.String(255), nullable=False, default="")
    note = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "mood": self.mood,
            "energy": self.energy,
            "tension": self.tension,
            "contexts": self.contexts,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MoodEntry {self.mood}/5 user={self.user_id}>"


class WaterSettings(db.Model):
    """Preferências e faixa pessoal de hidratação."""

    __tablename__ = "water_settings"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    weight_kg = db.Column(db.Float, nullable=True)
    extra_ml = db.Column(db.Integer, nullable=False, default=0)
    reminders_enabled = db.Column(db.Boolean, nullable=False, default=False)
    reminder_interval_minutes = db.Column(db.Integer, nullable=False, default=90)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WaterSettings user={self.user_id}>"


class WaterLog(db.Model):
    """Um registro de água bebida."""

    __tablename__ = "water_logs"
    __table_args__ = (
        db.Index("ix_water_logs_user_logged", "user_id", "logged_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount_ml = db.Column(db.Integer, nullable=False, default=200)
    logged_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "amount_ml": self.amount_ml,
            "logged_at": self.logged_at.isoformat() if self.logged_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WaterLog {self.amount_ml}ml user={self.user_id}>"


class PomodoroTimer(db.Model):
    """Estado compartilhado de um único Pomodoro por usuário."""

    __tablename__ = "pomodoro_timers"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode = db.Column(db.String(20), nullable=False, default="focus")
    duration_seconds = db.Column(db.Integer, nullable=False, default=1500)
    remaining_seconds = db.Column(db.Integer, nullable=False, default=1500)
    ends_at = db.Column(db.DateTime, nullable=True)
    running = db.Column(db.Boolean, nullable=False, default=False)
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    run_id = db.Column(db.String(64), nullable=True)
    revision = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    task = db.relationship("Task", foreign_keys=[task_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PomodoroTimer user={self.user_id} {self.mode} running={self.running}>"


class TaskComment(db.Model):
    """Comentário privado de progresso/problema em uma tarefa."""

    __tablename__ = "task_comments"
    __table_args__ = (
        db.Index("ix_task_comments_task_created", "task_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    body = db.Column(db.String(2000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    task = db.relationship("Task", back_populates="comments")
    attachments = db.relationship(
        "TaskAttachment",
        back_populates="comment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="dynamic",
    )

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "body": self.body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TaskComment {self.id} task={self.task_id}>"


class TaskAttachment(db.Model):
    """Arquivo privado anexado a uma tarefa ou comentário."""

    __tablename__ = "task_attachments"
    __table_args__ = (
        db.Index("ix_task_attachments_task_created", "task_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    comment_id = db.Column(
        db.Integer, db.ForeignKey("task_comments.id", ondelete="CASCADE"), nullable=True
    )
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    mime_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    task = db.relationship("Task", back_populates="attachments")
    comment = db.relationship("TaskComment", back_populates="attachments")

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    @property
    def size_label(self) -> str:
        size = max(0, int(self.size_bytes or 0))
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size / (1024 * 1024):.1f} MB".replace(".", ",")

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "comment_id": self.comment_id,
            "original_name": self.original_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TaskAttachment {self.id} task={self.task_id}>"


class PomodoroCycle(db.Model):
    __tablename__ = "pomodoro_cycles"
    __table_args__ = (
        db.CheckConstraint(
            "mode IN ('focus', 'short_break', 'long_break')",
            name="ck_cycles_mode",
        ),
        db.Index("ix_cycles_user_ended", "user_id", "ended_at"),
        db.UniqueConstraint("user_id", "run_id", name="uq_cycles_user_run"),
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
    run_id = db.Column(db.String(64), nullable=True, index=True)

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
            "run_id": self.run_id,
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
    completed_at = db.Column(db.DateTime, nullable=True, index=True)
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
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def preview(self) -> str:
        text = " ".join((self.content or "").split())
        return text[:160] + ("…" if len(text) > 160 else "")

    def to_export_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "converted_task_id": self.converted_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

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
