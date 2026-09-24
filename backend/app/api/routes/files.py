"""File uploads (validated by content), listing, image serving, deletion."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response

from app.api.deps import current_user
from app.config import get_settings
from app.core.errors import ValidationFailedError
from app.models import StoredFile
from app.security.auth import CurrentUser
from app.security.rate_limit import rate_limiter
from app.services import files as file_service

router = APIRouter(prefix="/api/files", tags=["files"])


def file_to_dict(f: StoredFile) -> dict[str, Any]:
    meta = f.meta or {}
    return {
        "id": str(f.id),
        "filename": f.filename,
        "kind": f.kind,
        "mime_type": f.mime_type,
        "size_bytes": f.size_bytes,
        "status": f.status,
        "error": f.error,
        "page_count": f.page_count,
        "char_count": f.char_count,
        "sections": [s.get("title") for s in (meta.get("sections") or [])][:50],
        "chunks": meta.get("chunks"),
        "created_at": f.created_at.isoformat(),
    }


@router.post("", status_code=201)
async def upload(request: Request, file: UploadFile = File(...), user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    rate_limiter.check(f"upload:{user.id}", 30)
    limit = get_settings().max_upload_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 1024 * 64:
        raise ValidationFailedError(f"The file is larger than {get_settings().max_upload_mb} MB.", code="file_too_large")
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ValidationFailedError(f"The file is larger than {get_settings().max_upload_mb} MB.", code="file_too_large")
    row = await file_service.store_upload(user.id, file.filename or "upload", data)
    return file_to_dict(row)


@router.get("")
async def list_files(user: CurrentUser = Depends(current_user)) -> list[dict[str, Any]]:
    return [file_to_dict(f) for f in await file_service.list_files(user.id)]


@router.get("/{file_id}")
async def get_file(file_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return file_to_dict(await file_service.get_file(user.id, file_id))


@router.get("/{file_id}/content")
async def file_content(file_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> Response:
    """Serves images inline (for previews). Other types are downloads - never rendered by the browser."""
    row = await file_service.get_file(user.id, file_id)
    data = await file_service.read_bytes(row)
    disposition = "inline" if row.kind == "image" else "attachment"
    media = row.mime_type if row.kind == "image" else "application/octet-stream"
    return Response(content=data, media_type=media, headers={
        "Content-Disposition": f'{disposition}; filename="{row.filename}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, max-age=3600",
    })


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: uuid.UUID, user: CurrentUser = Depends(current_user)) -> None:
    await file_service.delete_file(user.id, file_id)
