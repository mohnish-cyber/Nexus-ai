# NEXUS security model

NEXUS can read your files and act on your computer, so safety is enforced in code, not by prompting. The
model can *ask* for anything; only the executor decides what runs.

## Threats considered

| Threat | Mitigation |
|---|---|
| Prompt injection from web pages, documents, command output | All external content is wrapped in `<untrusted_content>` blocks, suspicious phrasing is flagged, and the system prompt forbids following embedded instructions. The hard guarantee: medium/high-risk actions always go through the permission broker, so injected text cannot delete, edit, run or send anything without you. |
| Destructive or unintended actions | Risk levels per call (`security/risk.py`). HIGH (delete, install) always asks and never offers *Always allow*; MEDIUM asks unless you created a scoped grant or turned confirmations off; background jobs and REST calls can't approve anything. Deletes move items to `data/trash`; edits keep backups in `data/backups`. |
| Command injection | No shell is ever used. Commands are tokenised with `shlex`, shell metacharacters are rejected, and only an allowlist of development commands matches (`security/commands.py`). Path-like arguments must stay inside authorised folders. Children run with secrets stripped from the environment, a timeout and an output cap. |
| Path traversal / credential theft | Every path is resolved (following symlinks) and must lie inside an authorised workspace folder. `.env`, SSH/GPG/cloud credential folders, key files and `.netrc`-style files are always blocked. Programs are never "opened" (that would execute them). |
| SSRF | Only http(s); no embedded credentials; hostnames must resolve exclusively to global addresses (blocks localhost, RFC1918, link-local/metadata, CGNAT, `.local`/`.internal`); redirects are followed manually and re-validated per hop; the connected peer address is re-checked when no proxy is used; the headless browser validates every sub-request; responses are size-capped. |
| Malicious uploads | Type detection by content (magic bytes), not extension; DOCX zip-bomb check; image decode + pixel cap; SVG and archives rejected; random storage names outside any web root; files are never executed; downloads of non-images are forced to `attachment` with a sandboxing CSP. |
| Unsafe URLs in answers | Markdown is rendered without raw HTML; only http(s)/mailto links are clickable and open with `noopener noreferrer`. |
| CSRF / DNS rebinding against the local server | `TrustedHostMiddleware` rejects unknown `Host` headers; state-changing requests and WebSocket upgrades from foreign `Origin`s are refused (same-origin and configured frontends only). `python -m app` refuses to listen on a network interface in local mode. |
| Secret leakage | API keys only live in the backend (`.env` or encrypted with Fernet in `app_secrets`, key from `NEXUS_SECRET_KEY` or a 0600 file in development). The API never returns a key — only configured/source/last-4 hint. Logs and audit records pass through a redaction filter (API keys, JWTs, bearer tokens, private keys, card numbers, passwords). |
| Memory privacy | Secrets, card and ID numbers are never stored; personal-sensitive and inferred facts require approval; everything is viewable, editable and deletable; full export and erase are available. |
| Abuse / cost blow-ups | Per-user sliding-window rate limits (chat, default, uploads, STT/TTS, run-now), minimum automation intervals, agent step limits and timeouts, max 3 concurrent requests per connection. |
| Remote control of a shared server | In Supabase (multi-user) mode computer control defaults to **off**, and host-level settings (workspace folders, custom apps) need an admin. |

## Authentication

- **Local mode:** one user, localhost only, protected by Host/Origin checks.
- **Supabase mode:** every REST call carries `Authorization: Bearer <access token>`; the WebSocket's first
  message carries the token. Tokens are verified with the project's JWT secret (HS256) or JWKS (RS256/ES256),
  audience `authenticated`, expiry required. All queries are scoped to the token's user id; Row Level
  Security on every table (see `supabase/migrations`) is defence in depth, and server-only tables (secrets,
  audit log) have no client policies.

## Audit trail

- `tool_calls` — every tool execution: redacted arguments, risk, approval (auto, policy, allow_once,
  always_allow, denied, expired, non_interactive), status, duration, error.
- `permission_requests` — every approval prompt and its decision.
- `agent_runs` — which agent handled what, and the outcome.
- `audit_logs` — settings changes, key updates/deletions, grant revocations, export and erase.

## Reporting

If you find a vulnerability, please open a private security advisory on the repository rather than a public
issue.
