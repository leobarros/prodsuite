"""Blueprints da aplicação."""

from .auth import auth_bp
from .dashboard import main_bp
from .export import export_bp
from .notes import notes_bp
from .planner import planner_bp
from .pomodoro import pomodoro_bp
from .review import review_bp
from .reports import reports_bp
from .scratchpad import scratchpad_bp
from .tasks import tasks_bp
from .water import water_bp
from .mood import mood_bp

__all__ = [
    "auth_bp",
    "main_bp",
    "tasks_bp",
    "pomodoro_bp",
    "scratchpad_bp",
    "notes_bp",
    "planner_bp",
    "review_bp",
    "reports_bp",
    "export_bp",
    "water_bp",
    "mood_bp",
]
