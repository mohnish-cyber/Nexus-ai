# NEXUS — Personal AI Operating System

NEXUS is a voice-capable personal AI assistant that understands natural-language commands, remembers what
matters, reads your documents, researches the web, manages tasks and reminders, runs background automations,
and — with your explicit permission — controls parts of your computer. It delegates work to specialised agents
behind a single, calm conversational interface.

It is local-first: in the default mode everything (database, files, API keys) lives on your machine.

```
You ──voice / text / files / screenshots──▶ NexusCore
                                             ├─ intent detection   (instant, rule-based)
                                             ├─ task planner       (templates, or the model for mixed requests)
                                             ├─ agent router ──▶ Research · File · Study · Memory · Computer
                                             │                   Coding · Vision · Automation · Conversation
                                             │                        └─▶ tools (permission-gated, audited)
                                             ├─ result verifier    (checks claims against the action ledger)
                                             └─ memory update      (suggestions you approve)
                                           ◀── streamed reply · spoken reply · live activity feed
```

## What works today

| Area | Capability |
|---|---|
| **Conversation** | Streaming chat over WebSockets, conversation history, Markdown answers, sources, and a verified *action ledger* under every reply |
| **Voice** | Push-to-talk (orb, mic button or `Ctrl+Shift+Space`) with server Whisper or browser recognition; spoken replies (browser voices, or OpenAI/ElevenLabs); experimental opt-in “Hey Nexus” wake phrase |
| **Memory** | “My college AI project is LinkGuard AI” → later “open my college AI project” resolves it. Explicit memory rules, approval for inferred/personal facts, never stores secrets. View, edit, approve and delete everything |
| **Files & study** | PDF, DOCX, text, code and image uploads validated by content; heading-aware chunking + BM25 retrieval (“explain Unit 3” retrieves Unit 3 only); StudyAgent separates **From your document** from **General knowledge** |
| **Research** | Tavily / Brave / SearXNG search, SSRF-safe page reading, optional headless browser (Playwright), cited answers; Open-Meteo weather with no key |
| **Computer** | Launch an allowlist of apps (VS Code, browser, terminal…), open folders/files, open URLs, run allowlisted dev commands, screenshots with per-use approval, delete-to-trash (high risk) |
| **Coding** | Inspect → diagnose → plan → minimal edit (diff shown in the approval) → test → verify, confined to authorised folders with backups |
| **Vision** | Screenshots, error dialogs, charts and photos — attach an image or use **Capture screen** (one frame, browser permission) |
| **Tasks & automations** | Natural-language reminders and tasks; database-backed scheduler (embedded or separate worker) for reminders, AI news digests, price watches and rain alerts, with notifications |
| **Observability** | Live activity panel, agent runs, tool calls, approval history and audit log — concise action summaries, never private reasoning |
| **Dashboard** | Command-centre UI with an animated canvas orb (idle / listening / thinking / speaking / executing / awaiting approval / error), real host telemetry, responsive down to phone width |

Without an AI key NEXUS runs in **limited mode**: memory, reminders, tasks, “what tasks do I have today?”, app
launching, weather, and file search still work deterministically, and everything else explains what's missing.

## Quick start

Requirements: Python 3.11+, Node.js 20+.

```bash
git clone <this repo> nexus-ai && cd nexus-ai
cp .env.example .env            # optional — add ANTHROPIC_API_KEY here or later in Settings
./scripts/dev.sh                # installs deps on first run, starts backend :8000 and frontend :5173
```

Open **http://localhost:5173**. The boot sequence shows the real status of each subsystem.

Manual setup, if you prefer:

```bash
# backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"                 # add ",desktop" for screenshots + headless browser
python -m app                           # http://127.0.0.1:8000  (API docs: /api/docs)

# frontend (second terminal)
cd frontend
npm install
npm run dev                             # http://localhost:5173 (proxies /api and /ws to :8000)
```

Single-process mode: `cd frontend && npm run build`, then start only the backend — it serves the built app at
http://127.0.0.1:8000.

### Connecting the AI core

Add an Anthropic API key in **Settings → API keys** (stored encrypted, never shown again) or set
`ANTHROPIC_API_KEY` in `.env`. The default model is `claude-opus-5` with adaptive thinking; change `AI_MODEL` or
`AI_EFFORT_DEFAULT` in `.env`. To run a local model instead, set `AI_PROVIDER=openai_compatible` with
`OPENAI_COMPAT_BASE_URL=http://localhost:11434/v1` and `OPENAI_COMPAT_MODEL=llama3.1` (Ollama).

`AI_PROVIDER=mock` exists for UI development only; every reply it produces is prefixed with `[DEV MOCK]`.

### Optional integrations

| Feature | Configure |
|---|---|
| Web search | `TAVILY_API_KEY` or `BRAVE_SEARCH_API_KEY` (or `SEARXNG_URL`) |
| Server speech-to-text | `OPENAI_API_KEY` (Whisper), or `pip install -e ".[local-stt]"` for offline faster-whisper |
| Server voice | `TTS_PROVIDER=openai` + `OPENAI_API_KEY`, or `elevenlabs` + `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` |
| Screenshots / headless browser | `pip install -e ".[desktop]"` then `playwright install chromium` |
| File & coding access | Settings → Workspace folders (or `WORKSPACE_ROOTS`) |
| Your apps | Settings → Applications (add an executable NEXUS may launch) |

## Try it

- “My college AI project is LinkGuard AI at ~/college/linkguard.” → “Open my college AI project.”
- “Remind me tomorrow at 8 AM to submit my assignment.” · “What tasks do I have today?”
- “Check tomorrow's weather and remind me to take an umbrella if rain is expected.”
- Attach a syllabus PDF → “Read this PDF and explain Unit 3.” → “Make me a 5-question quiz on it.”
- Capture your screen → “What's wrong on my screen? Help me fix it.”
- “Find gaming laptops below ₹60,000.” · “Search the latest AI news.”
- “Every morning at 8 give me five important AI news stories.”
- “Run my project's tests and tell me why they fail.” (needs a workspace folder)

## Safety model (summary)

Every tool declares a risk level and runs through one executor that validates arguments, asks the permission
broker, runs with a timeout, and writes an audit record:

- **Low** (read, search, open an app) → runs automatically.
- **Medium** (edit files, run dev commands, create AI automations, forget a memory) → “NEXUS wants to…” dialog
  with **Allow once / Always allow / Cancel**; always-allow grants are scoped and revocable.
- **High** (delete, install) → always asks; *Always allow* is never offered.
- Background jobs and REST calls can't be approved interactively, so they never run medium/high actions.

Shell commands never go through a shell; only an allowlist of development commands runs. Paths are confined to
authorised folders; credential files are always blocked. Outbound fetches are SSRF-guarded. Web pages,
documents and command output are wrapped as untrusted data. See [docs/SECURITY.md](docs/SECURITY.md).

## Project layout

```
backend/            FastAPI app
  app/core/         NexusCore, intent, planner, router, verifier, personality, memory update
  app/agents/       Specialised agents + registry (planned agents listed, never routed)
  app/tools/        Tool plugins, registry, permission-gated executor
  app/services/     AI providers, documents, memory, scheduler, voice, weather, notifications…
  app/security/     auth, permissions, path/URL/command guards, uploads, redaction, crypto, rate limit
  app/api/          REST routes + WebSocket
  app/models/       SQLAlchemy models (SQLite or PostgreSQL/Supabase)
  app/worker.py     Standalone background scheduler
  tests/            pytest suite (runs on SQLite, or PostgreSQL via NEXUS_TEST_DATABASE_URL)
frontend/           React 19 + TypeScript + Vite + Tailwind CSS 4
  src/components/   orb, chat, activity, permissions, boot, layout, common UI
  src/pages/        Home, Assistant, Tasks, Memory, Files, Automations, Agents, Devices, Settings, Login
  src/stores/       zustand stores (chat event stream, system, voice, settings, notifications, auth)
  src/services/     REST client, WebSocket client, voice (recorder, STT, TTS, wake word)
site/               Marketing site (landing, pricing, docs, live status page); see site/README.md
supabase/migrations Generated PostgreSQL schema with Row Level Security
docs/               Architecture, security, API and extension guides
```

## Tests

```bash
cd backend && .venv/bin/pytest            # 170 tests: security, permissions, agents, pipeline, scheduler, API, WebSocket
cd frontend && npm test && npm run build  # unit tests, type-check, production build
```

Run the backend suite against PostgreSQL:
`NEXUS_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/nexus_test pytest`.

## Multi-user mode (Supabase)

1. Create a Supabase project; apply `supabase/migrations/*.sql` (SQL editor or `supabase db push`).
2. Set `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, `NEXUS_SECRET_KEY`,
   `NEXUS_ADMIN_EMAILS`, and your deployed frontend origin in `CORS_ORIGINS` / host in `ALLOWED_HOSTS`.
3. Computer control is **off** by default in this mode, so remote users can never drive the server.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production notes (external worker, HTTPS, backups).

## Roadmap

- **Phase 1–4 (implemented):** dashboard, orb, chat, voice, AI backend, agents, files, study, memory, research,
  computer control, coding, vision, tasks, reminders, automations, activity dashboard.
- **Phase 5 (planned):** EmailAgent, CalendarAgent, HomeAgent, FinanceAgent, TravelAgent, SecurityAgent
  (listed on the Agents page as *planned*), a desktop build with an on-device wake word (Porcupine /
  openWakeWord), pgvector hybrid retrieval, and a phone companion app. Until then you can open NEXUS in a phone
  browser by running it in Supabase mode behind HTTPS (`python -m app` refuses to listen on a network interface
  in local mode, because local mode has no sign-in).

See [docs/EXTENDING.md](docs/EXTENDING.md) to add your own tools and agents.
