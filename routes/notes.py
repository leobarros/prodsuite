"""PKM: notas em Markdown, links internos, preview e busca."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from extensions import db
from forms import NoteForm
from models import Note, normalize_tags
from services.notes import render_note_excerpt, render_note_markdown

notes_bp = Blueprint("notes", __name__)


def _get_note(note_id: int) -> Note:
    return Note.query.filter_by(
        id=note_id, user_id=current_user.id
    ).first_or_404()


def _title_conflict(title: str, exclude_id: int | None = None) -> bool:
    query = Note.query.filter(
        Note.user_id == current_user.id,
        func.lower(Note.title) == title.strip().lower(),
    )
    if exclude_id is not None:
        query = query.filter(Note.id != exclude_id)
    return query.with_entities(Note.id).first() is not None


def _save_from_form(note: Note, form: NoteForm) -> bool:
    """Valida conflito de título (links [[...]] precisam ser determinísticos)."""
    if _title_conflict(form.title.data, exclude_id=note.id if note.id else None):
        form.title.errors.append(
            "Já existe uma nota com este título (links internos seriam ambíguos)."
        )
        return False
    note.title = form.title.data
    note.body = form.body.data or ""
    note.tags = normalize_tags(form.tags.data)
    return True


@notes_bp.get("/notas")
@login_required
def index():
    query = (request.args.get("q") or "").strip()[:120]
    notes_query = Note.query.filter(Note.user_id == current_user.id)
    if query:
        pattern = f"%{query}%"
        notes_query = notes_query.filter(
            or_(Note.title.ilike(pattern), Note.body.ilike(pattern))
        )
    notes = notes_query.order_by(Note.updated_at.desc()).limit(200).all()
    excerpts = {note.id: render_note_excerpt(note.body) for note in notes}
    return render_template(
        "notes.html", notes=notes, query=query, note_excerpts=excerpts
    )


@notes_bp.route("/notas/nova", methods=["GET", "POST"])
@login_required
def create():
    form = NoteForm()
    if form.validate_on_submit():
        note = Note(user_id=current_user.id)
        if _save_from_form(note, form):
            db.session.add(note)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar a nota.", "danger")
            else:
                flash("Nota criada.", "success")
                return redirect(url_for("notes.view", note_id=note.id))
    return render_template(
        "note_edit.html",
        form=form,
        note=None,
        rendered=render_note_markdown(current_user, ""),
    )


@notes_bp.get("/notas/<int:note_id>")
@login_required
def view(note_id: int):
    note = _get_note(note_id)
    rendered = render_note_markdown(current_user, note.body)
    backlinks = [
        n
        for n in Note.query.filter_by(user_id=current_user.id)
        .filter(Note.id != note.id)
        .all()
        if f"[[{note.title}]]".lower() in (n.body or "").lower()
    ][:6]
    return render_template(
        "note_view.html", note=note, rendered=rendered, backlinks=backlinks
    )


@notes_bp.route("/notas/<int:note_id>/editar", methods=["GET", "POST"])
@login_required
def edit(note_id: int):
    note = _get_note(note_id)
    form = NoteForm(obj=note)
    if form.validate_on_submit():
        if _save_from_form(note, form):
            db.session.commit()
            flash("Nota atualizada.", "success")
            return redirect(url_for("notes.view", note_id=note.id))
    return render_template(
        "note_edit.html",
        form=form,
        note=note,
        rendered=render_note_markdown(current_user, note.body),
    )


@notes_bp.post("/notas/<int:note_id>/excluir")
@login_required
def delete(note_id: int):
    note = _get_note(note_id)
    db.session.delete(note)
    db.session.commit()
    flash("Nota excluída.", "info")
    return redirect(url_for("notes.index"))


@notes_bp.post("/notas/preview")
@login_required
def preview():
    """Preview sanitizado para o editor em tempo real (debounce no cliente)."""
    payload = request.get_json(silent=True) or {}
    body = payload.get("body") or ""
    if len(body) > current_app.config["NOTE_MAX_LENGTH"]:
        return jsonify(ok=False, error="Conteúdo muito grande."), 413
    rendered = render_note_markdown(current_user, body)
    return jsonify(ok=True, html=str(rendered))
