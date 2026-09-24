"""Validation of uploaded files.

Uploads are identified by *content* (magic bytes), not by the extension or the
client-provided MIME type. They are stored under random names outside any web
root and are never executed.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from app.core.errors import ValidationFailedError

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".yaml", ".yml", ".toml", ".ini", ".log", ".rst"}
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb",
    ".php", ".swift", ".kt", ".kts", ".scala", ".sql", ".sh", ".bash", ".ps1", ".html", ".css", ".scss",
    ".vue", ".svelte", ".dart", ".lua", ".r", ".m", ".xml", ".gradle", ".dockerfile",
}
IMAGE_TYPES = {
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"GIF87a": ("image/gif", ".gif"),
    b"GIF89a": ("image/gif", ".gif"),
}
MAX_DOCX_UNCOMPRESSED = 200 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000


@dataclass
class DetectedFile:
    kind: str  # pdf | docx | text | code | image
    mime_type: str
    extension: str


def _ext(filename: str) -> str:
    name = filename.lower()
    if name.endswith("dockerfile"):
        return ".dockerfile"
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def _looks_textual(data: bytes) -> bool:
    sample = data[:8192]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError as exc:
        # tolerate a multi-byte char cut at the sample boundary
        return exc.start >= len(sample) - 4


def _check_docx(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "[Content_Types].xml" not in names or not any(n.startswith("word/") for n in names):
                raise ValidationFailedError("That .docx file is not a valid Word document.", code="invalid_docx")
            total = sum(i.file_size for i in zf.infolist())
            if total > MAX_DOCX_UNCOMPRESSED:
                raise ValidationFailedError(
                    "That document expands to an unsafe size.",
                    code="zip_bomb",
                    reason="The compressed archive would expand to more than 200 MB.",
                )
    except zipfile.BadZipFile as exc:
        raise ValidationFailedError("That .docx file is corrupted.", code="invalid_docx") from exc


def _check_image(data: bytes) -> None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            w, h = img.size
            if w * h > MAX_IMAGE_PIXELS:
                raise ValidationFailedError("That image is too large to process.", code="image_too_large")
            img.verify()
    except ValidationFailedError:
        raise
    except Exception as exc:
        raise ValidationFailedError("That image file is corrupted or unsupported.", code="invalid_image") from exc


def detect_file(filename: str, data: bytes) -> DetectedFile:
    if not data:
        raise ValidationFailedError("The uploaded file is empty.", code="empty_file")
    ext = _ext(filename)

    if data.startswith(b"%PDF-"):
        return DetectedFile("pdf", "application/pdf", ".pdf")

    for magic, (mime, img_ext) in IMAGE_TYPES.items():
        if data.startswith(magic):
            _check_image(data)
            return DetectedFile("image", mime, img_ext)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        _check_image(data)
        return DetectedFile("image", "image/webp", ".webp")

    if data.startswith(b"PK\x03\x04"):
        if ext == ".docx":
            _check_docx(data)
            return DetectedFile(
                "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
            )
        raise ValidationFailedError(
            "Archive files are not supported.",
            code="unsupported_file_type",
            next_step="Upload a PDF, DOCX, text, code or image file.",
        )

    if _looks_textual(data):
        if ext in CODE_EXTENSIONS:
            return DetectedFile("code", "text/plain", ext)
        if ext in TEXT_EXTENSIONS or ext == "":
            return DetectedFile("text", "text/plain", ext or ".txt")
        if ext == ".svg":
            raise ValidationFailedError("SVG files are not supported (they can contain scripts).", code="unsupported_file_type")
        return DetectedFile("text", "text/plain", ext)

    raise ValidationFailedError(
        f"'{filename}' is not a supported file type.",
        code="unsupported_file_type",
        reason="Supported: PDF, DOCX, TXT/Markdown, code files, PNG/JPEG/GIF/WebP images.",
        next_step="Convert the file to one of the supported formats.",
    )
