"""Categorias personalizadas por pessoa."""

from __future__ import annotations

import secrets

from extensions import db
from models import Category, Task

DEFAULT_CATEGORIES = (
    ("work", "Trabalho", "bi-briefcase"),
    ("study", "Estudos", "bi-mortarboard"),
    ("personal", "Pessoal", "bi-house-heart"),
)
CATEGORY_ICON_CHOICES = (
    ("bi-briefcase", "Trabalho"),
    ("bi-mortarboard", "Estudos"),
    ("bi-house-heart", "Pessoal"),
    ("bi-heart", "Bem-estar"),
    ("bi-code-slash", "Projetos"),
    ("bi-palette", "Criatividade"),
    ("bi-book", "Leitura"),
    ("bi-cart3", "Compras"),
    ("bi-activity", "Saúde"),
    ("bi-airplane", "Viagens"),
    ("bi-music-note-beamed", "Música"),
    ("bi-people", "Pessoas"),
    ("bi-lightbulb", "Ideias"),
    ("bi-star", "Favoritos"),
)
CATEGORY_ICON_KEYS = {key for key, _label in CATEGORY_ICON_CHOICES}
MAX_CATEGORIES = 20


def ensure_categories(user, commit: bool = True) -> list[Category]:
    """Cria as categorias iniciais e reencaixa tarefas antigas."""
    categories = (
        Category.query.filter_by(user_id=user.id)
        .order_by(Category.position.asc(), Category.id.asc())
        .all()
    )
    changed = False

    if not categories:
        for position, (key, name, icon) in enumerate(DEFAULT_CATEGORIES):
            category = Category(
                user_id=user.id,
                key=key,
                name=name,
                icon=icon,
                position=position,
            )
            db.session.add(category)
            categories.append(category)
        db.session.flush()
        changed = True

    valid_keys = {category.key for category in categories}
    fallback = categories[0].key
    for task in Task.query.filter_by(user_id=user.id).all():
        if task.category not in valid_keys:
            task.category = fallback
            changed = True

    if changed and commit:
        db.session.commit()
    return categories


def category_choices(categories: list[Category]) -> list[tuple[str, str]]:
    return [(category.key, category.name) for category in categories]


def category_by_key(user, key: str) -> Category | None:
    if not key:
        return None
    return Category.query.filter_by(user_id=user.id, key=key).first()


def category_by_id(user, category_id: int) -> Category | None:
    try:
        category_id = int(category_id)
    except (TypeError, ValueError):
        return None
    return Category.query.filter_by(user_id=user.id, id=category_id).first()


def new_category_key() -> str:
    return f"custom-{secrets.token_hex(4)}"
