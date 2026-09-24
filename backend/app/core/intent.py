"""Intent detection.

A fast, deterministic classifier (no model call) that scores every intent
NEXUS supports. It handles the vast majority of requests instantly; when a
request is ambiguous or mixes several intents, the TaskPlanner asks the model
to build the plan instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Intent(StrEnum):
    CONVERSATION = "conversation"
    RESEARCH = "research"
    WEATHER = "weather"
    COMPUTER = "computer"
    CODING = "coding"
    FILE_ANALYSIS = "file_analysis"
    STUDY = "study"
    REMINDER = "reminder"
    AUTOMATION = "automation"
    TASKS = "tasks"
    MEMORY_STORE = "memory_store"
    MEMORY_RECALL = "memory_recall"
    VISION = "vision"
    SCREEN = "screen"
    EMAIL = "email"
    CALENDAR = "calendar"


_RULES: list[tuple[Intent, float, re.Pattern[str]]] = [
    (Intent.MEMORY_STORE, 0.95, re.compile(
        r"^\s*(hey\s+nexus[,!.]?\s*)?(please\s+)?(remember|note down|keep in mind|don'?t forget)\b(?!\s+me\b)"
        r"|^\s*my\s+[\w\s'-]{2,60}\s+(is|are)\s+(?!.*\?)"
        r"|\b(folder|directory)\s+(contains|has|holds)\s+(all\s+)?my\b|^\s*(call me|my name is|i live in)\b", re.I)),
    (Intent.MEMORY_RECALL, 0.8, re.compile(
        r"\bwhat do you (know|remember)\b|\b(list|show)\s+(my\s+)?memor(y|ies)\b|^\s*forget\b"
        r"|\b(what|who|where|which)('s| is| are)\s+my\b", re.I)),
    (Intent.REMINDER, 0.95, re.compile(r"\bremind\s+me\b|\bset\s+(a\s+)?reminder\b|\breminder\b", re.I)),
    (Intent.AUTOMATION, 0.9, re.compile(
        r"\b(every|each)\s+(day|morning|evening|night|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|hour)\b"
        r"|\b(daily|weekly|hourly)\b|\b(alert|notify)\s+me\s+(when|if|below|above)\b|\bprice\s+(drops?|alert|watch)\b"
        r"|\b(my\s+)?automations?\b", re.I)),
    (Intent.TASKS, 0.85, re.compile(
        r"\b(to-?do|todo)s?\b|\b(my|what|which|list|show|add|create|new|complete|finish|mark)\b.{0,20}\btasks?\b", re.I)),
    (Intent.WEATHER, 0.9, re.compile(r"\b(weather|forecast|temperature|umbrella|raining|rain|snow(ing)?|humidity)\b", re.I)),
    (Intent.SCREEN, 0.95, re.compile(
        r"\b(on|in)\s+my\s+screen\b|\bmy\s+screen\b|\bscreenshot\b|\bscreen\s*shot\b|\bwhat('s| is)\s+on\s+(the\s+)?screen\b", re.I)),
    (Intent.CODING, 0.85, re.compile(
        r"\b(code|coding|bug|debug|stack\s*trace|traceback|exception|compile|compiler|refactor|function|class|"
        r"unit\s*tests?|npm|pytest|python|javascript|typescript|react|api|repo|repository|git|build\s+(is\s+)?fail|"
        r"(run|test)\s+my\s+project|why\s+is\s+(it|my\s+\w+)\s+failing|error\s+in\s+my|syntax\s+error)\b", re.I)),
    (Intent.COMPUTER, 0.85, re.compile(
        r"^\s*(hey\s+nexus[,!.]?\s*)?(please\s+)?(open|launch|start|close|quit)\b|\b(vscode_app|vscode|terminal|file\s+manager|"
        r"folder|desktop|downloads)\b|\b(delete|remove|trash)\b.{0,40}\b(file|folder|directory)\b|\b(system|cpu|battery|ram|memory usage|disk space)\b.{0,15}\b(status|usage|level|left)?\b", re.I)),
    (Intent.STUDY, 0.8, re.compile(
        r"\b(explain|teach|understand|simplify|summari[sz]e|revision|revise|notes|quiz|flashcards?|practice\s+questions?|"
        r"exam|syllabus|unit\s*\d+|chapter\s*\d+|question\s*\d+|step[-\s]by[-\s]step|solve|homework|assignment|lecture|"
        r"what\s+is\s+(a|an|the)?\s*\w+\s*\?|define|definition)\b", re.I)),
    (Intent.FILE_ANALYSIS, 0.8, re.compile(
        r"\b(pdf|document|docx|attachment|attached|uploaded|this\s+(paper|doc|report|file)|compare\s+(these|the)\s+"
        r"(documents|files)|in\s+my\s+(notes|files))\b", re.I)),
    # A bare "file" is ambiguous (uploaded document vs. a file on disk): weak signal only.
    (Intent.FILE_ANALYSIS, 0.5, re.compile(r"\bfiles?\b", re.I)),
    (Intent.RESEARCH, 0.8, re.compile(
        r"\b(search|look\s*up|google|find\s+(me\s+)?(the\s+)?(best|cheapest|latest|top|reviews?|info)|latest|news|"
        r"current(ly)?|today'?s|recent|price\s+of|how\s+much\s+(is|does|are)|compare|vs\.?|versus|review|best|"
        r"cheapest|under|below\s+[₹$€£]|laptops?|phones?|who\s+won|what\s+happened|stock\s+price)\b", re.I)),
    (Intent.EMAIL, 0.9, re.compile(r"\b(e-?mail|inbox|gmail|outlook)\b", re.I)),
    (Intent.CALENDAR, 0.85, re.compile(r"\b(calendar|meeting|appointment|schedule\s+a|my\s+schedule)\b", re.I)),
]

_APP_NAMES = re.compile(r"\b(vs\s*code|visual\s+studio\s+code)\b", re.I)
_QUESTION_WORDS = re.compile(r"^\s*(who|what|when|where|why|how|is|are|can|could|should|do|does|will)\b", re.I)


@dataclass
class IntentResult:
    scores: dict[Intent, float] = field(default_factory=dict)
    has_documents: bool = False
    has_images: bool = False

    @property
    def ranked(self) -> list[tuple[Intent, float]]:
        return sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True)

    @property
    def primary(self) -> Intent:
        return self.ranked[0][0] if self.scores else Intent.CONVERSATION

    def has(self, intent: Intent, threshold: float = 0.5) -> bool:
        return self.scores.get(intent, 0.0) >= threshold

    @property
    def strong(self) -> list[Intent]:
        return [i for i, s in self.ranked if s >= 0.75]

    def to_dict(self) -> dict[str, Any]:
        return {"primary": self.primary.value, "scores": {k.value: round(v, 2) for k, v in self.ranked}}


def classify(text: str, attachments: list[Any] | None = None) -> IntentResult:
    attachments = attachments or []
    result = IntentResult(
        has_documents=any(getattr(a, "kind", "") != "image" for a in attachments),
        has_images=any(getattr(a, "kind", "") == "image" for a in attachments),
    )
    # App names that contain generic words ("VS Code") must not trigger coding/research rules.
    rule_text = _APP_NAMES.sub(" vscode_app ", text or "")
    for intent, weight, pattern in _RULES:
        if pattern.search(rule_text):
            result.scores[intent] = max(result.scores.get(intent, 0.0), weight)

    # Context from attachments
    if result.has_images:
        result.scores[Intent.VISION] = 0.95
    if result.has_documents:
        base = result.scores.get(Intent.FILE_ANALYSIS, 0.0)
        result.scores[Intent.FILE_ANALYSIS] = max(base, 0.85)
        if Intent.STUDY in result.scores:
            result.scores[Intent.STUDY] = max(result.scores[Intent.STUDY], 0.9)

    # Disambiguation
    if Intent.SCREEN in result.scores and result.has_images and not re.search(r"\b(my|the)\s+screen\b", text, re.I):
        result.scores.pop(Intent.SCREEN)  # "analyse this screenshot" with the screenshot attached
    if Intent.REMINDER in result.scores:
        # "remind me ..." is not a memory-store request, and its topic words are not separate intents.
        result.scores.pop(Intent.MEMORY_STORE, None)
        for topic in (Intent.STUDY, Intent.CODING, Intent.COMPUTER, Intent.FILE_ANALYSIS):
            if not (topic == Intent.FILE_ANALYSIS and result.has_documents):
                result.scores.pop(topic, None)
        if not re.search(r"\b(search|look\s*up|find)\b", text, re.I):
            result.scores.pop(Intent.RESEARCH, None)
        if not re.search(r"\b(every|each|daily|weekly)\b", text, re.I):
            result.scores.pop(Intent.AUTOMATION, None)
    if Intent.AUTOMATION in result.scores and re.search(r"\b(every|each|daily|weekly|hourly|alert|notify)\b", text, re.I):
        # The research/price check is what the automation will do later, not a step to run now.
        for topic in (Intent.RESEARCH, Intent.WEATHER, Intent.TASKS):
            result.scores.pop(topic, None)
    if Intent.MEMORY_STORE in result.scores:
        for weak in (Intent.STUDY, Intent.RESEARCH, Intent.COMPUTER, Intent.CODING, Intent.FILE_ANALYSIS):
            if result.scores.get(weak, 0) < 0.9:
                result.scores.pop(weak, None)
    if Intent.SCREEN in result.scores:
        result.scores.pop(Intent.COMPUTER, None)
        if not result.has_images:
            result.scores.pop(Intent.VISION, None)
    if Intent.WEATHER in result.scores and Intent.RESEARCH in result.scores:
        if not re.search(r"\b(search|news|compare)\b", text, re.I):
            result.scores.pop(Intent.RESEARCH)
    if Intent.CODING in result.scores and Intent.COMPUTER in result.scores:
        # "open VS Code and start my project" -> computer first; coding decides the rest.
        if re.search(r"\b(run|test|fix|debug|failing|error)\b", text, re.I):
            result.scores[Intent.COMPUTER] = min(result.scores[Intent.COMPUTER], 0.7)
    if Intent.COMPUTER in result.scores and re.search(r"\bmemory\b", text, re.I) and Intent.MEMORY_RECALL in result.scores:
        result.scores.pop(Intent.COMPUTER)
    if Intent.STUDY in result.scores and not result.has_documents:
        # Generic "what is X?" questions are conversation unless study words are explicit.
        if not re.search(r"\b(explain|quiz|revision|notes|practice|syllabus|unit|chapter|homework|assignment|"
                         r"step[-\s]by[-\s]step|solve|teach|flashcards?)\b", text, re.I):
            result.scores[Intent.STUDY] = 0.5
    if Intent.TASKS in result.scores and Intent.REMINDER in result.scores:
        result.scores[Intent.TASKS] = 0.6
    if not result.scores:
        result.scores[Intent.CONVERSATION] = 0.6 if _QUESTION_WORDS.search(text or "") else 0.7
    return result
