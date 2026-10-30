"""Formulários WTForms com validação e mensagens em português.

Toda entrada de usuário passa por aqui (ou por validação equivalente nas
rotas JSON). O CSRF é injetado automaticamente pelo ``Flask-WTF``.
"""

from __future__ import annotations

import re

from flask import current_app
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import (
    BooleanField,
    DateField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from models import (
    TASK_QUADRANTS,
    TASK_QUADRANT_HINTS,
    TASK_QUADRANT_LABELS,
    TASK_STATUSES,
    TASK_STATUS_LABELS,
    User,
)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def strip_filter(value):
    return value.strip() if isinstance(value, str) else value


def unique_username(form, field):
    exists = (
        User.query.filter(func.lower(User.username) == field.data.strip().lower())
        .with_entities(User.id)
        .first()
    )
    if exists:
        raise ValidationError("Este nome de usuário já está em uso.")


def unique_email(form, field):
    exists = (
        User.query.filter(func.lower(User.email) == field.data.strip().lower())
        .with_entities(User.id)
        .first()
    )
    if exists:
        raise ValidationError("Este e-mail já está cadastrado.")


def password_min_length(form, field):
    """Aplica a política de tamanho mínimo (padrão: 4 caracteres).

    O limite é configurável por ``PASSWORD_MIN_LENGTH`` para que instalações
    expostas publicamente possam endurecer a política sem mudar código.
    """
    minimum = int(current_app.config.get("PASSWORD_MIN_LENGTH", 4))
    if len(field.data or "") < minimum:
        raise ValidationError(
            f"A senha precisa ter no mínimo {minimum} caracteres."
        )


class RegisterForm(FlaskForm):
    display_name = StringField(
        "Como podemos te chamar?",
        filters=[strip_filter],
        validators=[
            DataRequired("Informe o nome que devemos usar para te chamar."),
            Length(min=2, max=80, message="Use entre 2 e 80 caracteres."),
        ],
        render_kw={
            "autocomplete": "name",
            "placeholder": "ex.: Ana",
        },
    )
    username = StringField(
        "Nome de acesso",
        filters=[strip_filter],
        validators=[
            DataRequired("Informe um nome de acesso."),
            Length(min=3, max=32, message="Use entre 3 e 32 caracteres."),
            Regexp(
                USERNAME_RE,
                message="Use apenas letras, números, ponto, hífen ou sublinhado.",
            ),
            unique_username,
        ],
        render_kw={
            "autocomplete": "username",
            "autocapitalize": "none",
            "spellcheck": "false",
            "placeholder": "ex.: ana.dev",
        },
    )
    email = StringField(
        "E-mail",
        filters=[strip_filter],
        validators=[
            DataRequired("Informe seu e-mail."),
            Email(message="E-mail inválido."),
            Length(max=255),
            unique_email,
        ],
        render_kw={
            "autocomplete": "email",
            "inputmode": "email",
            "autocapitalize": "none",
            "spellcheck": "false",
            "placeholder": "voce@dominio.com",
        },
    )
    password = PasswordField(
        "Senha",
        validators=[
            DataRequired("Crie uma senha."),
            Length(max=128, message="Máximo de 128 caracteres."),
            password_min_length,
        ],
        render_kw={"autocomplete": "new-password", "placeholder": "Mín. 4 caracteres"},
    )
    confirm = PasswordField(
        "Confirmar senha",
        validators=[
            DataRequired("Confirme a senha."),
            EqualTo("password", message="As senhas não conferem."),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    submit = SubmitField("Criar conta")


class LoginForm(FlaskForm):
    identifier = StringField(
        "E-mail ou nome de acesso",
        filters=[strip_filter],
        validators=[DataRequired("Informe seu e-mail ou nome de acesso."), Length(max=255)],
        render_kw={
            "autocomplete": "username",
            "autocapitalize": "none",
            "spellcheck": "false",
            "placeholder": "e-mail ou nome de acesso",
        },
    )
    password = PasswordField(
        "Senha",
        validators=[
            DataRequired("Informe a senha."),
            Length(max=128, message="Máximo de 128 caracteres."),
        ],
        render_kw={"autocomplete": "current-password"},
    )
    submit = SubmitField("Entrar")


class DisplayNameForm(FlaskForm):
    display_name = StringField(
        "Nome de perfil",
        filters=[strip_filter],
        validators=[
            DataRequired("Informe o nome que devemos usar para te chamar."),
            Length(min=2, max=80, message="Use entre 2 e 80 caracteres."),
        ],
        render_kw={
            "autocomplete": "name",
            "placeholder": "ex.: Ana",
        },
    )
    submit = SubmitField("Salvar nome")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Senha atual",
        validators=[
            DataRequired("Informe a senha atual."),
            Length(max=128, message="Máximo de 128 caracteres."),
        ],
        render_kw={"autocomplete": "current-password"},
    )
    new_password = PasswordField(
        "Nova senha",
        validators=[
            DataRequired("Informe a nova senha."),
            Length(max=128, message="Máximo de 128 caracteres."),
            password_min_length,
        ],
        render_kw={"autocomplete": "new-password"},
    )
    confirm = PasswordField(
        "Confirmar nova senha",
        validators=[
            DataRequired("Confirme a nova senha."),
            EqualTo("new_password", message="As senhas não conferem."),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    submit = SubmitField("Atualizar senha")


class TaskForm(FlaskForm):
    title = StringField(
        "Título",
        filters=[strip_filter],
        validators=[
            DataRequired("Dê um título à tarefa."),
            Length(max=160, message="Máximo de 160 caracteres."),
        ],
        render_kw={"placeholder": "O que precisa ser feito?"},
    )
    description = TextAreaField(
        "Descrição",
        filters=[strip_filter],
        validators=[Optional(), Length(max=5000)],
        render_kw={"rows": 3, "placeholder": "Contexto, links, critério de pronto…"},
    )
    estimate_pomodoros = IntegerField(
        "Sessões de foco (estimativa)",
        default=1,
        validators=[
            Optional(),
            NumberRange(min=0, max=40, message="Use entre 0 e 40 sessões."),
        ],
        render_kw={"min": 0, "max": 40, "inputmode": "numeric"},
    )
    due_date = DateField(
        "Prazo final",
        format="%Y-%m-%d",
        validators=[Optional()],
        render_kw={"type": "date"},
    )
    category = SelectField(
        "Categoria",
        choices=[],
        default="work",
        validators=[Optional()],
    )
    quadrant = SelectField(
        "Quadrante da matriz",
        choices=[("", "Sem classificação")]
        + [(q, f"{TASK_QUADRANT_LABELS[q]} · {TASK_QUADRANT_HINTS[q]}") for q in TASK_QUADRANTS],
        default="",
        validators=[Optional()],
    )
    is_mit = BooleanField(
        "Prioridade do dia",
        default=False,
        description="Até três tarefas mais importantes do dia.",
    )
    tags = StringField(
        "Etiquetas",
        filters=[strip_filter],
        validators=[Optional(), Length(max=255)],
        render_kw={"placeholder": "trabalho, estudo (separadas por vírgula)"},
    )
    submit = SubmitField("Salvar tarefa")


class TaskStatusForm(FlaskForm):
    status = SelectField(
        "Status",
        choices=[(s, TASK_STATUS_LABELS[s]) for s in TASK_STATUSES],
        validators=[DataRequired()],
    )


class ScratchpadForm(FlaskForm):
    content = TextAreaField(
        "Sua anotação",
        filters=[strip_filter],
        validators=[
            DataRequired("Escreva algo antes de capturar."),
            Length(max=5000, message="Máximo de 5000 caracteres."),
        ],
        render_kw={
            "rows": 3,
            "placeholder": "Escreva uma ideia, uma tarefa ou um link. Organize depois.",
            "maxlength": 5000,
        },
    )
    submit = SubmitField("Capturar")


class ConvertScratchForm(FlaskForm):
    title = StringField(
        "Título da tarefa",
        filters=[strip_filter],
        validators=[
            DataRequired("Dê um título à tarefa."),
            Length(max=160),
        ],
    )
    category = SelectField(
        "Categoria",
        choices=[],
        default="work",
        validators=[Optional()],
    )
    estimate_pomodoros = IntegerField(
        "Sessões de foco (estimativa)",
        default=1,
        validators=[Optional(), NumberRange(min=0, max=40)],
        render_kw={"min": 0, "max": 40},
    )
    keep_note = BooleanField("Manter o rascunho original", default=True)


class NoteForm(FlaskForm):
    title = StringField(
        "Título",
        filters=[strip_filter],
        validators=[
            DataRequired("Dê um título à nota."),
            Length(max=160, message="Máximo de 160 caracteres."),
        ],
        render_kw={"placeholder": "Título da nota"},
    )
    body = TextAreaField(
        "Conteúdo (Markdown)",
        validators=[Optional(), Length(max=40000)],
        render_kw={
            "rows": 18,
            "placeholder": "# Título\n\nEscreva em Markdown. Use [[Outra nota]] para linkar.",
            "data-markdown-editor": "true",
            "spellcheck": "true",
        },
    )
    tags = StringField(
        "Etiquetas",
        filters=[strip_filter],
        validators=[Optional(), Length(max=255)],
        render_kw={"placeholder": "estudo, projeto, referência"},
    )
    submit = SubmitField("Salvar nota")


class SearchForm(FlaskForm):
    q = StringField(
        "Buscar",
        filters=[strip_filter],
        validators=[Optional(), Length(max=120)],
        render_kw={
            "placeholder": "Buscar tarefas, notas e rascunhos…",
            "autocomplete": "off",
            "type": "search",
        },
    )


class WeeklyGoalForm(FlaskForm):
    weekly_focus_goal = IntegerField(
        "Meta de sessões por semana",
        validators=[
            DataRequired("Informe uma meta."),
            NumberRange(min=1, max=100, message="Use entre 1 e 100 sessões."),
        ],
        render_kw={"min": 1, "max": 100, "inputmode": "numeric"},
    )
    submit = SubmitField("Salvar meta")


class WeeklyReviewForm(FlaskForm):
    wins = TextAreaField(
        "O que funcionou bem?",
        validators=[Optional(), Length(max=5000)],
        render_kw={
            "rows": 4,
            "placeholder": "Conquistas, momentos leves, o que você aprendeu…",
        },
    )
    challenges = TextAreaField(
        "O que foi difícil?",
        validators=[Optional(), Length(max=5000)],
        render_kw={
            "rows": 4,
            "placeholder": "O que atrapalhou, o que levou mais tempo que o esperado…",
        },
    )
    next_steps = TextAreaField(
        "Qual é o foco da próxima semana?",
        validators=[Optional(), Length(max=5000)],
        render_kw={
            "rows": 4,
            "placeholder": "Uma ou duas prioridades, sem sobrecarregar…",
        },
    )
    submit = SubmitField("Salvar revisão")
