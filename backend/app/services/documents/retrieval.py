"""Lexical retrieval (BM25) with section awareness.

Works with zero configuration and no embedding API. The interface
(`rank_chunks`) is deliberately small so a vector/hybrid retriever (e.g.
pgvector) can be slotted in later.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.'][a-z0-9]+)*")
_STOP = set(
    "a an and are as at be by for from has have how i in is it its me my of on or that the this to was "
    "what when where which who why will with you your explain tell about please can could do does give "
    "show summarize summarise describe".split()
)
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
          "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15}
_SECTION_REF_RE = re.compile(
    r"\b(unit|chapter|module|section|part|lesson|lecture|week|topic|question|q)\s*[-:.#]?\s*(\d{1,3}|[ivx]{1,5})\b",
    re.IGNORECASE,
)
_KIND_ALIASES = {"q": "question"}


class ChunkLike(Protocol):
    text: str
    section: str | None


@dataclass
class Scored:
    chunk: ChunkLike
    score: float


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def section_refs(text: str) -> set[tuple[str, int]]:
    refs: set[tuple[str, int]] = set()
    for kind, num in _SECTION_REF_RE.findall(text or ""):
        kind = _KIND_ALIASES.get(kind.lower(), kind.lower())
        n = int(num) if num.isdigit() else _ROMAN.get(num.lower())
        if n is not None:
            refs.add((kind, n))
    return refs


def rank_chunks(chunks: list[ChunkLike], query: str, top_k: int = 6, k1: float = 1.5, b: float = 0.75) -> list[Scored]:
    if not chunks:
        return []
    q_terms = tokenize(query)
    refs = section_refs(query)
    docs = [tokenize(c.text + " " + (c.section or "")) for c in chunks]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    scored: list[Scored] = []
    for chunk, terms in zip(chunks, docs, strict=True):
        tf = Counter(terms)
        dl = len(terms) or 1
        score = 0.0
        for t in q_terms:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        if refs and chunk.section and refs & section_refs(chunk.section):
            score += 25.0  # strong boost: the chunk belongs to the referenced unit/chapter
        scored.append(Scored(chunk, score))

    if refs:
        in_section = [s for s in scored if s.chunk.section and refs & section_refs(s.chunk.section)]
        if in_section:
            # Return the referenced section in document order so explanations read naturally.
            return in_section[: max(top_k, 12)]
    scored.sort(key=lambda s: s.score, reverse=True)
    return [s for s in scored[:top_k] if s.score > 0] or scored[: min(top_k, 3)]
