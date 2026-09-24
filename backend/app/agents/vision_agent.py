from __future__ import annotations

from app.agents.base import Agent, AgentResult, AgentTask
from app.core.context import RequestContext
from app.core.errors import ErrorInfo
from app.services.ai.base import AIProvider


class VisionAgent(Agent):
    name = "vision"
    title = "VisionAgent"
    purpose = "Understands screenshots, error dialogs, photos, charts and code screenshots."
    allowed_tools = frozenset()
    max_steps = 1
    instructions = """
You are VisionAgent. Analyse the attached image(s) carefully.

For screenshots with errors: quote the exact error text you can read, identify the application/context,
explain the likely cause in plain language, and give a short numbered fix. Mark anything you can't read
clearly as uncertain. Do not claim to have performed any fix - only NEXUS's other agents can act, and only
with permission.
For charts: state what is plotted, the key trends and notable values.
For photos: describe what is relevant to the user's question.
For code screenshots: transcribe the relevant code and point out problems.

Structure (omit sections that don't apply): **What I see**, **Likely problem**, **How to fix it**.
"""

    async def run(self, task: AgentTask, ctx: RequestContext, provider: AIProvider | None,
                  stream: bool = False) -> AgentResult:
        if not task.image_file_ids:
            return AgentResult.failure(self.name, ErrorInfo(
                "no_image", "There's no image to analyse.",
                next_step="Attach a screenshot or photo, or use “Capture screen” in the chat bar."))
        if provider is None:
            return AgentResult.failure(self.name, ErrorInfo(
                "ai_not_configured", "Image analysis needs the AI core, which is not connected yet.",
                next_step="Add your Anthropic API key in Settings → API keys."))
        if not provider.supports_vision:
            return AgentResult.failure(self.name, ErrorInfo(
                "vision_unsupported", f"The configured model ({provider.model}) can't read images.",
                next_step="Use a vision-capable model such as claude-opus-5."))
        return await self.run_llm(task, ctx, provider, stream=stream)
