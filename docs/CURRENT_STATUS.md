# Current checkpoint

Updated 12 November 2026. This file supersedes older planning statements that Supabase is not connected. Credentials remain in ignored local environment files; do not print, request in chat, overwrite, or commit them.

## Infrastructure

- Supabase project: `ai-soc-dev`, Mumbai region.
- Project URL: `https://irunqxzbxqqcuclkhpcj.supabase.co`.
- PostgreSQL: Session Pooler, psycopg/SQLAlchemy, `sslmode=require`.
- Migration: `001_initial.sql` applied successfully by the owner; schema version 1. **Do not execute it again.**
- Nine tables exist: soc_workspaces, soc_memberships, soc_audit_logs, soc_incidents, soc_sources, soc_alerts, soc_events, soc_alert_events, soc_schema_migrations.
- Owner verified RLS enabled and no SELECT privileges for anon/authenticated on all nine tables.
- Private workspace: `Private SOC`, ID `bd0fc3bb-f387-4aac-9256-44a9bb4bbb7a`.
- Owner created the Auth user and provisioned admin membership. **Do not rerun grant-member for this user.**
- Backend `.env` and frontend `.env.local` already exist and are configured.

## Checks performed in the current session

No database writes or migrations were performed.

- Frontend/backend Supabase URLs match the expected project.
- Both publishable-key values are present and equal, without displaying either value.
- PostgreSQL/psycopg and TLS-required configuration pass.
- Frontend API URL and localhost CORS configuration agree.
- `GET http://localhost:8000/health/live`: 200.
- `GET http://localhost:8000/health/ready`: 200.
- Anonymous `GET http://localhost:8000/api/incidents`: 401, as required.
- Frontend `http://localhost:5173`: 200.
- Read-only database queries confirmed schema version 1, the expected workspace name/ID, and at least one administrator membership in that workspace.

The owner has now confirmed that interactive login and the private five-event ingestion-to-incident workflow work, including the expected linked evidence. This is user-confirmed functional verification against Supabase. Concurrent PostgreSQL ingestion has not been independently tested. The 12 automated tests exercise isolated SQLite databases; all passed again on 12 November during deployment preparation.

## Completed: interactive login and the first private incident

The owner confirmed the workflow below works. It is retained for reference; do not repeat setup or insert more test records merely to re-establish this checkpoint. Individual disposition persistence remains a separate check if it was not included in the owner's test.

1. While both services are running, open `http://localhost:5173`.
2. Choose **Analyst sign in** and enter the existing Supabase Auth email/password yourself. Do not share them in chat. Confirm the header changes to **Private analyst workspace**.
3. Initially an empty private dashboard is expected if you have not ingested events. A valid Auth account without a membership would return 403; your membership is already provisioned.
4. Open **Telemetry sources** and create a source named `Authentication test` as the administrator. Save its one-time token privately. This creates a source and audit record in your private workspace.
5. Follow section 5 of CONNECT_ACCOUNTS.md to run `scripts/replay_auth.py` from the repository root, providing the source token locally via secure prompt. Expected response on one fresh run: `{"accepted":5,"duplicates":0}`.
6. Refresh the private dashboard. Expect five additional events, one additional alert, and one additional incident. Open the incident and check all five evidence events and rule rationale. This is a labelled synthetic pipeline test, not real sensor telemetry.
7. Set the incident to **investigating**, refresh, and confirm the status persists. Closing is terminal in this version, so use investigating for the first workflow check.

If services need restarting, use two PowerShell terminals with the repository as the initial directory:

Backend:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
Set-Location frontend
npm.cmd run dev -- --port 5173 --strictPort
```

Do not start duplicates if the ports are already serving the application. Start at `http://localhost:5173`, matching the configured CORS origin; `http://127.0.0.1:5173` is a different browser origin.

## Following milestones

The owner supplied the repository https://github.com/arnavjain131/ai-soc. It was checked and is empty. Source credential/exclusion checks passed before initial publication. The initial source branch is `codex/initial-soc`; select this branch in hosting integrations. Next: publish the reviewed source, deploy the first hosted version, configure production URLs/secrets in the hosting dashboards, and verify deployed private access. See DEPLOYMENT.md for the concrete sequence. Public demo plus private analyst access remains the agreed model. This hosted version will still be an early development release. Real telemetry adapters, broader rules/correlation, RAG/AI, and ML scope are later implementation work. Budget and deadline remain unspecified.
