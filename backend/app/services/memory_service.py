"""Long-term structured memory with explicit storage rules.

Memory rules
------------
* NEVER stored: secrets (API keys, passwords, PINs, OTPs), payment card
  numbers, government ID numbers, private keys.
* Needs the user's approval (stored as `pending`): anything NEXUS *inferred*
  on its own (unless the user turned that off), and personal-sensitive topics
  (health, finances, religion, politics, sexuality) even when explicit.
* Temporary (not stored): momentary states ("I'm tired", "I'm hungry") and
  one-off requests.
* Stored directly (`active`): facts the user explicitly asked NEXUS to
  remember, e.g. "My college AI project is LinkGuard AI".

Users can list, approve, edit and delete every memory from the Memory page.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select

from app.core.errors import NotFoundError, ValidationFailedError
from app.database.session import session_scope
from app.models import MEMORY_CATEGORIES, Memory
from app.models.base import utcnow
from app.security.redaction import contains_secret

_GOV_ID_PATTERNS = [
    re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),  # Aadhaar-like
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),  # Indian PAN
    re.compile(r"(?i)\bpassport (?:no\.?|number)\s*[:#]?\s*[A-Z0-9]{6,9}\b"),
]
_SENSITIVE_TOPICS = re.compile(
    r"(?i)\b(diagnos\w*|disease|illness|medication|prescription|therapy|therapist|depress\w*|anxiety|hiv|pregnan\w*|"
    r"salary|income|bank balance|debt|loan|religio\w*|caste|political|vote[sd]? for|sexual\w*|gay|lesbian|bisexual|"
    r"transgender)\b"
)
_TRANSIENT = re.compile(
    r"(?i)^(i'?m|i am|feeling|i feel)\s+(tired|hungry|sleepy|bored|busy|sick today|fine|ok|okay|good|great|back)\b"
)

_CATEGORY_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("project", re.compile(r"(?i)\b(project|repo|repository|app|codebase|assignment|thesis)\b")),
    ("person", re.compile(r"(?i)\b(friend|mom|mother|dad|father|brother|sister|wife|husband|partner|boss|manager|"
                          r"teacher|professor|colleague|son|daughter|name)\b")),
    ("place", re.compile(r"(?i)\b(city|home|office|college|university|school|hometown|address|live|lives|located)\b")),
    ("date", re.compile(r"(?i)\b(birthday|anniversary|exam|deadline|due date|interview)\b")),
    ("study", re.compile(r"(?i)\b(subject|course|semester|syllabus|major|studying|study)\b")),
    ("preference", re.compile(r"(?i)\b(favou?rite|prefer|preferred|like|love|hate|dislike)\b")),
    ("command", re.compile(r"(?i)\b(command|shortcut|alias|script)\b")),
]
_PATH_RE = re.compile(r"(?:[A-Za-z]:\\[^\s'\"<>|]*|~?/[^\s'\"<>|]+)")


@dataclass
class MemoryCandidate:
    category: str
    subject: str
    value: str
    aliases: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    explicit: bool = True


@dataclass
class PolicyDecision:
    action: str  # store_active | store_pending | reject | skip
    reason: str | None = None
    sensitivity: str = "normal"


def guess_category(text: str) -> str:
    for cat, pattern in _CATEGORY_HINTS:
        if pattern.search(text):
            return cat
    return "fact"


def evaluate(candidate: MemoryCandidate, prefs: dict[str, Any] | None = None) -> PolicyDecision:
    text = f"{candidate.subject} {candidate.value} {' '.join(map(str, candidate.attributes.values()))}"
    kind = contains_secret(text)
    if kind:
        return PolicyDecision("reject", f"it looks like a secret ({kind.replace('_', ' ')}), which NEXUS never stores")
    if any(p.search(text) for p in _GOV_ID_PATTERNS):
        return PolicyDecision("reject", "it contains an ID number, which NEXUS never stores")
    if _TRANSIENT.search(candidate.value) or _TRANSIENT.search(candidate.subject):
        return PolicyDecision("skip", "it describes a temporary state")
    if len(candidate.value.strip()) < 1 or len(candidate.subject.strip()) < 2:
        return PolicyDecision("skip", "not enough information")
    sensitive = bool(_SENSITIVE_TOPICS.search(text))
    sensitivity = "personal" if sensitive else "normal"
    if sensitive:
        return PolicyDecision("store_pending", "it is personal information, so it needs your approval", sensitivity)
    if not candidate.explicit:
        require = ((prefs or {}).get("memory") or {}).get("require_approval_for_inferred", True)
        if require:
            return PolicyDecision("store_pending", "NEXUS inferred it, so it needs your approval", sensitivity)
    return PolicyDecision("store_active", None, sensitivity)


# ---------------------------------------------------------------------------
# Rule-based extraction (works without an AI provider)
# ---------------------------------------------------------------------------

_REMEMBER_RE = re.compile(
    r"^\s*(?:hey\s+nexus[,!.]?\s*)?(?:please\s+)?(?:remember|note|keep in mind|don'?t forget|save)\s+(?:that\s+)?(?P<fact>.{3,500})$",
    re.IGNORECASE | re.DOTALL,
)
_MY_X_IS_Y = re.compile(
    r"^\s*my\s+(?P<subject>[\w\s'\-]{2,80}?)\s+(?:is|are|=|is called|is named)\s+(?:called\s+|named\s+)?(?P<value>.{1,300}?)\s*[.!]?$",
    re.IGNORECASE | re.DOTALL,
)
_THIS_FOLDER = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|~?/)[^\s'\"]+)\s+(?:folder\s+)?(?:contains|has|is where|holds)\s+(?:all\s+)?(?:of\s+)?my\s+(?P<what>.{2,80}?)\s*[.!]?$",
    re.IGNORECASE,
)
_I_LIVE = re.compile(r"^\s*i\s+live\s+in\s+(?P<value>[\w\s,.'\-]{2,80}?)\s*[.!]?$", re.IGNORECASE)
_CALL_ME = re.compile(r"^\s*(?:call me|my name is)\s+(?P<value>[\w\s.'\-]{1,60}?)\s*[.!]?$", re.IGNORECASE)


def extract_explicit(text: str) -> MemoryCandidate | None:
    """Extract a memory from an explicit statement (no AI needed)."""
    m = _REMEMBER_RE.match(text.strip())
    fact = m.group("fact").strip() if m else None
    body = fact or text.strip()

    pm = _THIS_FOLDER.search(body)
    if pm:
        what = pm.group("what").strip()
        return MemoryCandidate(category="project" if "project" in what.lower() else "place",
                               subject=f"folder for {what}", value=pm.group("path"),
                               aliases=[what], attributes={"path": pm.group("path")}, explicit=True)
    mm = _MY_X_IS_Y.match(body)
    if mm:
        subject = re.sub(r"\s+", " ", mm.group("subject")).strip()
        value = mm.group("value").strip().rstrip(".")
        attrs: dict[str, Any] = {}
        path = _PATH_RE.search(value)
        if path:
            attrs["path"] = path.group(0).rstrip(".,")
            head = re.sub(r"(?:,|\s)+(?:at|in|located at|stored at|under|inside)?\s*$", "", value[: path.start()]).strip()
            if head:
                value = head
        return MemoryCandidate(category=guess_category(subject), subject=subject, value=value,
                               attributes=attrs, explicit=True)
    lm = _I_LIVE.match(body)
    if lm:
        return MemoryCandidate(category="place", subject="home city", value=lm.group("value").strip(), explicit=True)
    cm = _CALL_ME.match(body)
    if cm:
        return MemoryCandidate(category="person", subject="user's name", value=cm.group("value").strip(), explicit=True)
    if fact:
        return MemoryCandidate(category=guess_category(fact), subject=fact[:80], value=fact, explicit=True)
    return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def memory_to_dict(m: Memory) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "category": m.category,
        "subject": m.subject,
        "value": m.value,
        "aliases": m.aliases or [],
        "attributes": m.attributes or {},
        "source": m.source,
        "status": m.status,
        "sensitivity": m.sensitivity,
        "use_count": m.use_count,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        "last_used_at": m.last_used_at.isoformat() if m.last_used_at else None,
    }


async def save_candidate(user_id: uuid.UUID, candidate: MemoryCandidate, prefs: dict[str, Any] | None = None
                         ) -> tuple[PolicyDecision, Memory | None]:
    if candidate.category not in MEMORY_CATEGORIES:
        candidate.category = "fact"
    decision = evaluate(candidate, prefs)
    if decision.action in ("reject", "skip"):
        return decision, None
    status = "active" if decision.action == "store_active" else "pending"
    async with session_scope() as db:
        existing = (await db.execute(
            select(Memory).where(Memory.user_id == user_id, Memory.category == candidate.category,
                                 func.lower(Memory.subject) == candidate.subject.lower())
        )).scalar_one_or_none()
        if existing is not None:
            existing.value = candidate.value
            existing.aliases = sorted(set((existing.aliases or []) + candidate.aliases))
            existing.attributes = {**(existing.attributes or {}), **candidate.attributes}
            # Explicit restatement upgrades a pending memory.
            if status == "active":
                existing.status = "active"
            existing.source = "explicit" if candidate.explicit else existing.source
            existing.sensitivity = decision.sensitivity
            row = existing
        else:
            row = Memory(
                user_id=user_id,
                category=candidate.category,
                subject=candidate.subject[:200],
                value=candidate.value[:4000],
                aliases=candidate.aliases[:20],
                attributes=candidate.attributes,
                source="explicit" if candidate.explicit else "inferred",
                status=status,
                sensitivity=decision.sensitivity,
            )
            db.add(row)
        await db.flush()
    return decision, row


async def list_memories(user_id: uuid.UUID, *, category: str | None = None, status: str | None = None,
                        query: str | None = None, limit: int = 500) -> list[Memory]:
    stmt = select(Memory).where(Memory.user_id == user_id)
    if category:
        stmt = stmt.where(Memory.category == category)
    if status:
        stmt = stmt.where(Memory.status == status)
    if query:
        like = f"%{query.lower()}%"
        stmt = stmt.where(or_(func.lower(Memory.subject).like(like), func.lower(Memory.value).like(like)))
    stmt = stmt.order_by(Memory.updated_at.desc()).limit(limit)
    async with session_scope() as db:
        return list((await db.execute(stmt)).scalars().all())


_WORD = re.compile(r"[a-z0-9]+")
_RECALL_STOP = {"my", "the", "a", "an", "of", "is", "what", "open", "start", "launch", "show", "me", "to", "for",
                "please", "nexus", "hey", "can", "you", "and", "in", "on", "i", "about"}


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _RECALL_STOP}


def score_memory(m: Memory, query: str) -> float:
    q = _terms(query)
    if not q:
        return 0.0
    subject_terms = _terms(m.subject) | {t for a in (m.aliases or []) for t in _terms(a)}
    value_terms = _terms(m.value)
    overlap_subject = len(q & subject_terms) / max(len(subject_terms), 1)
    overlap_query = len(q & (subject_terms | value_terms)) / len(q)
    score = 2.0 * overlap_subject + overlap_query
    if m.subject.lower() in query.lower():
        score += 1.5
    return score + min(m.use_count, 10) * 0.01


async def recall(user_id: uuid.UUID, query: str, *, category: str | None = None, limit: int = 5,
                 min_score: float = 0.34, touch: bool = True) -> list[tuple[Memory, float]]:
    rows = await list_memories(user_id, category=category, status="active", limit=2000)
    scored = sorted(((m, score_memory(m, query)) for m in rows), key=lambda x: x[1], reverse=True)
    hits = [(m, s) for m, s in scored if s >= min_score][:limit]
    if touch and hits:
        async with session_scope() as db:
            for m, _ in hits:
                row = await db.get(Memory, m.id)
                if row is not None:
                    row.use_count += 1
                    row.last_used_at = utcnow()
    return hits


async def get_memory(user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory:
    async with session_scope() as db:
        row = await db.get(Memory, memory_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("That memory was not found.", code="memory_not_found")
    return row


async def update_memory(user_id: uuid.UUID, memory_id: uuid.UUID, **fields: Any) -> Memory:
    async with session_scope() as db:
        row = await db.get(Memory, memory_id)
        if row is None or row.user_id != user_id:
            raise NotFoundError("That memory was not found.", code="memory_not_found")
        for k in ("category", "subject", "value", "aliases", "attributes", "status"):
            if k in fields and fields[k] is not None:
                if k == "category" and fields[k] not in MEMORY_CATEGORIES:
                    raise ValidationFailedError("Unknown memory category.", code="invalid_category")
                if k in ("subject", "value") and contains_secret(str(fields[k])):
                    raise ValidationFailedError("NEXUS does not store secrets in memory.", code="secret_rejected")
                setattr(row, k, fields[k])
        await db.flush()
        return row


async def delete_memory(user_id: uuid.UUID, memory_id: uuid.UUID) -> None:
    async with session_scope() as db:
        row = await db.get(Memory, memory_id)
        if row is None or row.user_id != user_id:
            raise NotFoundError("That memory was not found.", code="memory_not_found")
        await db.delete(row)


async def delete_all(user_id: uuid.UUID) -> int:
    rows = await list_memories(user_id, limit=100000)
    async with session_scope() as db:
        for m in rows:
            obj = await db.get(Memory, m.id)
            if obj is not None:
                await db.delete(obj)
    return len(rows)


def format_for_context(memories: list[Memory]) -> str:
    lines = []
    for m in memories:
        extra = f" (path: {m.attributes['path']})" if (m.attributes or {}).get("path") else ""
        aliases = f" [also: {', '.join(m.aliases)}]" if m.aliases else ""
        lines.append(f"- [{m.category}] {m.subject}: {m.value}{extra}{aliases} (memory id {m.id})")
    return "\n".join(lines)
