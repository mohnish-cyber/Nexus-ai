# NEXUS architecture

NEXUS is split into clear layers. Each layer only talks to the one below it.

| Layer | Where | Responsibility |
|---|---|---|
| UI | `frontend/src` | Dashboard, orb, chat, voice capture/playback, approval dialog |
| Transport | `backend/app/api` | REST routes, WebSocket event stream, auth, rate limits, error mapping |
| Reasoning | `backend/app/core` | NexusCore: intent → plan → route → verify → persist → memory update |
| Agents | `backend/app/agents` | Specialists with fixed tool sets, instructions and fallbacks |
| Tools | `backend/app/tools` | Individual capabilities behind a registry and one permission-gated executor |
| Services | `backend/app/services` | AI providers, documents, memory, scheduler, voice, weather, notifications |
| Security | `backend/app/security` | Auth, permissions, path/URL/command guards, uploads, redaction, crypto |
| Data | `backend/app/models`, `database` | SQLAlchemy models; SQLite locally, PostgreSQL/Supabase in production |
| Automation | `backend/app/services/scheduler.py`, `app/worker.py` | Database-backed background jobs |

## Request lifecycle

1. **Input.** The browser sends `{"type": "chat", text, attachments, voice}` over `/ws` (or `POST /api/chat`).
   Voice is transcribed first (server Whisper or browser recognition); files are uploaded to `/api/files`
   beforehand and referenced by id.
2. **Context.** `NexusCore.handle` stores the user message, loads the last turns of the conversation
   (short-term memory), recalls relevant long-term memories (`memory_context`), loads attachments, and
   builds a per-request context block (time in the user's timezone, location, authorised folders, memories,
   files, voice flag). The system prompt stays byte-stable so it can be prompt-cached; everything that
   varies goes into the user turn.
3. **Intent detection** (`core/intent.py`). A rule-based classifier scores intents (conversation, research,
   weather, computer, coding, file analysis, study, reminder, automation, tasks, memory store/recall,
   vision, screen, email, calendar) using the text and attachment types, then disambiguates overlaps
   ("remind me to submit my assignment" is a reminder, not study).
4. **Planning** (`core/planner.py`). Clear requests map to one agent. Known multi-step patterns use
   templates — attached document + study → `file(retrieve) → study`; "my screen" → `computer(screenshot) →
   vision`; weather + reminder → `research → automation`. Anything else with several intents asks the model
   for a small JSON plan, validated against the agent registry; failures fall back to a deterministic plan.
5. **Routing** (`core/router.py`). Each step runs on its agent with an `AgentTask` (instruction, user
   message, context, history, image ids, options). Earlier results are appended to the next step's context —
   agents never call each other. Every run is recorded in `agent_runs` and shown in the activity feed.
6. **Agents** (`agents/base.py`). An agent either answers deterministically (`fallback`, used when no AI
   key is set or for simple requests such as "remind me tomorrow at 8") or runs the tool loop: model turn →
   tool calls → results → model turn, until a final answer. Only the last step streams tokens; interim text
   before a tool call is streamed as a segment and discarded if the turn ends in tool use.
7. **Tools** (`tools/executor.py`). Arguments are validated with pydantic; availability is checked (keys,
   display, OS); the tool assesses the concrete call (risk, summary, scope, diff); the permission broker
   decides or asks the user; the tool runs with a timeout; the call is audited in `tool_calls` and appended
   to the request's **action ledger**.
8. **Verification** (`core/verifier.py`). The final text is checked for claims ("I've set a reminder",
   "I opened VS Code", "I deleted…") that have no matching successful action in the ledger. Unbacked claims
   get an explicit correction appended. The UI renders the ledger itself, so what the user sees as "done"
   always comes from tool results, never from model prose.
9. **Persistence & memory update.** The reply is saved with its ledger, sources and plan. In the
   background, `memory_update` looks for durable facts the user mentioned in passing and stores them as
   *pending* suggestions (never silently).

## Agents

| Agent | Tools | Notes |
|---|---|---|
| NexusCore (conversation) | recall, get_weather, list_tasks, get_system_status | General answers |
| ResearchAgent | web_search, fetch_webpage, browse_page, get_weather | Cites sources; weather needs no AI |
| FileAgent | list_files, search_files, get_file_outline, read_file_section | Retrieval mode feeds StudyAgent |
| StudyAgent | same file tools | Separates document facts from general knowledge |
| MemoryAgent | remember, recall, list_memories, forget | Deterministic for common phrasings |
| ComputerAgent | open_application, open_path, open_url, run_command, take_screenshot, list_applications, get_system_status, recall, delete_path | Resolves "my project" via memory |
| CodingAgent | list_directory, read_text_file, search_code, write_file, edit_file, run_command, recall, file tools | Inspect → diagnose → plan → modify → test → verify → report |
| VisionAgent | (model vision) | Images from attachments or a screenshot step |
| AutomationAgent | create_reminder, create_task, list_tasks, complete_task, create_automation, list_automations, cancel_automation, get_weather | Deterministic reminders/tasks |

Planned (visible, never routed): EmailAgent, CalendarAgent, HomeAgent, FinanceAgent, TravelAgent,
SecurityAgent.

## AI provider abstraction

`services/ai/base.py` defines provider-neutral messages, tool specs and responses. Implementations:

- `AnthropicProvider` — official SDK, streaming, tool use with `eager_input_streaming`, images, adaptive
  thinking with configurable effort, server-side refusal fallback, prompt caching of the frozen system
  prompt, and a free `models.retrieve` health check for the boot sequence. Truncated (`max_tokens`) tool
  calls are never executed; refusals are handled explicitly.
- `OpenAICompatibleProvider` — any `/v1/chat/completions` endpoint (Ollama, LM Studio, vLLM).
- `DevMockProvider` (`AI_PROVIDER=mock`, labelled `[DEV MOCK]`) and `ScriptedProvider` (tests).

## Memory

- **Short-term:** conversation messages (`messages`), last 12 turns passed to agents.
- **Long-term:** structured `memories` (category, subject, value, aliases, attributes such as `path`,
  source explicit/inferred, status active/pending, sensitivity). Recall scores subject/alias/value overlap;
  "open my college AI project" matches the memory whose subject is "college AI project".
- **Rules:** see `services/memory_service.py` — never store secrets, card or ID numbers; approval for
  inferred and personal-sensitive facts; skip temporary states; explicit requests are stored.

## Files and retrieval

Uploads are identified by magic bytes, stored under random names, parsed (pypdf, python-docx, UTF-8
text), and chunked by heading so a chunk never spans two sections (`Unit 3`, `Chapter 2`, Markdown/Word
headings, code symbols). Retrieval is BM25 with a strong boost for section references; a query naming a unit
returns that unit's chunks in document order. The retriever interface is small so a pgvector hybrid can be
added without touching agents.

## Automations

`automations` rows hold kind, trigger (`once` / `interval` / `cron`), schedule, timezone, config, status and
`next_run_at`. The scheduler polls, claims due jobs with a lease (`locked_until`) so multiple instances never
double-run, executes by kind, evaluates conditions (price below threshold, rain expected), writes
`automation_runs` and `notifications`, computes the next run (croniter, user timezone), and backs off on
failure (stopping after 5 consecutive failures with a notification). Agent tasks run NexusCore
non-interactively, so they can't perform actions that need approval.

Notifications are written to the database; a relay in the API process pushes new rows to connected
WebSockets. The same path works whether the scheduler is embedded or runs in `python -m app.worker`.

## Frontend

- `services/ws.ts` — authenticated WebSocket with queueing, heartbeats and backoff reconnects.
- `stores/chatStore.ts` — reduces the server event stream (status, plan, activity, token, segment_discard,
  permission_request, message, notification, done) into conversation state.
- `components/orb/NexusOrb.tsx` — Canvas 2D orb with per-state palettes, energy, particle orbits, plasma
  filaments, audio ripples and completion/error flashes; pauses when the tab is hidden and respects
  reduced motion.
- `stores/voiceStore.ts` — push-to-talk via MediaRecorder (server STT) or Web Speech recognition, live mic
  level for the orb, opt-in wake phrase; `hooks/useSpeechOutput.ts` speaks replies.
- Pages are lazy-loaded and wrapped in error boundaries.
