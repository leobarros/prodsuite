"""Busca global (tarefas, notas e rascunhos) com consultas parametrizadas."""

from __future__ import annotations

from sqlalchemy import or_

from models import Note, Scratchpad, Task

MAX_PER_KIND = 8


def _snippet(text: str | None, term: str, radius: int = 90) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    lowered = text.lower()
    idx = lowered.find(term.lower())
    if idx < 0:
        return text[: radius * 2] + ("…" if len(text) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + len(term) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def global_search(user, query: str, limit_per_kind: int = MAX_PER_KIND) -> dict:
    """Retorna resultados agrupados, sempre restritos ao usuário autenticado."""
    term = " ".join((query or "").split())[:120]
    if len(term) < 2:
        return {"query": term, "total": 0, "groups": []}

    pattern = f"%{term}%"
    limit_per_kind = max(1, min(limit_per_kind, 20))

    tasks = (
        Task.query.filter(
            Task.user_id == user.id,
            or_(
                Task.title.ilike(pattern),
                Task.description.ilike(pattern),
                Task.tags.ilike(pattern),
            ),
        )
        .order_by(Task.updated_at.desc())
        .limit(limit_per_kind)
        .all()
    )

    notes = (
        Note.query.filter(
            Note.user_id == user.id,
            or_(Note.title.ilike(pattern), Note.body.ilike(pattern)),
        )
        .order_by(Note.updated_at.desc())
        .limit(limit_per_kind)
        .all()
    )

    scratchpads = (
        Scratchpad.query.filter(
            Scratchpad.user_id == user.id,
            Scratchpad.content.ilike(pattern),
        )
        .order_by(Scratchpad.updated_at.desc())
        .limit(limit_per_kind)
        .all()
    )

    groups = []

    if tasks:
        groups.append(
            {
                "kind": "tasks",
                "label": "Tarefas",
                "icon": "bi-check2-square",
                "items": [
                    {
                        "title": task.title,
                        "snippet": _snippet(task.description or task.tags, term),
                        "url": f"/tarefas/{task.id}/editar",
                        "meta": task.status,
                    }
                    for task in tasks
                ],
            }
        )

    if notes:
        groups.append(
            {
                "kind": "notes",
                "label": "Notas",
                "icon": "bi-journal-text",
                "items": [
                    {
                        "title": note.title,
                        "snippet": _snippet(note.body, term),
                        "url": f"/notas/{note.id}",
                        "meta": "nota",
                    }
                    for note in notes
                ],
            }
        )

    if scratchpads:
        groups.append(
            {
                "kind": "scratch",
                "label": "Rascunhos",
                "icon": "bi-lightning",
                "items": [
                    {
                        "title": "Rascunho",
                        "snippet": _snippet(scratch.content, term),
                        "url": "/rascunhos",
                        "meta": "captura",
                    }
                    for scratch in scratchpads
                ],
            }
        )

    total = sum(len(group["items"]) for group in groups)
    return {"query": term, "total": total, "groups": groups}
