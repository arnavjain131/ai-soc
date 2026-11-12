# First hosted development release

Checkpoint: 12 November 2026. The owner confirmed the local private workflow works. Next is a hosted version of that slice, while the remaining SOC features continue to be implemented. No migration rerun, duplicate workspace, or new database is needed.

## 1. GitHub source repository

Create an empty private repository named `ai-soc` if one does not already exist. Leave README, license, and .gitignore initialization unchecked because the local project already has its own files. Provide only the repository URL. No personal access token, password, database connection string, or source token should be posted in chat.

Selected repository: https://github.com/arnavjain131/ai-soc. Initial source branch: `codex/initial-soc`. Select this branch explicitly in Vercel/Render if it is not selected by default. The remote was empty when checked. Before pushing: check the source file list, verify ignored environment/database/dependency files stay excluded, then commit and push the reviewed source. Browser/CLI GitHub authentication uses the owner's normal authenticated session.

## 2. Deploy the frontend shell to Vercel

This obtains the exact frontend origin needed by backend production validation. The demo can load while backend deployment is pending.

| Setting | Value |
| --- | --- |
| Repository | The owner's ai-soc repository |
| Framework | Vite |
| Root directory | frontend |
| Build command | npm run build |
| Output directory | dist |

Record the generated HTTPS deployment URL. Until the hosted API URL is configured, private mode is not ready for remote visitors. Use the stable production URL, not a changing branch-preview origin, for the initial setup.

Vercel frontend environment variables for the completed connection:

- `VITE_SUPABASE_URL`: the existing project URL.
- `VITE_SUPABASE_PUBLISHABLE_KEY`: the existing publishable key, entered directly in the host settings.
- `VITE_API_BASE_URL`: the Render HTTPS URL obtained in step 3, not localhost.

The frontend environment is compiled into its build. Never put database credentials, source tokens, AI secrets, or Supabase secret/service-role keys here.

## 3. Deploy the backend to Render

Create a Python Web Service connected to the same repository. Select the compute plan deliberately; the repository includes a free-plan reference, not an instruction to buy anything. Free hosting availability limits remain relevant.

| Setting | Value |
| --- | --- |
| Root directory | backend |
| Build command | pip install -r requirements.txt |
| Start command | uvicorn app.main:app --host 0.0.0.0 --port $PORT |
| Health check | /health/ready |
| Python version | 3.11.9, as in infra/render.yaml |

Set these variables directly in Render's settings:

- `APP_ENV=production`
- `DATABASE_URL`: existing Supabase Session Pooler URL, using `postgresql+psycopg://` and `sslmode=require`. Enter privately; do not send it in chat.
- `SUPABASE_URL`: existing project URL.
- `SUPABASE_PUBLISHABLE_KEY`: existing publishable key.
- `ALLOWED_ORIGINS`: the exact Vercel HTTPS origin, without a trailing slash. Do not use `*`.

`infra/render.yaml` contains the equivalent reference configuration. Do not run `init-local` or grant-member during deploy/startup. The existing Supabase schema and memberships persist independently of the web service.

Record the backend HTTPS URL. Readiness must return 200. Anonymous `/api/incidents` must return 401.

## 4. Complete the hosted connection

Set Vercel's `VITE_API_BASE_URL` to the Render HTTPS URL and redeploy the frontend. Confirm Render's allowed origin exactly matches the final frontend origin. Configure Supabase Auth's Site URL to the frontend HTTPS URL and appropriate exact redirect allow-list entries for supported flows. Password login is the currently implemented flow; invite/recovery acceptance screens are not yet implemented merely because redirect URLs exist.

Local `.env` files can continue pointing to the local API for development. Do not replace the frontend production API URL with localhost; localhost on a visitor's device refers to their computer.

## 5. Verify and record the release

1. In a fresh signed-out browser session, open the frontend HTTPS URL. Confirm the public demo works and is labelled synthetic/read-only.
2. Sign in with the existing administrator account privately. Confirm existing incidents from Supabase load.
3. Confirm anonymous backend requests cannot read private incidents and invalid/expired sessions are rejected.
4. If a hosted ingestion smoke test is needed, set `SOC_API_URL` locally to the Render HTTPS URL and use the source token privately with the existing script. Each fresh run adds a labelled five-event test scenario; do not rerun without intending to create records.
5. Confirm a changed incident disposition persists after refresh and an API restart/redeploy. Terminal closed/false-positive states cannot be reopened in this version.
6. Record the frontend/backend URLs, deployed commit, plan, and verification results in CURRENT_STATUS.md. Do not record secrets or Auth/source tokens.

This release does not add live sensors, multistage correlation, AI/RAG, or ML. Those are subsequent implementation milestones. Use sanitized/lab telemetry while the documented production hardening remains incomplete.

## References

- https://vercel.com/docs/frameworks/frontend/vite
- https://render.com/docs/deploy-fastapi
- https://supabase.com/docs/guides/auth/redirect-urls
