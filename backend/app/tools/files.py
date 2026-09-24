"""Tools over the user's uploaded files (PDF, DOCX, text, code)."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.core.context import RequestContext
from app.core.errors import NotFoundError
from app.security.prompt_injection import wrap_untrusted
from app.services import files as file_service
from app.services.documents.retrieval import section_refs
from app.tools.base import NoParams, Tool, ToolOutput, ToolParams


def _file_label(f) -> str:
    return f"{f.filename} (id: {f.id}, {f.kind}, {f.status}" + (f", {f.page_count} pages" if f.page_count else "") + ")"


class ListFilesTool(Tool):
    name = "list_files"
    description = "List the user's uploaded files with their ids, types and processing status."
    Params = NoParams
    category = "files"

    def describe_call(self, params) -> str:
        return "Listing your files"

    async def run(self, params: NoParams, ctx: RequestContext) -> ToolOutput:
        rows = await file_service.list_files(ctx.user.id, limit=100)
        attached = {str(a.id) for a in ctx.attachments}
        lines = [("* " if str(f.id) in attached else "- ") + _file_label(f) for f in rows]
        note = "\n(* = attached to the current message)" if attached else ""
        return ToolOutput(summary=f"Found {len(rows)} files", content=("\n".join(lines) or "No files uploaded.") + note,
                          data={"count": len(rows)})


class SearchFilesParams(ToolParams):
    query: str = Field(min_length=1, max_length=500, description="What to look for, e.g. 'Unit 3' or 'TCP handshake'")
    file_ids: list[uuid.UUID] | None = Field(default=None, description="Limit to these files (default: attached files, else all)")
    top_k: int = Field(default=6, ge=1, le=15)


class SearchFilesTool(Tool):
    name = "search_files"
    description = ("Search inside the user's uploaded documents and return the most relevant excerpts with file "
                   "name, section and page. Section references like 'Unit 3' or 'Chapter 2' return that section.")
    Params = SearchFilesParams
    category = "files"

    def describe_call(self, params: SearchFilesParams) -> str:
        return f"Searching your files for “{params.query[:60]}”"

    async def run(self, params: SearchFilesParams, ctx: RequestContext) -> ToolOutput:
        ids = params.file_ids or [a.id for a in ctx.attachments if a.kind != "image"] or None
        results = await file_service.search(ctx.user.id, params.query, ids, params.top_k)
        if not results:
            return ToolOutput(summary="No matching passages found", content="No matching passages in the user's files.",
                              data={"count": 0})
        names = {f.id: f.filename for f in await file_service.list_files(ctx.user.id, limit=500)}
        blocks = []
        for r in results:
            c = r.chunk
            loc = f"{names.get(c.file_id, 'file')}" + (f" · {c.section}" if c.section else "") + (
                f" · page {c.page}" if c.page else "")
            blocks.append(f"--- Excerpt [{loc}] ---\n{c.text}")
            ctx.add_source(loc, None, "file")
        refs = section_refs(params.query)
        missing = ""
        if refs and not any(r.chunk.section and refs & section_refs(r.chunk.section) for r in results):
            missing = ("\nNOTE: No section matching the requested unit/chapter was found in the document. "
                       "Say so explicitly instead of guessing.")
        return ToolOutput(
            summary=f"Found {len(results)} relevant passages",
            content=wrap_untrusted("\n\n".join(blocks), source="user_files", max_chars=30000) + missing,
            data={"count": len(results)},
        )


class OutlineParams(ToolParams):
    file_id: uuid.UUID


class FileOutlineTool(Tool):
    name = "get_file_outline"
    description = "Get a document's outline: detected sections (units, chapters, headings) with page numbers."
    Params = OutlineParams
    category = "files"

    def describe_call(self, params) -> str:
        return "Reading the document outline"

    async def run(self, params: OutlineParams, ctx: RequestContext) -> ToolOutput:
        f = await file_service.get_file(ctx.user.id, params.file_id)
        sections = (f.meta or {}).get("sections") or []
        lines = [f"- {s['title']}" + (f" (page {s['page']})" if s.get("page") else "") for s in sections]
        content = f"{_file_label(f)}\nSections:\n" + ("\n".join(lines) if lines else "(no headings detected)")
        return ToolOutput(summary=f"Outline of {f.filename}", content=wrap_untrusted(content, source=f.filename),
                          data={"sections": len(sections)})


class ReadSectionParams(ToolParams):
    file_id: uuid.UUID
    section: str | None = Field(default=None, max_length=200, description="Section title or reference, e.g. 'Unit 3'")
    start_chunk: int = Field(default=0, ge=0)
    max_chars: int = Field(default=15000, ge=1000, le=40000)


class ReadFileSectionTool(Tool):
    name = "read_file_section"
    description = ("Read the full text of a document, or of one section of it (e.g. 'Unit 3'). Use after "
                   "get_file_outline or search_files when you need complete context.")
    Params = ReadSectionParams
    category = "files"

    def describe_call(self, params: ReadSectionParams) -> str:
        return f"Reading {params.section or 'the document'}"

    async def run(self, params: ReadSectionParams, ctx: RequestContext) -> ToolOutput:
        f = await file_service.get_file(ctx.user.id, params.file_id)
        chunks = await file_service.get_chunks(ctx.user.id, [f.id])
        if params.section:
            refs = section_refs(params.section)
            needle = params.section.lower()
            selected = [c for c in chunks if c.section and (
                (refs and refs & section_refs(c.section)) or needle in c.section.lower())]
            if not selected:
                raise NotFoundError(f"No section matching '{params.section}' was found in {f.filename}.",
                                    code="section_not_found",
                                    next_step="Use get_file_outline to see the available sections.")
        else:
            selected = chunks[params.start_chunk:]
        text, used = "", 0
        for c in selected:
            piece = (f"[{c.section}{', page ' + str(c.page) if c.page else ''}]\n" if c.section else "") + c.text + "\n\n"
            if len(text) + len(piece) > params.max_chars:
                break
            text += piece
            used += 1
        more = len(selected) - used
        ctx.add_source(f"{f.filename}" + (f" · {params.section}" if params.section else ""), None, "file")
        tail = f"\n[{more} more chunks not shown; call again with start_chunk to continue]" if more > 0 and not params.section else ""
        return ToolOutput(summary=f"Read {params.section or f.filename}",
                          content=wrap_untrusted(text, source=f.filename, max_chars=params.max_chars + 200) + tail,
                          data={"chunks": used})
