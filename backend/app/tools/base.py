"""Tool plugin interface.

A tool is a single capability (search the web, open an app, create a
reminder...). Each tool declares its name, description, typed parameters,
risk level and execution function. Tools never decide on their own whether
they are allowed to run - the ToolExecutor asks the PermissionBroker first.

To add a tool: subclass `Tool`, define `Params`, implement `run`, and add it
to `app/tools/registry.py`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

from app.security.risk import RiskLevel
from app.services.ai.base import ToolSpec

if TYPE_CHECKING:
    from app.core.context import RequestContext


class ToolParams(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NoParams(ToolParams):
    pass


@dataclass
class ToolOutput:
    summary: str  # one line, shown in the activity panel and the action ledger
    content: str  # what the model sees (external data must already be wrapped)
    data: dict[str, Any] = field(default_factory=dict)  # structured result for the UI


@dataclass
class Assessment:
    """Dynamic, per-call view of a tool invocation used for permissions."""

    risk: RiskLevel
    summary: str  # e.g. "Delete project/test.txt"
    scope: str = "*"  # what an "Always Allow" grant would cover
    details: dict[str, Any] = field(default_factory=dict)


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop pydantic's noisy 'title' keys to keep tool definitions compact."""
    if isinstance(schema, dict):
        return {k: _clean_schema(v) for k, v in schema.items() if k != "title" or not isinstance(v, str)}
    if isinstance(schema, list):
        return [_clean_schema(v) for v in schema]  # type: ignore[return-value]
    return schema


class Tool(abc.ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Params: ClassVar[type[ToolParams]] = NoParams
    risk: ClassVar[RiskLevel] = RiskLevel.LOW
    category: ClassVar[str] = "general"
    # Whether "Always Allow" may be offered for MEDIUM-risk calls of this tool.
    allow_always: ClassVar[bool] = True
    timeout_seconds: ClassVar[float] = 60.0

    def spec(self) -> ToolSpec:
        schema = _clean_schema(self.Params.model_json_schema())
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        return ToolSpec(name=self.name, description=self.description, input_schema=schema)

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        """Whether the tool can run in this environment (keys, OS support...)."""
        return True, None

    def assess(self, params: Any, ctx: RequestContext) -> Assessment:
        return Assessment(risk=self.risk, summary=self.describe_call(params))

    def describe_call(self, params: Any) -> str:
        return self.name.replace("_", " ")

    @abc.abstractmethod
    async def run(self, params: Any, ctx: RequestContext) -> ToolOutput: ...

    def public_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk.value,
            "category": self.category,
            "parameters": self.spec().input_schema,
        }
