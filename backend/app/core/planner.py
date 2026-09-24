"""Task planner: turns a classified request into an ordered list of agent steps.

* Clear single-intent requests use deterministic templates (instant, free).
* Known multi-step patterns use templates too (document → study, screen →
  vision, weather → conditional reminder).
* Anything else with several intents asks the model for a small JSON plan,
  validated against the registered agents; on any failure we fall back to a
  deterministic plan.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.registry import get_agent
from app.config import get_settings
from app.core.intent import Intent, IntentResult
from app.services.ai.base import AIProvider, ChatMessage

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    agent: str
    instruction: str
    options: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        agent = get_agent(self.agent)
        return {"agent": agent.title if agent else self.agent, "instruction": self.instruction[:200]}


@dataclass
class Plan:
    steps: list[PlanStep]
    source: str  # template | model | fallback
    unsupported: str | None = None  # e.g. "email"

    def to_public(self) -> dict[str, Any]:
        return {"steps": [s.to_public() for s in self.steps], "source": self.source}


INTENT_TO_AGENT: dict[Intent, str] = {
    Intent.CONVERSATION: "conversation",
    Intent.RESEARCH: "research",
    Intent.WEATHER: "research",
    Intent.COMPUTER: "computer",
    Intent.CODING: "coding",
    Intent.FILE_ANALYSIS: "file",
    Intent.STUDY: "study",
    Intent.REMINDER: "automation",
    Intent.AUTOMATION: "automation",
    Intent.TASKS: "automation",
    Intent.MEMORY_STORE: "memory",
    Intent.MEMORY_RECALL: "memory",
    Intent.VISION: "vision",
}
# Canonical order for deterministic multi-step plans: gather → act → explain.
_ORDER = ["memory", "file", "research", "computer", "coding", "vision", "study", "automation", "conversation"]

PLANNER_PROMPT = """You are the task planner inside NEXUS, a personal AI assistant. Split the user's request into
the fewest steps, each handled by one agent. Later steps automatically receive earlier steps' results.

Agents:
- research: web search, reading web pages, comparing sources, weather forecasts
- file: find/extract content from the user's uploaded files
- study: explain, summarise, quiz, revision notes (uses the user's documents)
- memory: store or recall facts about the user
- computer: open apps/folders/URLs, run approved commands, take screenshots
- coding: inspect/fix/test code in the user's projects
- vision: analyse images/screenshots
- automation: reminders, tasks, recurring automations (news digests, price or rain alerts)
- conversation: general chat and knowledge questions

Return ONLY JSON: {"steps": [{"agent": "<name>", "instruction": "<what this agent must do>"}]}
Use 1-3 steps. Do not add steps the user did not ask for."""


def _single(agent: str, instruction: str, **options: Any) -> Plan:
    return Plan([PlanStep(agent, instruction, options)], "template")


def template_plan(text: str, intent: IntentResult) -> Plan | None:
    strong = intent.strong
    if intent.has(Intent.EMAIL, 0.8) and len(strong) <= 1:
        return Plan([], "template", unsupported="email")
    if intent.has(Intent.CALENDAR, 0.8) and len(strong) <= 1:
        return Plan([], "template", unsupported="calendar")

    if intent.has(Intent.SCREEN):
        return Plan([
            PlanStep("computer", "Capture one screenshot of the user's screen.", {"mode": "screenshot"}),
            PlanStep("vision", f"Analyse the screenshot to answer: {text}"),
        ], "template")
    if intent.has_images:
        return _single("vision", f"Analyse the attached image(s) to answer: {text}")
    if intent.has_documents:
        if intent.has(Intent.STUDY):
            return Plan([
                PlanStep("file", "Retrieve the passages relevant to the request.", {"mode": "retrieve"}),
                PlanStep("study", f"Using the retrieved passages, respond to: {text}"),
            ], "template")
        return _single("file", f"Work with the attached document(s) to respond to: {text}")
    if intent.has(Intent.WEATHER) and intent.has(Intent.REMINDER):
        return Plan([
            PlanStep("research", "Get the weather forecast relevant to the request (use get_weather)."),
            PlanStep("automation", f"Based on the forecast from the previous step, handle: {text}"),
        ], "template")

    if len(strong) == 1 or (len(strong) == 0 and intent.scores):
        primary = strong[0] if strong else intent.primary
        agent = INTENT_TO_AGENT.get(primary)
        if agent:
            return _single(agent, text)
    return None


def fallback_plan(text: str, intent: IntentResult) -> Plan:
    agents: list[str] = []
    for i in intent.strong or [intent.primary]:
        a = INTENT_TO_AGENT.get(i)
        if a and a not in agents:
            agents.append(a)
    agents.sort(key=lambda a: _ORDER.index(a) if a in _ORDER else 99)
    if not agents:
        agents = ["conversation"]
    agents = agents[:3]
    steps = [PlanStep(a, text if len(agents) == 1 else f"Handle the part of this request that fits your role: {text}")
             for a in agents]
    return Plan(steps, "fallback")


def _parse_plan_json(raw: str) -> list[PlanStep] | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    steps = []
    for item in (data.get("steps") or [])[:3]:
        name = str(item.get("agent", "")).strip().lower()
        instruction = str(item.get("instruction", "")).strip()
        if get_agent(name) is None or not instruction:
            return None
        steps.append(PlanStep(name, instruction[:1000]))
    return steps or None


async def plan(text: str, intent: IntentResult, provider: AIProvider | None,
               history: list[dict[str, str]] | None = None) -> Plan:
    templated = template_plan(text, intent)
    if templated is not None:
        return templated
    if provider is None:
        return fallback_plan(text, intent)
    recent = "\n".join(f"{t['role']}: {t['content'][:300]}" for t in (history or [])[-4:])
    prompt = (f"Recent conversation:\n{recent}\n\n" if recent else "") + f"User request: {text}"
    try:
        resp = await provider.generate(system=PLANNER_PROMPT, messages=[ChatMessage.user(prompt)],
                                       effort=get_settings().ai_effort_routing, max_tokens=2000)
        steps = _parse_plan_json(resp.text)
    except Exception as exc:  # planning must never break the request
        logger.warning("Model planning failed, using fallback plan: %s", exc)
        steps = None
    if not steps:
        return fallback_plan(text, intent)
    return Plan(steps, "model")
