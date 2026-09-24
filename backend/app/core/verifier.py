"""Result verification.

The action ledger (what tools actually did) is the source of truth. Before a
reply is shown, we check it for claims of actions that have no successful
matching tool execution, and append a clear correction if we find one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.context import ActionRecord


@dataclass(frozen=True)
class ClaimRule:
    label: str
    pattern: re.Pattern[str]
    tools: frozenset[str]


_I = r"\b(?:i|i've|i have|i just|i've just|i have just)\s+"
_CLAIMS = [
    ClaimRule("a reminder or task was scheduled",
              re.compile(_I + r"(?:set|scheduled|created|added)\b.{0,40}\b(?:reminder|task|alarm)"
                         r"|\breminder\s+(?:is\s+|has been\s+)?(?:set|scheduled|created)\b|\bi'll remind you\b", re.I),
              frozenset({"create_reminder", "create_task", "create_automation"})),
    ClaimRule("an automation was created",
              re.compile(_I + r"(?:set up|created|scheduled)\b.{0,40}\b(?:automation|digest|alert|watch)\b", re.I),
              frozenset({"create_automation"})),
    ClaimRule("an application or file was opened",
              re.compile(_I + r"(?:opened|launched|started)\b.{0,40}\b(?:vs\s*code|app|application|folder|browser|"
                         r"terminal|file|project|chrome|firefox)\b", re.I),
              frozenset({"open_application", "open_path", "open_url"})),
    ClaimRule("something was deleted",
              re.compile(_I + r"(?:deleted|removed|erased|forgot|forgotten)\b.{0,30}\b(?:file|folder|directory|memory|"
                         r"automation|reminder)\b", re.I),
              frozenset({"delete_path", "forget", "cancel_automation"})),
    ClaimRule("a file was modified",
              re.compile(_I + r"(?:edited|modified|updated|changed|fixed|patched|saved|wrote|written|created)\b.{0,40}"
                         r"\b(?:the\s+file|your\s+file|a\s+file|file\s+\S+|\S+\.(?:py|js|jsx|ts|tsx|json|md|css|html))\b", re.I),
              frozenset({"write_file", "edit_file"})),
    ClaimRule("a command or tests were run",
              re.compile(_I + r"(?:ran|executed|re-ran|reran)\b.{0,30}\b(?:tests?|command|npm|pytest|build|script)\b", re.I),
              frozenset({"run_command"})),
    ClaimRule("something was remembered",
              re.compile(r"\bi(?:'ll| will)\s+remember\s+that\b|" + _I + r"(?:saved|stored|remembered)\b.{0,20}\b(?:memory|that|this)\b",
                         re.I),
              frozenset({"remember"})),
]


def unverified_claims(answer: str, actions: list[ActionRecord]) -> list[str]:
    succeeded = {a.tool for a in actions if a.status == "succeeded"}
    problems = []
    for rule in _CLAIMS:
        if rule.pattern.search(answer or "") and not (rule.tools & succeeded):
            # Negated statements ("I haven't opened...", "couldn't") are fine.
            window = rule.pattern.search(answer).group(0)
            if re.search(r"\b(not|n't|couldn't|cannot|can't|unable|failed|won't)\b", window, re.I):
                continue
            problems.append(rule.label)
    return problems


def verify(answer: str, actions: list[ActionRecord]) -> tuple[str, list[str]]:
    problems = unverified_claims(answer, actions)
    if not problems:
        return answer, []
    note = ("\n\n> ⚠️ **Verification:** I couldn't confirm that " + "; ".join(problems) +
            " — no successful action was recorded for it. Please treat that part as not done.")
    return answer + note, problems
