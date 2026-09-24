# Deploying NEXUS

## Personal machine (recommended)

The default configuration is designed for one person on their own computer:

```bash
cd frontend && npm ci && npm run build          # the backend serves frontend/dist
cd ../backend && pip install -e ".[desktop]"    # screenshots + headless browser (optional)
python -m app                                   # http://127.0.0.1:8000
```

- Keep `AUTH_MODE=local` and the default `NEXUS_HOST=127.0.0.1`.
- Set `NEXUS_SECRET_KEY` so stored API keys survive moving the data folder.
- Back up `backend/data/` (database, uploads, backups, trash, `.secret_key`).
- Start it at login with your OS's service manager (systemd user unit, launchd agent, Task Scheduler).

## Multi-user (Supabase)

1. **Database & auth.** Create a Supabase project and apply `supabase/migrations/*.sql`. Enable the email
   provider under Authentication. Use a *direct* or *session pooler* connection string for `DATABASE_URL`
   (the backend uses asyncpg with its own pool).
2. **Environment.**

   ```dotenv
   NEXUS_ENV=production
   NEXUS_SECRET_KEY=<48+ random bytes>
   AUTH_MODE=supabase
   SUPABASE_URL=https://<ref>.supabase.co
   SUPABASE_ANON_KEY=<anon key>
   # SUPABASE_JWT_SECRET only for legacy HS256 projects; otherwise JWKS is used
   NEXUS_ADMIN_EMAILS=admin@example.com
   DATABASE_URL=postgresql://...
   CORS_ORIGINS=https://nexus.example.com
   ALLOWED_HOSTS=nexus.example.com
   SCHEDULER_MODE=external
   ```

3. **Processes.** Run the API (`python -m app`, or `uvicorn app.main:app --workers 1`) and the scheduler
   (`python -m app.worker`) as separate services. Keep **one API worker process**: approvals are resolved
   through in-process futures and rate limits are in-memory (swap `security/rate_limit.py` for a Redis
   implementation before scaling out).
4. **TLS.** Put the API behind a reverse proxy that terminates HTTPS and forwards WebSocket upgrades
   (`/ws`). Microphone access in browsers requires HTTPS (or localhost).
5. **Computer control** stays disabled in this mode unless you explicitly set
   `COMPUTER_CONTROL_ENABLED=true` for a single-tenant server you own.

## Checks after deploying

- `GET /api/health` → `{"status": "ok"}`
- `GET /api/system/status` → every component you configured reports `ready: true`
- Sign in, send "remember that my favourite colour is teal", reload, ask "what is my favourite colour?"
- Create a reminder 2 minutes out and confirm the notification arrives (tests the worker + relay path)
