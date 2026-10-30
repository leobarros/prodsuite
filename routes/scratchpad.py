"""Captura rápida (Scratchpad) e conversão em tarefa."""

from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from extensions import db
from forms import ConvertScratchForm, ScratchpadForm
from models import Scratchpad, Task, normalize_tags, utcnow
from services.boards import ensure_default_project, project_columns
from services.categories import category_choices, ensure_categories
from services.timeutils import to_local

scratchpad_bp = Blueprint("scratchpad", __name__)


def _wants_json() -> bool:
    return bool(
        request.is_json
        or request.headers.get("X-Requested-With")
        in {"fetch", "XMLHttpRequest"}
        or request.accept_mimetypes.best == "application/json"
    )


def _get_item(item_id: int) -> Scratchpad:
    return Scratchpad.query.filter_by(
        id=item_id, user_id=current_user.id
    ).first_or_404()


@scratchpad_bp.route("/rascunhos", methods=["GET", "POST"])
@login_required
def index():
    form = ScratchpadForm()

    if form.validate_on_submit():
        item = Scratchpad(user_id=current_user.id, content=form.content.data)
        db.session.add(item)
        db.session.commit()
        if _wants_json():
            created = to_local(item.created_at)
            return (
                jsonify(
                    ok=True,
                    scratchpad={
                        "id": item.id,
                        "content": item.content,
                        "preview": item.preview,
                        "created_at": created.strftime("%d/%m %H:%M")
                        if created
                        else "",
                    },
                ),
                201,
            )
        flash("Rascunho capturado.", "success")
        return redirect(url_for("scratchpad.index"))

    if request.method == "POST" and _wants_json():
        return jsonify(ok=False, errors=form.errors), 400

    items = (
        Scratchpad.query.filter_by(user_id=current_user.id)
        .order_by(Scratchpad.created_at.desc())
        .limit(100)
        .all()
    )
    categories = ensure_categories(current_user)
    convert_form = ConvertScratchForm()
    convert_form.category.choices = category_choices(categories)
    if convert_form.category.data not in {c.key for c in categories}:
        convert_form.category.data = categories[0].key
    return render_template(
        "scratchpad.html", form=form, items=items, convert_form=convert_form
    )


@scratchpad_bp.post("/rascunhos/<int:item_id>/converter")
@login_required
def convert(item_id: int):
    item = _get_item(item_id)
    if item.is_converted:
        flash("Este rascunho já foi convertido em tarefa.", "warning")
        return redirect(url_for("scratchpad.index"))

    categories = ensure_categories(current_user)
    form = ConvertScratchForm()
    form.category.choices = category_choices(categories)
    if form.category.data not in {c.key for c in categories}:
        form.category.data = categories[0].key
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
        return redirect(url_for("scratchpad.index"))

    project = ensure_default_project(current_user)
    columns = project_columns(project) if project else []
    if project is None or not columns:
        flash("Crie um projeto e uma coluna antes de converter o rascunho.", "warning")
        return redirect(url_for("scratchpad.index"))
    column = columns[0]

    task = Task(
        user_id=current_user.id,
        title=form.title.data,
        description=item.content,
        status="done" if column.kind == "done" else "todo",
        column_id=column.id,
        column_entered_at=utcnow(),
        project_id=project.id,
        estimate_pomodoros=form.estimate_pomodoros.data or 0,
        category=form.category.data or categories[0].key,
        tags=normalize_tags(""),
    )
    if task.status == "done":
        task.completed_at = utcnow()
    db.session.add(task)
    db.session.flush()

    if form.keep_note.data:
        item.converted_task_id = task.id
    else:
        db.session.delete(item)
    db.session.commit()

    flash("Rascunho convertido em tarefa.", "success")
    return redirect(url_for("tasks.edit", task_id=task.id))


@scratchpad_bp.post("/rascunhos/<int:item_id>/excluir")
@login_required
def delete(item_id: int):
    item = _get_item(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Rascunho excluído.", "info")
    return redirect(url_for("scratchpad.index"))
