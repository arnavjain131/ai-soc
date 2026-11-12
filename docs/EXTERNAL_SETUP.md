# External setup and deployment checklist

Status updated 11 November 2026: accounts, Supabase project, migration 001, TLS Session Pooler configuration, and first admin/workspace provisioning are complete. The first local application slice is implemented; read-only API/database checks pass. Access model confirmed: public demo plus private analyst workspace. Resume from [Current checkpoint](CURRENT_STATUS.md); do not redo the historical setup checklist below. Public deployment is pending.

## 1. First actions for the owner

1. Create a GitHub account at https://github.com and enable MFA. We can build locally before a remote repository exists. A private source repository can still deploy a public website.
2. Create a Supabase account at https://supabase.com. Create a development project, choose a region near the eventual API, and store the database password securely. Do not paste credentials into chat.
3. Create a Render account at https://render.com for the Python API. Repository integration comes after the initial code is ready.
4. Create a Vercel account at https://vercel.com for the React frontend. We will configure build settings and the API URL when the frontend exists.
5. Later choose an LLM/embedding provider, create an API account if needed, configure usage controls/alerts, and add its key only to the backend host's secret settings. Provider/account and pricing remain undecided.

No domain purchase is necessary at the start. Do not upgrade plans before there is a concrete runtime or availability need. Budget and deadline remain unanswered; no paid plan is authorized by this document.

## 2. Local tools

Environment inspection found Python 3.11.9, Node.js 24.15.0, npm, and Git. Docker was not found on PATH; this does not prove it is absent. Check installed applications before installing it.

- Use a project Python virtual environment and a declared supported Node version.
- Docker Desktop/WSL2 is useful for reproducible local services; a cloud development database is an alternative while Docker is unavailable.
- For real telemetry, prepare a Linux lab in a hypervisor or compatible VM setup. Inspect host RAM, disk, and virtualization support before choosing VM allocations.
- Install a stable Suricata version inside the lab and enable EVE JSON. Add target application/authentication logging. Zeek is a later addition.

Account ownership, email verification, MFA, billing choices, and granting repository permissions need owner interaction. Implementation, migrations, testing, and deployment configuration can be prepared without sharing passwords.

## 3. Supabase configuration when code is ready

1. Apply versioned migrations; do not maintain the schema solely with manual dashboard edits.
2. Enable pgvector for knowledge retrieval, using the chosen embedding dimension.
3. Configure Auth URL settings for local development and the exact production frontend URL.
4. Keep private access invite-only; bootstrap the first administrator through a controlled operation. Users must not grant themselves admin roles through editable profile metadata.
5. Configure appropriate RLS policies and database grants. Service-role/database-owner access can bypass RLS, so test backend query authorization too.
6. Choose a direct or pooled database connection supported by the host/network and driver; require TLS and use bounded connection pools.
7. Separate development and production data; separate demo/private data and credentials. Plan a backup/export and restore procedure.

## 4. Configuration ownership

The exact variable names will be finalized with implementation. These are planned names, not currently working configuration.

| Setting | Location | Public? |
| --- | --- | --- |
| VITE_API_BASE_URL | Frontend build settings | Yes |
| VITE_SUPABASE_URL | Frontend build settings | Yes |
| VITE_SUPABASE_PUBLISHABLE_KEY | Frontend build settings | Yes; access still depends on RLS/policies |
| DATABASE_URL | Backend/worker secret settings | No |
| SUPABASE_URL, expected JWT issuer/audience | Backend settings | Non-secret configuration |
| LLM_API_KEY / EMBEDDING_API_KEY | Backend secret settings | No |
| ALLOWED_ORIGINS | Backend settings | Exact approved frontend origins |
| Source ingestion token | Collector secret store/environment | No; source-scoped, revocable |

Never place database passwords, Supabase secret/service-role keys, or AI keys in `VITE_` variables. Vite exposes prefixed variables in the browser bundle. Do not commit `.env` files with real values. Commit a placeholder-only `.env.example` once the application contract is defined.

## 5. Deployment sequence

1. Finish the foundation locally: migrations, token verification, permissions, minimal UI, tests, and environment contract.
2. Push source to the owner's repository; connect only the intended repository to the hosts.
3. Provision production database/auth and run reviewed migrations once, separately from every web worker startup.
4. Deploy FastAPI to Render. Planned backend root: `backend`; planned start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. This is for the Linux host, and depends on the future source layout. Configure readiness checks and secrets.
5. Deploy the React/Vite app to Vercel. Planned frontend root: `frontend`; build: `npm run build`; output: `dist`. Configure SPA deep-link rewrites and the public configuration variables.
6. Update backend CORS and Supabase redirect URLs to the deployed frontend. Redeploy if build-time frontend variables change.
7. Provision the processing worker if the chosen architecture uses one. Set durable retries, health monitoring, and failure visibility. Free web hosting alone is not a durable always-running worker.
8. Load sanitized demo data separately, register the private lab source, and configure collector HTTPS delivery.
9. Run the implementation plan's release gates against deployed services, including a fresh unauthenticated browser and a restart/redeploy.
10. Publish the verified URL and operational instructions. Configure an optional custom domain only after the provider URL works.

## 6. Costs and availability

Verified provider documentation on 11 November 2026; recheck before buying:

- Supabase Free lists a 500 MB database and pauses inactive free projects after one week. That capacity is suitable for limited development data, not unlimited network telemetry. Pro starts at USD 25/month; limits/usage charges and taxes can change. https://supabase.com/pricing
- Render Free web services spin down after 15 minutes without inbound traffic and use ephemeral local files. Free compute is for testing/demos, not continuous SOC availability. Worker and always-on runtime costs must be checked against the selected plan. https://render.com/docs/free and https://render.com/pricing
- Vercel offers a Hobby tier; check current eligibility, limits, and usage terms before using it beyond a personal/academic project. https://vercel.com/pricing
- Hosted LLM/embedding usage is separate from hosting; set per-user/server quotas, context limits, timeouts, and usage alerts. Public demo answers can be precomputed to keep anonymous traffic from generating unbounded API costs.
- Domains and reliable production email are optional additional purchases depending on requirements. Invite/recovery emails need deliverability testing before release.

A largely free development setup is feasible. A reliably available service with ongoing ingestion may require paid compute and database capacity. There is no agreed monthly budget or guaranteed zero-cost production deployment.

## 7. Immediate next implementation slice

Build the repository foundation and one real backend-to-frontend path: authenticated event ingestion -> persisted records -> brute-force rule -> incident -> dashboard timeline. Establish meaningful tests and deploy that slice before expanding to all rules and AI. Local work can begin while the owner creates accounts.
