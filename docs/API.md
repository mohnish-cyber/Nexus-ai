# NEXUS API

Interactive OpenAPI docs are served at `/api/docs` in development. All errors share one shape:

```json
{ "error": { "code": "executable_not_found",
             "message": "VS Code could not be opened because the executable was not found.",
             "reason": "None of ['code', 'codium'] is installed or on PATH.",
             "next_step": "Install VS Code, or register its executable in Settings → Applications." } }
```

In Supabase mode send `Authorization: Bearer <access token>` on every request.

## WebSocket `/ws`

1. Connect (same origin or an origin listed in `CORS_ORIGINS`).
2. First message: `{"type": "auth", "token": "<access token or null in local mode>"}` → `{"type": "ready", "user": {...}}`.

Client → server

| type | fields |
|---|---|
| `chat` | `request_id`, `text`, `conversation_id?`, `attachments: [file ids]`, `voice: bool` |
| `permission_decision` | `permission_id`, `decision`: `allow_once` \| `always_allow` \| `deny` |
| `cancel` | `request_id` |
| `ping` | — (server replies `pong`) |

Server → client (all request-scoped events carry `request_id`)

| type | meaning |
|---|---|
| `status` | `state`: thinking / executing / waiting / completed / error / idle, optional `label` |
| `conversation` | conversation id + title (created on the first message) |
| `plan` | the agent steps NexusCore chose, and the intent scores |
| `activity` | `id`, `agent`, `action`, `status` started/succeeded/failed — the same `id` is updated in place |
| `token` | streamed text for `segment` |
| `segment_discard` | drop a streamed segment (it was an interim note before a tool call) |
| `permission_request` | `permission`: id, tool, agent, risk, summary, reason, details (path/command/diff), scope, allow_always, expires_at |
| `permission_resolved` | approval outcome |
| `message` | the final assistant message (content, actions ledger, sources, meta) — replaces streamed text |
| `memory_update` | memories saved (usually pending suggestions) after the turn |
| `notification` | reminder/automation notification pushed from the database |
| `error` | structured error |
| `done` | request finished |

## REST

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/system/config` | Public config (auth mode, Supabase URL + anon key, upload limit) |
| `GET /api/system/status` | Real startup checks per component (database, memory, AI, agents, voice, network, search, scheduler, computer control) |
| `GET /api/system/telemetry` | Host CPU, memory, disk, battery, network (nulls when unavailable) |
| `POST /api/chat` | One-shot chat (non-interactive: approval-requiring actions are declined) |
| `GET /api/conversations` · `GET /api/conversations/{id}/messages` · `PATCH`/`DELETE /api/conversations/{id}` | History |
| `GET/POST /api/memories` · `PATCH/DELETE /api/memories/{id}` · `POST /api/memories/{id}/approve` · `DELETE /api/memories?confirm=true` | Long-term memory |
| `POST /api/files` (multipart `file`) · `GET /api/files` · `GET /api/files/{id}` · `GET /api/files/{id}/content` · `DELETE /api/files/{id}` | Files |
| `GET/POST /api/tasks` · `PATCH/DELETE /api/tasks/{id}` | Tasks (`view` = open, today, overdue, upcoming, done, all) |
| `GET/POST /api/automations` · `PATCH` (pause/resume) · `POST /{id}/run` · `GET /{id}/runs` · `DELETE /{id}` · `POST /api/automations/parse-time` | Automations |
| `GET /api/agents` · `GET /api/tools` · `GET /api/activity` · `GET /api/audit` | Agents, tools, observability |
| `GET /api/permissions/pending` · `POST /api/permissions/{id}/decision` · `GET /api/permissions/grants` · `DELETE /api/permissions/grants/{id}` | Approvals |
| `GET /api/settings` · `PUT /api/settings/{section}` · `PUT/DELETE /api/settings/secrets/{name}` · `POST /api/settings/test-ai` · `GET /api/settings/apps` · `GET /api/settings/export` · `POST /api/settings/erase` | Settings and data ownership |
| `GET /api/voice/status` · `POST /api/voice/transcribe` (multipart `audio`) · `POST /api/voice/speak` | Voice |
| `GET /api/notifications` · `POST /api/notifications/read` | Notifications |
| `GET /api/devices` · `POST /api/devices/heartbeat` · `DELETE /api/devices/{id}` | Devices |

Preference sections: `profile`, `voice`, `permissions`, `memory`, `location`, `regional`, `workspace`, `apps`.
Configurable secrets: `ANTHROPIC_API_KEY`, `OPENAI_COMPAT_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY`,
`BRAVE_SEARCH_API_KEY`, `ELEVENLABS_API_KEY`.
