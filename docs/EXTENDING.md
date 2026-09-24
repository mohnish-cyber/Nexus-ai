# Extending NEXUS

## Add a tool

1. Create a class in `backend/app/tools/` (or a new module):

```python
from pydantic import Field

from app.security.risk import RiskLevel
from app.tools.base import Assessment, Tool, ToolOutput, ToolParams


class TranslateParams(ToolParams):
    text: str = Field(min_length=1, max_length=5000)
    target: str = Field(pattern=r"^[a-z]{2}$", description="ISO language code")


class TranslateTool(Tool):
    name = "translate_text"
    description = "Translate text into another language."
    Params = TranslateParams
    risk = RiskLevel.LOW          # LOW runs automatically; MEDIUM/HIGH ask the user
    category = "research"

    async def available(self, ctx):                    # optional: keys, OS support…
        return True, None

    def assess(self, params, ctx) -> Assessment:       # optional: per-call risk, summary, scope, details
        return Assessment(self.risk, f"Translate text to {params.target}")

    async def run(self, params: TranslateParams, ctx) -> ToolOutput:
        translated = ...                               # do the work; raise NexusError subclasses on failure
        return ToolOutput(summary="Translated text", content=translated, data={"target": params.target})
```

2. Register it in `backend/app/tools/registry.py`.
3. Add its name to the `allowed_tools` of the agent(s) that may use it.
4. Add tests (`backend/tests`): happy path, invalid input, and — for MEDIUM/HIGH tools — the approval path.

Rules of thumb:

- External content returned to the model must be wrapped with `wrap_untrusted(...)`.
- Raise `NexusError` subclasses with `message`, `reason`, `next_step`; the executor turns them into clear
  user-facing errors and tells the model the action did not happen.
- Keep `data` small: it is stored in the message's action ledger and shown in the UI.
- Paths must go through `resolve_within(...)`; URLs through `validate_url`/`safe_fetch`; commands through
  `validate_command`/`run_validated`.

## Add an agent (e.g. EmailAgent)

```python
from app.agents.base import Agent
from app.security.risk import RiskLevel


class EmailAgent(Agent):
    name = "email"
    title = "EmailAgent"
    purpose = "Reads, summarises and drafts email. Sending always needs approval."
    allowed_tools = frozenset({"list_emails", "read_email", "draft_email", "send_email"})
    permission_level = RiskLevel.HIGH
    instructions = """You are EmailAgent. Summarise before quoting. Never send without the user's approval..."""
```

1. Register it in `backend/app/agents/registry.py` (and remove it from `PLANNED_AGENTS`).
2. Route to it: add the intent → agent mapping in `core/planner.py` (`INTENT_TO_AGENT`) and, if needed, a rule
   in `core/intent.py`; describe it in `PLANNER_PROMPT` so model-built plans can use it.
3. Mark send-like tools `RiskLevel.HIGH` with `allow_always = False`.
4. Optionally implement `fallback()` for requests that don't need the model.

## Add an AI provider

Implement `AIProvider.generate()` (and `health()`) in `backend/app/services/ai/`, returning
`ProviderResponse` with normalised `tool_calls` and `stop_reason`, then select it in
`services/ai/factory.py`. Agents don't change.

## Add a speech engine

Implement `STTProvider.transcribe()` or `TTSProvider.synthesize()` in `backend/app/services/voice/` and
select it in `get_stt()` / `get_tts()`. The browser falls back to Web Speech automatically when no server
engine is configured. For an on-device wake word, replace `frontend/src/services/voice/wakeword.ts` with a
Porcupine or openWakeWord implementation exposing the same `start/pause/resume/stop` interface.

## Change the database schema

Edit the models in `backend/app/models`, then regenerate the Supabase migration:

```bash
cd backend && python -m scripts.export_schema > ../supabase/migrations/<timestamp>_<change>.sql
```

`tests/test_schema.py` fails if the committed migration and the models disagree.
