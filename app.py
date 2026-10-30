"""Fábrica da aplicação PRD//SUITE.

Execução local:  ``flask --app app run --debug``
Produção:        ``gunicorn --config gunicorn.conf.py app:app``
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click
from flask import Flask, flash, jsonify, redirect, request, url_for
from flask_login import current_user
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine

from config import Config
from extensions import csrf, db, login_manager
from models import Task, User
from security import (
    init_error_handlers,
    init_security_headers,
    init_session_guard,
)
from services.timeutils import app_timezone, format_minutes, local_today, to_local

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# SQLite: WAL para leitura concorrente + integridade referencial + timeout.
# O listener é global e registrado uma única vez.
# --------------------------------------------------------------------------
@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
    finally:
        cursor.close()


def _ensure_sqlite_directory(app: Flask) -> None:
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:///"):
        return
    path = uri.removeprefix("sqlite:///")
    if path and path != ":memory:":
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _greeting() -> str:
    hour = datetime.now(timezone.utc).astimezone(app_timezone()).hour
    if hour < 12:
        return "Bom dia"
    if hour < 18:
        return "Boa tarde"
    return "Boa noite"


def ensure_schema() -> None:
    """Migração leve e idempotente para instalações SQLite existentes.

    ``db.create_all`` cria tabelas novas, mas não altera tabelas já existentes.
    Como esta suíte não usa Alembic na v1, adicionamos as colunas de
    planejamento manualmente, preservando os dados. Para evoluções futuras,
    o caminho recomendado é introduzir migrações versionadas.
    """
    if db.engine.url.get_backend_name() != "sqlite":
        return

    table_columns = {
        "tasks": {
            "planned_for": "DATE",
            "category": "VARCHAR(20) NOT NULL DEFAULT 'work'",
            "quadrant": "VARCHAR(20)",
            "is_mit": "BOOLEAN NOT NULL DEFAULT 0",
            "column_id": "INTEGER",
            "column_entered_at": "DATETIME",
            "project_id": "INTEGER",
        },
        "board_columns": {
            "project_id": "INTEGER",
        },
        "users": {
            "weekly_focus_goal": "INTEGER NOT NULL DEFAULT 12",
            "legacy_done_migrated": "BOOLEAN NOT NULL DEFAULT 0",
            "onboarding_completed": "BOOLEAN NOT NULL DEFAULT 1",
            "display_name": "VARCHAR(80)",
        },
    }

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    with db.engine.begin() as connection:
        for table, columns in table_columns.items():
            if table not in existing_tables:
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table)
            }
            for name, ddl in columns.items():
                if name not in existing_columns:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}')
                    )
        if "users" in existing_tables:
            connection.execute(
                text(
                    "UPDATE users SET display_name = username "
                    "WHERE display_name IS NULL OR TRIM(display_name) = ''"
                )
            )
        if "tasks" in existing_tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_tasks_user_planned "
                    "ON tasks (user_id, planned_for)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_tasks_user_column "
                    "ON tasks (user_id, column_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_tasks_user_project "
                    "ON tasks (user_id, project_id)"
                )
            )
        if "board_columns" in existing_tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_board_columns_project "
                    "ON board_columns (project_id)"
                )
            )
        if (
            "board_columns" in existing_tables
            and "tasks" in existing_tables
            and "users" in existing_tables
        ):
            # Migração única para quadros antigos: antes do seletor de coluna
            # de conclusão, quadros chamavam a última coluna de "Done" sem
            # marcar o tipo. Preserva a intenção de quem já usava esse nome.
            candidates = connection.execute(
                text(
                    """
                    SELECT c.id, c.project_id, c.user_id
                    FROM board_columns c
                    JOIN users u ON u.id = c.user_id
                    WHERE u.legacy_done_migrated = 0
                      AND lower(trim(c.title)) IN (
                        'done', 'concluido', 'concluído', 'concluida',
                        'concluída', 'concluidas', 'concluídas', 'feito',
                        'finalizado', 'finalizada', 'completed', 'complete'
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM board_columns d
                        WHERE d.project_id = c.project_id
                          AND d.kind = 'done'
                      )
                    ORDER BY c.project_id ASC, c.position DESC, c.id DESC
                    """
                )
            ).fetchall()
            seen_projects: set[int] = set()
            for column_id, project_id, _user_id in candidates:
                if project_id in seen_projects:
                    continue
                seen_projects.add(project_id)
                connection.execute(
                    text("UPDATE board_columns SET kind = 'done' WHERE id = :id"),
                    {"id": column_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE tasks
                        SET status = 'done',
                            completed_at = COALESCE(
                                completed_at, updated_at, created_at, CURRENT_TIMESTAMP
                            )
                        WHERE column_id = :id AND status != 'done'
                        """
                    ),
                    {"id": column_id},
                )
            connection.execute(
                text("UPDATE users SET legacy_done_migrated = 1")
            )


def create_app(config_override: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    _ensure_sqlite_directory(app)

    secret_key = str(app.config.get("SECRET_KEY") or "")
    if not app.config.get("TESTING") and (
        secret_key == "dev-insecure-change-me"
        or secret_key.startswith("troque-por")
        or len(secret_key) < 32
    ):
        logger.warning(
            "SECRET_KEY fraca/padrão em uso. Gere uma chave de 32+ bytes e "
            "defina SECRET_KEY no ambiente antes de expor a aplicação."
        )

    # ---------------------------------------------------------- extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def _load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def _unauthorized():
        # Requisições JSON (timer/HUD) recebem 401 em vez de redirect HTML.
        if (
            request.path.startswith("/foco/ciclos")
            or request.is_json
            or request.accept_mimetypes.best == "application/json"
        ):
            return jsonify(ok=False, error="Autenticação necessária."), 401
        flash(login_manager.login_message, "warning")
        return redirect(
            url_for("auth.login", next=request.full_path.rstrip("?"))
        )

    # ------------------------------------------------------------- rotas
    from routes.auth import auth_bp
    from routes.dashboard import main_bp
    from routes.export import export_bp
    from routes.help import help_bp
    from routes.notes import notes_bp
    from routes.onboarding import onboarding_bp
    from routes.planner import planner_bp
    from routes.pomodoro import pomodoro_bp
    from routes.review import review_bp
    from routes.scratchpad import scratchpad_bp
    from routes.tasks import tasks_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(pomodoro_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(scratchpad_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(export_bp)

    # ----------------------------------------------------- segurança/erros
    init_security_headers(app)
    init_session_guard(app)
    init_error_handlers(app)

    # --------------------------------------------------- helpers de template
    @app.template_filter("localtime")
    def _localtime(value, fmt: str = "%d/%m/%Y %H:%M"):
        local = to_local(value)
        return local.strftime(fmt) if local else "—"

    @app.template_filter("datebr")
    def _datebr(value):
        if not value:
            return "—"
        return value.strftime("%d/%m/%Y")

    @app.template_filter("minutes")
    def _minutes(value):
        return format_minutes(value)

    @app.template_filter("initials")
    def _initials(value: str):
        return (value or "?")[:2].upper()

    @app.context_processor
    def _inject_globals():
        data = {
            "app_name": app.config.get("APP_NAME", "PRD//SUITE"),
            "current_year": datetime.now(timezone.utc).year,
            "today_local": local_today(),
            "greeting": _greeting(),
            "allow_registration": app.config.get("ALLOW_REGISTRATION", True),
            "show_onboarding": False,
        }
        if current_user.is_authenticated:
            from forms import ScratchpadForm, SearchForm

            data["show_onboarding"] = bool(
                not current_user.onboarding_completed
                or request.args.get("tour") == "1"
            )
            data["hud_tasks"] = (
                Task.query.filter(
                    Task.user_id == current_user.id, Task.status != "done"
                )
                .order_by(Task.updated_at.desc())
                .limit(30)
                .all()
            )
            data["nav_pending"] = Task.query.filter(
                Task.user_id == current_user.id, Task.status != "done"
            ).count()
            data["capture_form"] = ScratchpadForm()
            data["search_form"] = SearchForm()
        return data

    # --------------------------------------------------------------- CLI
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Cria/migra as tabelas (idempotente)."""
        db.create_all()
        ensure_schema()
        click.echo("Banco inicializado.")

    @app.cli.command("create-user")
    @click.option("--username", prompt=True, help="Nome de acesso")
    @click.option("--name", prompt="Nome de perfil", help="Como a pessoa será chamada")
    @click.option("--email", prompt=True, help="E-mail")
    @click.password_option(help="Senha")
    def create_user_command(
        username: str, name: str, email: str, password: str
    ) -> None:
        """Cria um usuário manualmente (útil no primeiro deploy)."""
        db.create_all()
        if User.query.filter(
            (User.username == username) | (User.email == email)
        ).first():
            raise click.ClickException("Usuário ou e-mail já existe.")
        user = User(
            username=username.strip(),
            display_name=name.strip() or username.strip(),
            email=email.strip().lower(),
            onboarding_completed=False,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Usuário {user.username} criado.")

    # Criação idempotente no boot. O container roda init-db antes do Gunicorn,
    # mas isso mantém o modo local e os testes simples.
    if app.config.get("CREATE_DB_ON_START", True):
        with app.app_context():
            db.create_all()
            ensure_schema()

    return app


# Instância para ``gunicorn app:app`` e ``flask --app app``.
app = create_app()


if __name__ == "__main__":  # pragma: no cover
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
