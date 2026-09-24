from __future__ import annotations

from app.agents.base import Agent


class ConversationAgent(Agent):
    """NexusCore's own voice for normal conversation."""

    name = "conversation"
    title = "NexusCore"
    purpose = "Everyday conversation, quick answers and general knowledge."
    allowed_tools = frozenset({"recall", "get_weather", "list_tasks", "get_system_status"})
    max_steps = 3
    instructions = """
You are handling a general conversational request. Answer directly from your knowledge and the provided
context. Use a tool only when it clearly helps (recall a memory, check weather, list today's tasks, read
system status). If the request needs capabilities you don't have in this role (web research, files,
computer control), say briefly what NEXUS would need rather than guessing.
"""
