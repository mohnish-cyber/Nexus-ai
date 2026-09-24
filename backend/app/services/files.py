"""Uploaded file storage, processing and retrieval."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from app.config import get_settings
from app.core.errors import NexusError, NotFoundError, ValidationFailedError
from app.database.session import session_scope
from app.models import FileChunk, StoredFile
from app.security.paths import sanitize_filename
from app.security.uploads import detect_file
from app.services.documents.chunking import chunk_document
from app.services.documents.parsing import parse_document
from app.services.documents.retrieval import Scored, rank_chunks

logger = logging.getLogger(__name__)


def _user_dir(user_id: uuid.UUID) -> Path:
    d = get_settings().uploads_dir / user_id.hex
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_path(row: StoredFile) -> Path:
    return _user_dir(row.user_id) / row.stored_name


async def store_upload(user_id: uuid.UUID, filename: str, data: bytes) -> StoredFile:
    settings = get_settings()
    if len(data) > settings.max_upload_bytes:
        raise ValidationFailedError(
            f"The file is larger than {settings.max_upload_mb} MB.", code="file_too_large",
            next_step="Split or compress the file and try again.")
    detected = detect_file(filename, data)
    safe_name = sanitize_filename(filename)
    stored_name = uuid.uuid4().hex + detected.extension
    path = _user_dir(user_id) / stored_name
    await asyncio.to_thread(path.write_bytes, data)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    async with session_scope() as db:
        row = StoredFile(
            user_id=user_id,
            filename=safe_name,
            stored_name=stored_name,
            mime_type=detected.mime_type,
            kind=detected.kind,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            status="processing" if detected.kind != "image" else "ready",
            meta={"language": detected.extension.lstrip(".")} if detected.kind == "code" else {},
        )
        db.add(row)
        await db.flush()
        file_id = row.id
    if detected.kind != "image":
        await process_file(file_id, data)
    return await get_file(user_id, file_id)


async def process_file(file_id: uuid.UUID, data: bytes) -> None:
    async with session_scope() as db:
        row = await db.get(StoredFile, file_id)
        if row is None:
            return
        kind, user_id = row.kind, row.user_id
    try:
        doc = await asyncio.to_thread(parse_document, kind, data)
        chunks, sections = await asyncio.to_thread(chunk_document, doc)
        async with session_scope() as db:
            await db.execute(delete(FileChunk).where(FileChunk.file_id == file_id))
            for c in chunks:
                db.add(FileChunk(file_id=file_id, user_id=user_id, idx=c.idx, text=c.text, section=c.section,
                                 page=c.page))
            row = await db.get(StoredFile, file_id)
            if row is not None:
                row.status = "ready"
                row.page_count = doc.meta.get("page_count") or len(doc.pages)
                row.char_count = len(doc.text)
                row.meta = {**(row.meta or {}), "sections": sections[:300], "chunks": len(chunks),
                            "title": doc.title}
    except NexusError as exc:
        await _mark_failed(file_id, exc.message + (f" {exc.info.reason}" if exc.info.reason else ""))
    except Exception as exc:
        logger.exception("Processing file %s failed", file_id)
        await _mark_failed(file_id, f"Could not process the file ({exc.__class__.__name__}).")


async def _mark_failed(file_id: uuid.UUID, message: str) -> None:
    async with session_scope() as db:
        row = await db.get(StoredFile, file_id)
        if row is not None:
            row.status = "failed"
            row.error = message[:1000]


async def get_file(user_id: uuid.UUID, file_id: uuid.UUID) -> StoredFile:
    async with session_scope() as db:
        row = await db.get(StoredFile, file_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("That file was not found.", code="file_not_found")
    return row


async def list_files(user_id: uuid.UUID, limit: int = 200) -> list[StoredFile]:
    async with session_scope() as db:
        rows = (await db.execute(
            select(StoredFile).where(StoredFile.user_id == user_id).order_by(StoredFile.created_at.desc()).limit(limit)
        )).scalars().all()
    return list(rows)


async def delete_file(user_id: uuid.UUID, file_id: uuid.UUID) -> None:
    row = await get_file(user_id, file_id)
    path = file_path(row)
    async with session_scope() as db:
        await db.execute(delete(FileChunk).where(FileChunk.file_id == file_id))
        await db.execute(delete(StoredFile).where(StoredFile.id == file_id, StoredFile.user_id == user_id))
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete %s: %s", path, exc)


async def read_bytes(row: StoredFile) -> bytes:
    return await asyncio.to_thread(file_path(row).read_bytes)


async def image_b64(row: StoredFile) -> tuple[str, str]:
    if row.kind != "image":
        raise ValidationFailedError(f"'{row.filename}' is not an image.", code="not_an_image")
    data = await read_bytes(row)
    return row.mime_type, base64.standard_b64encode(data).decode()


async def get_chunks(user_id: uuid.UUID, file_ids: list[uuid.UUID]) -> list[FileChunk]:
    if not file_ids:
        return []
    async with session_scope() as db:
        rows = (await db.execute(
            select(FileChunk).where(FileChunk.user_id == user_id, FileChunk.file_id.in_(file_ids))
            .order_by(FileChunk.file_id, FileChunk.idx)
        )).scalars().all()
    return list(rows)


async def search(user_id: uuid.UUID, query: str, file_ids: list[uuid.UUID] | None = None, top_k: int = 6) -> list[Scored]:
    if not file_ids:
        file_ids = [f.id for f in await list_files(user_id) if f.status == "ready" and f.kind != "image"]
    chunks = await get_chunks(user_id, file_ids)
    return rank_chunks(chunks, query, top_k=top_k)
