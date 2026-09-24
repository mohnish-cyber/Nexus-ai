"""Agent interface.

Every agent declares: name, purpose, allowed tools, input schema (AgentTask),
output schema (AgentResult), error handling and a permission ceiling. Agents
never call each other - NexusCore passes one agent's result to the next as
context.

To add an agent (e.g. EmailAgent): subclass `Agent`, list its tools, write its
instructions, and register it in `app/agents/registry.py`.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import BaseModel, Field

from app.core.errors import ErrorInfo, NexusError
from app.core.personality import agent_system_prompt
from app.security.risk import RiskLevel
from app.services.ai.base import (
    AIProvider,
    ChatMessage,
    ImagePart,
    Part,
    ProviderResponse,
    TextCallback,
    TextPart,
    ToolResultPart,
)
from app.tools.executor import execute_tool
from app.tools.registry import get_tool, specs_for

if TYPE_CHECKING:
    from app.core.context import RequestContext

logger = logging.getLogger(__name__)


class AgentTask(BaseModel):
    """Input schema for every agent."""

    instruction: str = Field(description="What NexusCore wants this agent to do")
    user_message: str = Field(description="The user's original message")
    context: str = Field(default="", description="Per-request context: time, memories, previous step results")
    history: list[dict[str, str]] = Field(default_factory=list, description="Recent conversation turns")
    image_file_ids: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict, description="Step options set by the planner")
    voice: bool = False


class AgentResult(BaseModel):
    """Output schema for every agent."""

    agent: str
    status: Literal["succeeded", "failed", "needs_input"]
    answer: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    streamed: bool = False  # True when `answer` was already streamed to the client

    @classmethod
    def failure(cls, agent: str, error: ErrorInfo, answer: str | None = None) -> AgentResult:
        text = answer or format_error(error)
        return cls(agent=agent, status="failed", answer=text, error=error.to_dict())


def format_error(error: ErrorInfo) -> str:
    parts = [error.message]
    if error.reason:
        parts.append(f"Reason: {error.reason}")
    if error.next_step:
        parts.append(f"Next step: {error.next_step}")
    return "\n\n".join(parts)


class SegmentRelay:
    """Streams text deltas to the client. If the model turn ends in tool calls,
    the streamed text was an interim note, so the client is told to discard
    that segment from the live answer."""

    def __init__(self, ctx: RequestContext, agent: str) -> None:
        self.ctx = ctx
        self.agent = agent
        self.segment = uuid.uuid4().hex[:8]
        self.streamed = False

    async def on_text(self, delta: str) -> None:
        self.streamed = True
        await self.ctx.emit({"type": "token", "segment": self.segment, "text": delta})

    async def discard(self) -> None:
        if self.streamed:
            await self.ctx.emit({"type": "segment_discard", "segment": self.segment})
        self.segment = uuid.uuid4().hex[:8]
        self.streamed = False


class Agent(abc.ABC):
    name: ClassVar[str]
    title: ClassVar[str]
    purpose: ClassVar[str]
    allowed_tools: ClassVar[frozenset[str]] = frozenset()
    # Highest-risk tool this agent may request (the user still approves each one).
    permission_level: ClassVar[RiskLevel] = RiskLevel.LOW
    requires_ai: ClassVar[bool] = True
    max_steps: ClassVar[int] = 8
    timeout_seconds: ClassVar[float] = 600.0
    instructions: ClassVar[str] = ""

    # ------------------------------------------------------------------
    def system_prompt(self) -> str:
        return agent_system_prompt(self.instructions)

    def info(self) -> dict[str, Any]:
        tools = []
        for name in sorted(self.allowed_tools):
            tool = get_tool(name)
            if tool is not None:
                tools.append({"name": name, "risk": tool.risk.value, "description": tool.description})
        return {
            "name": self.name,
            "title": self.title,
            "purpose": self.purpose,
            "tools": tools,
            "permission_level": self.permission_level.value,
            "requires_ai": self.requires_ai,
            "input_schema": AgentTask.model_json_schema(),
            "output_schema": AgentResult.model_json_schema(),
            "status": "available",
        }

    # ------------------------------------------------------------------
    async def fallback(self, task: AgentTask, ctx: RequestContext) -> AgentResult | None:
        """Deterministic handling used when no AI provider is configured (or
        for requests simple enough not to need one). Return None to decline."""
        return None

    async def prefer_fallback(self, task: AgentTask, ctx: RequestContext) -> bool:
        """Whether this request should use the deterministic path even when AI is available."""
        return False

    async def run(self, task: AgentTask, ctx: RequestContext, provider: AIProvider | None,
                  stream: bool = False) -> AgentResult:
        if provider is None or await self.prefer_fallback(task, ctx):
            result = await self.fallback(task, ctx)
            if result is not None:
                return result
            if provider is None:
                return AgentResult.failure(self.name, ErrorInfo(
                    "ai_not_configured",
                    f"{self.title} needs the AI core, which is not connected yet.",
                    reason="No AI provider API key is configured.",
                    next_step="Add your Anthropic API key in Settings → API keys.",
                ))
        return await self.run_llm(task, ctx, provider, stream=stream)

    async def build_user_turn(self, task: AgentTask, ctx: RequestContext) -> ChatMessage:
        text = (
            f"<context>\n{task.context.strip()}\n</context>\n\n"
            f"<task_from_nexus_core>\n{task.instruction.strip()}\n</task_from_nexus_core>\n\n"
            f"User message: {task.user_message.strip()}"
        )
        parts: list[Part] = []
        if task.image_file_ids:
            from app.services import files as file_service

            for fid in task.image_file_ids[:5]:
                try:
                    row = await file_service.get_file(ctx.user.id, uuid.UUID(fid))
                    media, data = await file_service.image_b64(row)
                    parts.append(ImagePart(media, data))
                    parts.append(TextPart(f"(Image above: {row.filename}, file id {row.id})"))
                except (NexusError, ValueError) as exc:
                    logger.info("Skipping image %s: %s", fid, exc)
        parts.append(TextPart(text))
        return ChatMessage(role="user", content=parts)

    async def run_llm(self, task: AgentTask, ctx: RequestContext, provider: AIProvider, *, stream: bool) -> AgentResult:
        messages: list[ChatMessage] = []
        for turn in task.history[-10:]:
            if turn.get("content"):
                messages.append(ChatMessage(role="user" if turn["role"] == "user" else "assistant",
                                            content=turn["content"]))
        # The API requires the first message to be from the user.
        while messages and messages[0].role != "user":
            messages.pop(0)
        messages.append(await self.build_user_turn(task, ctx))
        try:
            text, streamed = await asyncio.wait_for(
                run_tool_loop(self, provider, messages, ctx, stream=stream), timeout=self.timeout_seconds
            )
        except TimeoutError:
            return AgentResult.failure(self.name, ErrorInfo("agent_timeout", f"{self.title} ran out of time.",
                                                            next_step="Try a narrower request."))
        except NexusError as exc:
            return AgentResult.failure(self.name, exc.info)
        return AgentResult(agent=self.name, status="succeeded", answer=text, streamed=streamed)


def _is_low_risk(name: str) -> bool:
    tool = get_tool(name)
    return tool is not None and tool.risk == RiskLevel.LOW


async def run_tool_loop(agent: Agent, provider: AIProvider, messages: list[ChatMessage], ctx: RequestContext, *,
                        stream: bool = False) -> tuple[str, bool]:
    """The agentic loop: model -> tools -> model ... until a final answer."""
    tools = specs_for(agent.allowed_tools) if agent.allowed_tools else None
    system = agent.system_prompt()
    relay = SegmentRelay(ctx, agent.name) if stream else None
    for step in range(agent.max_steps + 1):
        if ctx.cancelled:
            raise asyncio.CancelledError()
        final_round = step == agent.max_steps
        if final_round and tools:
            last = messages[-1]
            if isinstance(last.content, list):
                last.content.append(TextPart("You have used the maximum number of tool calls. Do not call more "
                                             "tools; give your best final answer now, stating what is incomplete."))
        on_text: TextCallback | None = relay.on_text if relay else None
        resp: ProviderResponse = await provider.generate(system=system, messages=messages, tools=tools, on_text=on_text)
        if resp.stop_reason == "refusal":
            if relay:
                await relay.discard()
            return ("I can't help with that request. If you think this is a mistake, try rephrasing it "
                    "with more context."), False
        messages.append(resp.as_message())
        if not resp.tool_calls or final_round:
            text = resp.text.strip()
            if resp.stop_reason == "max_tokens":
                text += "\n\n_(The answer was cut off because it reached the length limit.)_"
            return text, bool(relay and relay.streamed)
        if relay:
            await relay.discard()
        await ctx.set_state("executing", None)
        allowed = set(agent.allowed_tools)
        if all(_is_low_risk(tc.name) for tc in resp.tool_calls):
            executions = await asyncio.gather(*[
                execute_tool(ctx, tc.name, tc.arguments, agent=agent.title, allowed_tools=allowed)
                for tc in resp.tool_calls
            ])
        else:
            executions = []
            for tc in resp.tool_calls:
                executions.append(await execute_tool(ctx, tc.name, tc.arguments, agent=agent.title,
                                                     allowed_tools=allowed))
        results: list[Part] = [
            ToolResultPart(tool_call_id=tc.id, content=ex.model_content(), is_error=not ex.ok)
            for tc, ex in zip(resp.tool_calls, executions, strict=True)
        ]
        messages.append(ChatMessage(role="user", content=results))
        await ctx.set_state("thinking", None)
    return "", False
