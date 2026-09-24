"""Agent registry: the agents NexusCore can route to, plus the roadmap of
planned agents (shown in the UI as not yet available - never routable)."""

from __future__ import annotations

from typing import Any

from app.agents.automation_agent import AutomationAgent
from app.agents.base import Agent
from app.agents.coding_agent import CodingAgent
from app.agents.computer_agent import ComputerAgent
from app.agents.conversation_agent import ConversationAgent
from app.agents.file_agent import FileAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.research_agent import ResearchAgent
from app.agents.study_agent import StudyAgent
from app.agents.vision_agent import VisionAgent

_AGENTS: dict[str, Agent] = {}

PLANNED_AGENTS: list[dict[str, Any]] = [
    {"name": "email", "title": "EmailAgent", "purpose": "Read, summarise and draft emails (sending always needs approval)."},
    {"name": "calendar", "title": "CalendarAgent", "purpose": "Check your schedule and create events."},
    {"name": "home", "title": "HomeAgent", "purpose": "Control smart-home devices."},
    {"name": "finance", "title": "FinanceAgent", "purpose": "Track budgets and expenses (read-only by default)."},
    {"name": "travel", "title": "TravelAgent", "purpose": "Plan trips and compare travel options."},
    {"name": "security", "title": "SecurityAgent", "purpose": "Audit NEXUS permissions and detect risky activity."},
]


def register(agent: Agent) -> None:
    _AGENTS[agent.name] = agent


def _ensure_loaded() -> None:
    if _AGENTS:
        return
    for agent in (ConversationAgent(), ResearchAgent(), FileAgent(), StudyAgent(), MemoryAgent(), ComputerAgent(),
                  CodingAgent(), VisionAgent(), AutomationAgent()):
        register(agent)


def get_agent(name: str) -> Agent | None:
    _ensure_loaded()
    return _AGENTS.get(name)


def all_agents() -> list[Agent]:
    _ensure_loaded()
    return list(_AGENTS.values())


def agent_catalog() -> list[dict[str, Any]]:
    _ensure_loaded()
    items = [a.info() for a in _AGENTS.values()]
    items += [{**p, "status": "planned", "tools": [], "requires_ai": True} for p in PLANNED_AGENTS]
    return items
