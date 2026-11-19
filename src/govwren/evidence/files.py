"""Files in the data home, stored once by the SHA-256 of their content.

A file is kept, never run, and is always handed back as a download. What kind of file it is
is judged from its content first and its name second, and anything a browser might execute
is refused.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.core.clock import utc_now
from govwren.core.errors import Invalid
from govwren.db.models import FileUpload, StoredFile

MAX_BYTES = 25 * 1024 * 1024
OFFICE = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "zip": "application/zip",
}
LEGACY = {
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
    "ppt": "application/vnd.ms-powerpoint",
    "msg": "application/vnd.ms-outlook",
}
TEXT = {
    "txt": "text/plain",
    "md": "text/plain",
    "log": "text/plain",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "json": "application/json",
    "yaml": "text/plain",
    "yml": "text/plain",
    "eml": "message/rfc822",
}
REFUSED_TEXT = (b"<!doctype html", b"<html", b"<svg", b"<script", b"<?php", b"#!")
KINDS = "PDF, images, office documents, plain text, CSV, and JSON"


def extension(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def sniff(data: bytes, name: str) -> str | None:
    """The media type of a file GovWren will keep, or None for one it will not."""
    ext = extension(name)
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        return OFFICE.get(ext)
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return LEGACY.get(ext)
    if ext not in TEXT or b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    head = text[:2000].lstrip("﻿ \t\r\n").lower().encode()
    if head.startswith(REFUSED_TEXT):
        return None
    return TEXT[ext]


def clean_name(name: str) -> str:
    """A file name safe to show and to send in a header: no path, no control characters."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    kept = "".join(ch for ch in base if ch.isprintable() and ch not in '"<>|:*?').strip(" .")
    return kept[:200] or "file"


def path_of(files_dir: Path, sha256: str) -> Path:
    return files_dir / sha256[:2] / sha256[2:4] / sha256


def store(
    session: Session, files_dir: Path, data: bytes, name: str, uploader: int | None = None
) -> StoredFile:
    """Keep a file. The same content is kept once, however many times it is sent. ``uploader``
    is the account sending it, which is then allowed to attach it as evidence."""
    if not data:
        raise Invalid("The file was not kept.", {"file": "The file is empty."})
    if len(data) > MAX_BYTES:
        limit = MAX_BYTES // (1024 * 1024)
        raise Invalid("The file was not kept.", {"file": f"Keep files to {limit} MB."})
    media_type = sniff(data, name)
    if media_type is None:
        raise Invalid(
            "The file was not kept.",
            {"file": f"GovWren keeps {KINDS}. This does not look like one of those."},
        )
    sha256 = hashlib.sha256(data).hexdigest()
    existing = session.scalars(select(StoredFile).where(StoredFile.sha256 == sha256)).first()
    target = path_of(files_dir, sha256)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f"{sha256}.part-{os.getpid()}")
        partial.write_bytes(data)
        partial.replace(target)  # whole or not at all
    row = existing
    if row is None:
        row = StoredFile(sha256=sha256, size=len(data), media_type=media_type, created_at=utc_now())
        session.add(row)
        session.flush()
    if uploader is not None and not sent_by(session, row.id, uploader):
        session.add(FileUpload(file_id=row.id, account_id=uploader, uploaded_at=utc_now()))
        session.flush()
    return row


def sent_by(session: Session, file_id: int, account_id: int | None) -> bool:
    """Whether this account sent this file itself."""
    if account_id is None:
        return False
    return (
        session.scalars(
            select(FileUpload.id).where(
                FileUpload.file_id == file_id, FileUpload.account_id == account_id
            )
        ).first()
        is not None
    )


def read(files_dir: Path, row: StoredFile) -> bytes:
    """A stored file's content, checked against its name before it is handed back."""
    data = path_of(files_dir, row.sha256).read_bytes()
    if hashlib.sha256(data).hexdigest() != row.sha256:
        raise Invalid("The file cannot be read.", {"file": "It has changed since it was kept."})
    return data
