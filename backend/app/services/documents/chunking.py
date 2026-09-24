"""Heading-aware chunking.

Chunks never span two sections, so a question about "Unit 3" retrieves text
that actually belongs to Unit 3.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.documents.parsing import ParsedDocument, detect_heading


@dataclass
class Chunk:
    idx: int
    text: str
    section: str | None
    page: int | None


def chunk_document(doc: ParsedDocument, target_chars: int = 1400, overlap_chars: int = 150) -> tuple[list[Chunk], list[dict]]:
    chunks: list[Chunk] = []
    sections: list[dict] = []
    section: str | None = None
    buf: list[str] = []
    buf_len = 0
    buf_page: int | None = None

    def flush(carry_overlap: bool) -> None:
        nonlocal buf, buf_len, buf_page
        text = "\n".join(buf).strip()
        if text:
            chunks.append(Chunk(len(chunks), text, section, buf_page))
        if carry_overlap and text:
            tail = text[-overlap_chars:]
            buf, buf_len = [tail], len(tail)
        else:
            buf, buf_len = [], 0
        buf_page = None

    for page in doc.pages:
        for line in page.text.splitlines():
            heading = detect_heading(line, doc.kind)
            if heading:
                flush(carry_overlap=False)
                section = heading[:300]
                sections.append({"title": section, "page": page.number if doc.kind == "pdf" else None})
            if not line.strip():
                if buf and buf[-1] != "":
                    buf.append("")
                continue
            if buf_page is None:
                buf_page = page.number if doc.kind == "pdf" else None
            # Hard-split pathological very long lines.
            while len(line) > target_chars:
                buf.append(line[:target_chars])
                buf_len += target_chars
                line = line[target_chars:]
                flush(carry_overlap=True)
            buf.append(line)
            buf_len += len(line) + 1
            if buf_len >= target_chars:
                flush(carry_overlap=True)
    flush(carry_overlap=False)
    return chunks, sections
