"""Central tool registry.

Tools are registered once at import time. Agents reference tools by name in
their `allowed_tools`; NexusCore/agents only ever see the specs of the tools
an agent is allowed to use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.ai.base import ToolSpec

if TYPE_CHECKING:
    from app.tools.base import Tool

_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.name in _TOOLS:
        raise ValueError(f"Duplicate tool name: {tool.name}")
    _TOOLS[tool.name] = tool
    return tool


def _ensure_loaded() -> None:
    if _TOOLS:
        return
    from app.tools import browser, code, computer, files, memory, tasks, weather, web

    for tool in (
        web.WebSearchTool(),
        web.FetchWebpageTool(),
        browser.BrowsePageTool(),
        weather.WeatherTool(),
        files.ListFilesTool(),
        files.SearchFilesTool(),
        files.FileOutlineTool(),
        files.ReadFileSectionTool(),
        memory.RememberTool(),
        memory.RecallTool(),
        memory.ListMemoriesTool(),
        memory.ForgetTool(),
        tasks.CreateReminderTool(),
        tasks.CreateTaskTool(),
        tasks.ListTasksTool(),
        tasks.CompleteTaskTool(),
        tasks.CreateAutomationTool(),
        tasks.ListAutomationsTool(),
        tasks.CancelAutomationTool(),
        computer.OpenApplicationTool(),
        computer.OpenPathTool(),
        computer.OpenUrlTool(),
        computer.RunCommandTool(),
        computer.ScreenshotTool(),
        computer.DeletePathTool(),
        computer.ListApplicationsTool(),
        computer.SystemStatusTool(),
        code.ListDirectoryTool(),
        code.ReadTextFileTool(),
        code.SearchCodeTool(),
        code.WriteFileTool(),
        code.EditFileTool(),
    ):
        register(tool)


def get_tool(name: str) -> Tool | None:
    _ensure_loaded()
    return _TOOLS.get(name)


def all_tools() -> list[Tool]:
    _ensure_loaded()
    return list(_TOOLS.values())


def specs_for(names: list[str] | set[str]) -> list[ToolSpec]:
    _ensure_loaded()
    # Deterministic order keeps the prompt-cache prefix stable.
    return [_TOOLS[n].spec() for n in sorted(names) if n in _TOOLS]
