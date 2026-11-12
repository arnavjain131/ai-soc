# Connect the first implementation slice

**Resume at section 5 after starting both local services and signing in.** Supabase project creation, migration 001, local environment configuration, database connectivity, and administrator provisioning are complete. Do not repeat sections 1-4, rerun the initial migration, overwrite environment files, or provision a duplicate administrator/workspace. See CURRENT_STATUS.md for the current checkpoint. Earlier setup instructions below remain as reference for fresh environments only. No public deployment has happened yet; never post passwords, tokens, or keys in chat.

## 1. Create the Supabase project

In Supabase, create a project if you have only created an account. Use a name such as `ai-soc-dev`, select a nearby region, and save the database password in a password manager. Wait for project provisioning.

Find the Project URL and publishable API key in the project's connection/API settings. These two values are intended for browser configuration and can be shared to configure the application. Do not copy a secret key or service-role key instead.

The backend currently validates login tokens by asking this project's Auth server for the current user. It does not accept a browser's claimed user ID or role.

## 2. Apply the initial database schema once

Open `supabase/migrations/001_initial.sql` from this repository. In your new development project's SQL editor, review the script, paste it, and run it once. It creates only the `soc_*` tables used by this slice, enables RLS, and revokes browser-role access. It does not modify Supabase Auth tables. It records schema version 1.

This initial migration expects a new project without these tables. Do not rerun it or apply it to an unrelated existing database. It runs in a transaction; an error should leave the migration unapplied. Do not remove error checks merely to make an unsuccessful migration appear complete.

For the current project, the owner reports successful execution and verification that browser roles cannot SELECT from all nine tables. Read-only application checks confirm schema version 1. PostgreSQL ingestion is the next functional verification.

## 3. Configure local secrets yourself

Copy `backend/.env.example` to `backend/.env`. Copy `frontend/.env.example` to `frontend/.env.local`. Both destination files are ignored by Git.

Frontend values:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
```

Backend values for the cloud development database:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://USER:URL_ENCODED_PASSWORD@HOST:PORT/postgres?sslmode=require
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
ALLOWED_ORIGINS=http://localhost:5173
```

Use the host, username, and port from Supabase's Connect dialog. A session-pooler connection can avoid direct-connection IPv6 compatibility issues. Do not assume all pooler modes have the same driver behavior. URL-encode special characters in your password; do not remove TLS. If you keep SQLite locally, use the template's SQLite URL and run `python -m app.manage init-local` instead of applying PostgreSQL SQL locally.

Do not run `init-local` against Supabase. Run backend commands from the `backend` directory so the intended `.env` is loaded. Restart the backend/frontend after changing their environment files.

## 4. Provision your analyst account

For this first development slice, use the Supabase Authentication user-management screen to add your own email/password user and complete any required confirmation. Enter the password yourself and keep it private. Disable public sign-up for the invite-only deployment. This slice does not yet implement invite acceptance or password recovery in its UI.

Copy the new Auth user's UUID. From the `backend` directory, with the intended `DATABASE_URL` configured, run:

```powershell
.\.venv\Scripts\python.exe -m app.manage grant-member --user-id YOUR_AUTH_USER_UUID --role admin --workspace-name "Private SOC"
```

This explicit owner operation creates a workspace and grants that user membership. It prints a workspace UUID, not a password. Additional analysts use `--role analyst --workspace-id EXISTING_WORKSPACE_UUID` so they join the same workspace. The first version supports one workspace membership per user.

After starting both services as described in the README, sign in through the website. An empty private dashboard is the correct initial result. It must not display demo metrics as private telemetry.

## 5. Test the first private pipeline

After signing in as your administrator account, open Telemetry sources in the website. Enter `Authentication test` and choose Create source. Save the source token shown once, then hide it. The token only authorizes ingestion; it cannot read incidents. The server stores its hash and never returns the original token again.

From the repository root, in a local PowerShell session, set `SOC_SOURCE_TOKEN` without putting its value in shell history:

```powershell
$sourceSecret = Read-Host 'Source token' -AsSecureString
$sourceCredential = [System.Net.NetworkCredential]::new('', $sourceSecret)
$env:SOC_SOURCE_TOKEN = $sourceCredential.Password
python scripts/replay_auth.py
Remove-Item Env:SOC_SOURCE_TOKEN
Remove-Variable sourceCredential,sourceSecret
```

This sends five synthetic authentication failures and should create one private incident. It proves the pipeline, not real monitoring. Each script run creates fresh external event IDs; API tests separately verify retry deduplication. Refresh the dashboard, open the incident, inspect its five linked events, and change its disposition.

Real telemetry adapters and the reliable sensor collector are later milestones. Do not describe this smoke test as live Suricata ingestion.

## 6. Prepare GitHub and hosting

Create an empty private GitHub repository, for example `ai-soc`. Do not initialize an unrelated remote history if you want a straightforward first push. Share its repository URL, not a personal access token. The implementation must be reviewed/committed before pushing; no remote has been set by the agent.

The first frontend can be deployed to Vercel with root `frontend`, build `npm run build`, output `dist`. The public demo can run without Supabase/API configuration. Private mode additionally needs its three frontend variables.

For Render use the prepared `infra/render.yaml` as a reference, or configure a Python web service manually with root `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and health check `/health/ready`. Set `APP_ENV=production`, a TLS PostgreSQL `DATABASE_URL`, Supabase URL/publishable key, and exact HTTPS `ALLOWED_ORIGINS`. Apply the schema before expecting readiness to pass.

Use the frontend's deployed URL in backend CORS and Supabase Auth URL settings. Set the deployed backend URL as `VITE_API_BASE_URL`; rebuild the frontend after that value changes. Test deployed login, fresh anonymous access, private isolation, ingestion, and database persistence. Free hosting has availability limits described in EXTERNAL_SETUP.md.

## Information needed after the local test

- Whether website login succeeds and the private dashboard opens.
- Whether the synthetic ingestion test creates an incident with five linked events. Share only redacted error text if a step fails.
- Your GitHub repository URL, if created, when moving to deployment. Local passwords and keys are already configured; do not send them in chat.

Budget/deadline, ML requirements, and AI provider choice remain open, but do not block this initial connection work.
