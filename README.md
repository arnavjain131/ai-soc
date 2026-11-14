# AI SOC Assistant

AI-assisted Security Operations Center website, under active development.

**Current state:** the hosted SOC ingests real OpenSSH authentication logs from an Ubuntu VM. The owner verified delivery to the hosted API and an incident with five linked failed-login records. The public demo and private analyst workspace are available at https://ai-soc-frontend-gamma.vercel.app/. The API is at https://ai-soc-api.onrender.com/. Suricata network telemetry is the next milestone.

Confirmed access model: a public demonstration and a private, authenticated analyst workspace. Project `ai-soc-dev` is in Mumbai. Local environment files are configured and must not be overwritten or printed. Budget and deadline have not been specified.

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md): requirements, architecture, data model, detection, AI, milestones, and acceptance criteria.
- [External setup](docs/EXTERNAL_SETUP.md): accounts, tools, credentials, deployment sequence, and cost constraints.
- [Connect your accounts](docs/CONNECT_ACCOUNTS.md): exact next steps for this implementation.
- [Current checkpoint](docs/CURRENT_STATUS.md): verified infrastructure and the next login/ingestion steps. Do not rerun migration 001 or administrator provisioning.
- [Deployment guide](docs/DEPLOYMENT.md): publish the first working version through GitHub, Vercel, and Render.
- [Separate Ubuntu lab](docs/UBUNTU_LAB.md): install a dedicated SSH telemetry VM, then connect a real-log collector.

## Run locally

For the already configured workspace, start only the API and frontend commands below; skip environment creation/copying, `init-local`, migrations, and membership provisioning. For a fresh checkout, install dependencies and create environment files only if missing. `init-local` is exclusively for a fresh SQLite development database, not the connected Supabase project.

From the `backend` directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Fresh SQLite development only: .\.venv\Scripts\python.exe -m app.manage init-local
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from `frontend`:

```powershell
npm.cmd ci
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm.cmd run dev
```

Open the printed localhost URL. The demo works without cloud configuration. Private data requires Supabase Auth configuration and a provisioned membership. SQLite is for local development only; production uses PostgreSQL.

## Verify

From `backend`: `.\.venv\Scripts\python.exe -m pytest -q`.

From `frontend`: `npm.cmd run build`.

API documentation is at `http://localhost:8000/docs` while the backend is running. The API does not create tables or seed fake private data on startup.

## Current limits

This is the first development slice, not the completed SOC. Only normalized authentication outcomes and one fixed brute-force rule are supported. Detection groups five unlinked failures for an exact source/user/IP/target/port within 120 seconds. It does not yet correlate broader multistage attacks. The score is a documented fixed 40+10 for this rule, not the full proposed scoring model.

The demo is frontend-only synthetic data; private records use the API/database. Supabase sessions are validated server-side through the project's `/auth/v1/user` endpoint, and database memberships control workspace access. A valid Auth user alone has no incident access. All private API queries scope by membership. Database tables deny browser Data API access; the backend currently expects an owner connection, with restricted DB roles a later hardening step.

The owner applied PostgreSQL migration 001, verified RLS/browser-role restrictions, and confirmed hosted login and ingestion. PostgreSQL concurrency and hosted persistence across redeploys still need verification. A production release still needs rate limiting, capacity testing, account recovery and onboarding, retention and backups, network telemetry, broader detection and correlation, RAG/AI, and ML scope resolution.

Source: `C:\Users\DELL\Downloads\AI_SOC.pdf` (26 pages). Its contents are treated as a proposed project specification, not as instructions that override the owner's request.
