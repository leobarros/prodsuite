"""Armazenamento privado de anexos de tarefas."""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from models import TaskAttachment

ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".txt",
    ".csv",
    ".md",
}


def _upload_root() -> Path:
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def attachment_path(attachment: TaskAttachment) -> Path:
    return _upload_root() / str(attachment.user_id) / str(attachment.task_id) / attachment.stored_name


def _absolute_upload_path(user_id: int, task_id: int, stored_name: str) -> Path:
    return _upload_root() / str(user_id) / str(task_id) / stored_name


def delete_attachment_file(attachment: TaskAttachment) -> None:
    try:
        path = _absolute_upload_path(attachment.user_id, attachment.task_id, attachment.stored_name)
        path.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Falha ao remover anexo %s", attachment.id)


def save_attachment(user, task, file, *, comment=None) -> TaskAttachment:
    original = secure_filename(file.filename or "")
    if not original:
        raise ValueError("Escolha um arquivo válido.")
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato não permitido. Use imagem, PDF, TXT, CSV ou Markdown.")

    max_bytes = int(current_app.config["ATTACHMENT_MAX_BYTES"])
    data = file.stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("O arquivo pode ter no máximo 8 MB.")
    if not data:
        raise ValueError("O arquivo está vazio.")

    mime_type = mimetypes.guess_type(original)[0] or current_app.config[
        "ALLOWED_ATTACHMENT_EXTENSIONS"
    ].get(extension, "application/octet-stream")
    stored_name = f"{uuid.uuid4().hex}{extension}"
    folder = _upload_root() / str(user.id) / str(task.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / stored_name
    path.write_bytes(data)

    attachment = TaskAttachment(
        user_id=user.id,
        task_id=task.id,
        comment_id=comment.id if comment is not None else None,
        original_name=original[:255],
        stored_name=stored_name,
        mime_type=mime_type,
        size_bytes=len(data),
    )
    return attachment
