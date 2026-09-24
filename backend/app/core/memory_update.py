"""Post-turn memory update.

After a reply, NEXUS may notice durable facts the user mentioned in passing
("I study at MIT", "my sister's name is Ana"). These are *inferred*, so by
default they are saved as `pending` suggestions the user approves on the
Memory page - never silently stored. Explicit "remember that ..." requests are
handled by MemoryAgent during the turn instead.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from app.config import get_settings
from app.core.context import ActionRecord, EmitFn
from app.services import memory_service as ms
from app.services.ai.base import AIProvider, ChatMessage

logger = logging.getLogger(__name__)

_DURABLE_HINT = re.compile(
    r"\b(i am|i'm|i work|i study|i live|i was born|my (name|birthday|project|college|university|school|job|company|"
    r"favou?rite|wife|husband|partner|friend|brother|sister|mom|mother|dad|father|boss|manager|exam|major|course|"
    r"team|city|hometown|laptop|phone|cat|dog)|i prefer|i like|i love|i hate|i always|i usually|i use)\b",
    re.IGNORECASE,
)

EXTRACTION_PROMPT = """Extract durable personal facts from the user's message that would be useful to remember
for future conversations (projects, people, places, preferences, study details, important dates).
Ignore temporary states, questions, opinions about the current topic, and anything sensitive (health,
finances, passwords, IDs). Return ONLY JSON: {"memories": [{"category": "preference|project|person|place|
study|date|fact", "subject": "short subject e.g. 'college AI project'", "value": "the fact",
"aliases": []}]}. Return {"memories": []} if there is nothing worth remembering."""


async def update_after_turn(user_id: uuid.UUID, text: str, prefs: dict[str, Any], provider: AIProvider | None,
                            actions: list[ActionRecord], emit: EmitFn | None = None) -> list[dict[str, Any]]:
    if not (prefs.get("memory") or {}).get("auto_remember", True):
        return []
    if any(a.tool in ("remember", "forget") for a in actions):
        return []
    text = (text or "").strip()
    if len(text) < 12 or len(text) > 2000 or not _DURABLE_HINT.search(text):
        return []

    candidates: list[ms.MemoryCandidate] = []
    if "?" not in text and len(text) < 200:
        c = ms.extract_explicit(text)
        if c is not None and len(c.value) < 120:
            c.explicit = False
            candidates.append(c)
    if not candidates and provider is not None:
        try:
            resp = await provider.generate(system=EXTRACTION_PROMPT, messages=[ChatMessage.user(text)],
                                           effort=get_settings().ai_effort_routing, max_tokens=1500)
            match = re.search(r"\{.*\}", resp.text, re.DOTALL)
            data = json.loads(match.group(0)) if match else {}
            for item in (data.get("memories") or [])[:3]:
                subject, value = str(item.get("subject", "")).strip(), str(item.get("value", "")).strip()
                if subject and value:
                    candidates.append(ms.MemoryCandidate(
                        category=str(item.get("category", "fact")), subject=subject[:200], value=value[:1000],
                        aliases=[str(a)[:80] for a in (item.get("aliases") or [])][:5], explicit=False))
        except Exception as exc:
            logger.info("Memory extraction skipped: %s", exc)

    saved = []
    for cand in candidates:
        decision, row = await ms.save_candidate(user_id, cand, prefs)
        if row is not None:
            saved.append(ms.memory_to_dict(row))
    if saved and emit is not None:
        try:
            await emit({"type": "memory_update", "memories": saved})
        except Exception:  # client may be gone
            logger.debug("memory_update emit failed")
    return saved
