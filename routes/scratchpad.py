"""Captura rápida (Scratchpad), edição e conversão em tarefa."""

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
from forms import ScratchpadForm, TaskForm
from models import Scratchpad
from services.boards import ensure_default_project, project_columns
from services.categories import category_choices, ensure_categories
from services.task_creation import create_task_from_form
from services.timeutils import local_today, to_local

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


def _task_form_context(item: Scratchpad, form: TaskForm | None = None) -> dict:
    categories = ensure_categories(current_user)
    task_form = form or TaskForm()
    task_form.category.choices = category_choices(categories)
    valid_categories = {category.key for category in categories}
    if not task_form.category.data or task_form.category.data not in valid_categories:
        task_form.category.data = categories[0].key
    project = ensure_default_project(current_user)
    columns = project_columns(project) if project else []
    selected_column_id = (
        int(request.form.get("column_id"))
        if request.form.get("column_id", "").isdigit()
        else (columns[0].id if columns else None)
    )
    if form is None:
        task_form.title.data = (item.content.split("\n")[0] or "")[:160]
        task_form.description.data = item.content
        task_form.estimate_pomodoros.data = 1
        task_form.due_date.data = local_today()
    return {
        "task_form": task_form,
        "categories": categories,
        "project": project,
        "board_columns": columns,
        "selected_column_id": selected_column_id,
    }


def _render_detail(
    item: Scratchpad,
    *,
    edit_form: ScratchpadForm | None = None,
    task_form: TaskForm | None = None,
    open_modal: bool = False,
    status: int = 200,
):
    edit_form = edit_form or ScratchpadForm(obj=item)
    context = _task_form_context(item, task_form)
    return (
        render_template(
            "scratchpad_detail.html",
            item=item,
            form=edit_form,
            open_modal=open_modal,
            **context,
        ),
        status,
    )


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
        Scratchpad.query.filter(
            Scratchpad.user_id == current_user.id,
            Scratchpad.converted_task_id.is_(None),
        )
        .order_by(Scratchpad.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template("scratchpad.html", form=form, items=items)


@scratchpad_bp.get("/rascunhos/<int:item_id>")
@login_required
def detail(item_id: int):
    return _render_detail(_get_item(item_id))


@scratchpad_bp.post("/rascunhos/<int:item_id>/editar")
@login_required
def edit(item_id: int):
    item = _get_item(item_id)
    form = ScratchpadForm(obj=item)
    if form.validate_on_submit():
        item.content = form.content.data
        db.session.commit()
        flash("Rascunho atualizado.", "success")
        return redirect(url_for("scratchpad.detail", item_id=item.id))
    flash("Revise a anotação antes de salvar.", "danger")
    return _render_detail(item, edit_form=form, status=400)


@scratchpad_bp.post("/rascunhos/<int:item_id>/converter")
@login_required
def convert(item_id: int):
    item = _get_item(item_id)
    if item.is_converted:
        flash("Este rascunho já foi convertido em tarefa.", "warning")
        return redirect(url_for("scratchpad.detail", item_id=item.id))

    task_form = TaskForm()
    context = _task_form_context(item, task_form)
    if not task_form.description.data:
        task_form.description.data = item.content
    if not task_form.validate_on_submit():
        flash("Revise os campos da tarefa.", "danger")
        return _render_detail(
            item, task_form=task_form, open_modal=True, status=400
        )

    task = create_task_from_form(
        current_user,
        task_form,
        context["project"],
        context["board_columns"],
        context["categories"],
        request.form.get("column_id"),
    )
    if task is None:
        return redirect(url_for("scratchpad.detail", item_id=item.id))

    db.session.delete(item)
    db.session.commit()
    flash("Rascunho convertido em tarefa e removido dos rascunhos.", "success")
    return redirect(url_for("tasks.edit", task_id=task.id))


@scratchpad_bp.post("/rascunhos/<int:item_id>/excluir")
@login_required
def delete(item_id: int):
    item = _get_item(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Rascunho excluído.", "info")
    return redirect(url_for("scratchpad.index"))
