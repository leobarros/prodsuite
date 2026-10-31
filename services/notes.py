"""Renderização segura de Markdown para as notas PKM.

Pipeline:
1. ``[[Título]]`` vira link interno quando existe nota com o mesmo título.
2. Markdown -> HTML.
3. Bleach remove tags/atributos perigosos (XSS) e protocolos como
   ``javascript:``.

O HTML final é marcado como ``Markup`` para o Jinja não escapar novamente —
por isso o passo 3 é obrigatório e coberto por testes.
"""

from __future__ import annotations

import html
import re

import bleach
import markdown as md
from markupsafe import Markup

from models import Note

WIKI_LINK_RE = re.compile(r"\[\[([^\[\]\n]{1,120})\]\]")

ALLOWED_TAGS = [
    "p", "br", "hr", "strong", "em", "u", "s", "del", "ins",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "code",
    "a", "table", "thead", "tbody", "tr", "th", "td",
    "span", "div",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "span": ["class"],
    "div": ["class"],
    "code": ["class"],
    "th": ["align"],
    "td": ["align"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_EXTERNAL_ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bhref="https?://[^"]+"[^>]*>', re.IGNORECASE
)


def _open_external_links(html_fragment: str) -> str:
    """Abre links externos em outra aba sem permitir acesso ao opener."""
    def _replace(match: re.Match) -> str:
        tag = match.group(0)
        if "target=" in tag.lower():
            return tag
        return tag[:-1] + ' target="_blank" rel="noopener noreferrer">'

    return _EXTERNAL_ANCHOR_RE.sub(_replace, html_fragment)


def _escape_link_text(text: str) -> str:
    """Escapa caracteres que quebrariam a sintaxe de link Markdown."""
    for char in ("\\", "[", "]", "(", ")"):
        text = text.replace(char, "\\" + char)
    return text


def render_note_markdown(user, body: str | None) -> Markup:
    body = body or ""

    # Resolve todos os títulos do usuário em uma única query (casefold em
    # Python para funcionar igual em SQLite e outros bancos).
    titles = {
        (note.title or "").strip().casefold(): note.id
        for note in Note.query.filter_by(user_id=user.id).all()
    }

    def _replace_wiki(match: re.Match) -> str:
        raw = match.group(1).strip()
        note_id = titles.get(raw.casefold())
        if note_id is not None:
            return f"[{_escape_link_text(raw)}](/notas/{note_id})"
        # Nota ainda não criada: vira um "link fantasma" visível, sem HTML
        # controlado pelo usuário (html.escape antes de entrar no Markdown).
        return f'<span class="wiki-missing">[[{html.escape(raw)}]]</span>'

    prepared = WIKI_LINK_RE.sub(_replace_wiki, body)
    rendered = md.markdown(
        prepared,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )
    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
    # Também transforma URLs coladas como texto em links.
    linked = bleach.linkify(cleaned, parse_email=False, skip_tags=["pre", "code"])
    return Markup(_open_external_links(linked))


def render_note_excerpt(body: str | None) -> Markup:
    """Resumo seguro para a lista, com URLs clicáveis."""
    text = re.sub(r"[#*_>`\[\]()!-]+", " ", body or "")
    text = " ".join(text.split())
    excerpt = text[:180] + ("…" if len(text) > 180 else "")
    escaped = html.escape(excerpt)
    linked = bleach.linkify(escaped, parse_email=False)
    cleaned = bleach.clean(
        linked,
        tags=["a", "br"],
        attributes={"a": ["href", "rel", "target"]},
        protocols=["http", "https"],
        strip=True,
    )
    return Markup(_open_external_links(cleaned))
