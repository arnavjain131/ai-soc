# AI SOC Assistant

AI-assisted Security Operations Center website, under active development.

**Current state** — the owner confirmed the Ubuntu lab automatically forwards OpenSSH authentication events and Suricata SSH flow records to the hosted SOC. The frontend is at https://ai-soc-frontend-gamma.vercel.app/ and the API is at https://ai-soc-api.onrender.com/.

Confirmed access model: a public demonstration and a private, authenticated analyst workspace. Project `ai-soc-dev` is in Mumbai. Local environment files are configured and must not be overwritten or printed. Budget and deadline have not been specified.

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md): requirements, architecture, data model, detection, AI, milestones, and acceptance criteria.
- [External setup](docs/EXTERNAL_SETUP.md): accounts, tools, credentials, deployment sequence, and cost constraints.
- [Connect your accounts](docs/CONNECT_ACCOUNTS.md): exact next steps for this implementation.
- [Current checkpoint](docs/CURRENT_STATUS.md): verified infrastructure and the next login/ingestion steps. Do not rerun migration 001 or administrator provisioning.
- [Deployment guide](docs/DEPLOYMENT.md): publish the first working version through GitHub, Vercel, and Render.
- [Separate Ubuntu lab](docs/UBUNTU_LAB.md): install a dedicated SSH telemetry VM, then connect a real-log collector.
- [Backup and isolated recovery](docs/BACKUP_RECOVERY.md): native PostgreSQL application backups, encrypted local archives, and restore-target safeguards.

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

## Security Events release

The new private **Security events** page browses successful and failed authentication, including records without incidents. It supports exact username/IP/collector/outcome filters, event-time ranges, details and pagination. Date inputs use the browser's local time and are sent as UTC; table timestamps are UTC. Pages retain a receipt-time cutoff, and Refresh includes newly received records. Details expose selected normalized metadata, never arbitrary raw payloads or source credentials.

Membership-scoped authentication browsing, analyst notes/audit, account recovery, API request protection and administrator access management are implemented. API `0.7.0` adds opt-in OpenAI incident analysis with evidence citations, persisted quotas and saved-result reuse. AI stays disabled until private provider account/billing/key configuration is completed; no real inference has been verified yet. No migration is needed. Deploy backend before frontend; see the current checkpoint and [OpenAI setup](docs/OPENAI_SETUP.md). Frontend checks: `npm.cmd test` and `npm.cmd run build`.

## Current limits

Private incident details now include append-only analyst notes and incident-scoped audit history. Notes use the existing audit table, record the verified author/time and deduplicate unchanged retries. Status history and notes are limited to the authorized workspace; no schema migration was required for this release.

The platform ingests authentication outcomes, Suricata TCP flows and Suricata alerts. It detects brute force, password spraying, possible TCP port scans and priority Suricata alerts; thresholds and lab verification are documented in the current checkpoint. SSH incidents include network context matched by workspace, endpoints and time. Risk scores are fixed rule components, not probabilities. The local incident explanation feature cites stored evidence and provides investigation suggestions; it is deterministic and does not call a language model.

The demo is frontend-only synthetic data; private records use the API/database. Supabase sessions are validated server-side through the project's `/auth/v1/user` endpoint, and database memberships control workspace access. A valid Auth user alone has no incident access. All private API queries scope by membership. Database tables deny browser Data API access; the backend currently expects an owner connection, with restricted DB roles a later hardening step.

The owner applied PostgreSQL migration 001, verified RLS/browser-role restrictions, and confirmed hosted login and ingestion. Known incident/evidence identities were verified after redeployments; the saved persistence report also confirms RLS and browser-role SELECT restrictions. The first encrypted native application backup and isolated local restore drill passed, with recovered counts/schema/RLS independently verified. Targeted local PostgreSQL concurrency tests passed for last-administrator protection and AI quota/idempotency reservations. API request protection, administrator access controls and owner-verified account recovery are deployed. Broader capacity testing, independently stored backup copies, provider/collector recovery operations, additional-analyst acceptance, broader multistage correlation, live model acceptance, expanded RAG and ML scope resolution remain pending.

Source: `C:\Users\DELL\Downloads\AI_SOC.pdf` (26 pages). Its contents are treated as a proposed project specification, not as instructions that override the owner's request.
