"""Extensões compartilhadas.

Ficam em um módulo separado para evitar import circular entre ``app``,
``models`` e ``routes``.
"""

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# Redireciona usuários anônimos para o login em vez de devolver 401.
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar a suíte."
login_manager.login_message_category = "warning"
# "strong" invalida a sessão quando o IP/user-agent mudam de forma suspeita.
login_manager.session_protection = "strong"
