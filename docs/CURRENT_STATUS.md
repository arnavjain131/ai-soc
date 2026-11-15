# Current checkpoint

Updated 16 November 2026 after the owner confirmed live Suricata alert display. Keep credentials in ignored local configuration.

## Infrastructure

- Frontend deployed: https://ai-soc-frontend-gamma.vercel.app/.
- API deployed: https://ai-soc-api.onrender.com/.
- Owner confirmed hosted sign-in and access to the existing private incident work.
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

The source was pushed successfully to https://github.com/arnavjain131/ai-soc on branch `codex/initial-soc`. The initial implementation commit is `b1bee68`; publication checkpoint commit is `bb3b9df`. Source credential/exclusion checks passed before publication; local environment files and databases were excluded. Both frontend and API are deployed. Public demo plus private analyst access remains the agreed model. This is an early development release; budget and deadline remain unspecified.

API `/health/live` and `/health/ready` returned 200, anonymous `/api/incidents` returned 401, and CORS and the authenticated-request preflight allowed the Vercel origin. The owner confirmed hosted login and subsequently verified live ingestion. Persistence across a hosted redeploy still needs verification.

Automatic Suricata forwarding and hosted alert display are verified. The isolated forwarder-to-API test verified that matching flows and alerts appear on an SSH incident when they fall within its correlation window. Live incident correlation remains open. The next development milestone is an incident explanation that cites the linked evidence and shows relevant network context.

## Completed: hosted SSH telemetry

The owner confirmed that `AI-SOC-Ubuntu` runs Ubuntu Server 24.04.5 LTS with 3 GB RAM, 2 CPUs, and a 25 GB dynamic disk. VirtualBox NAT forwards `127.0.0.1:2222` to guest SSH port 22. The guest clock is synchronized in Asia/Kolkata.

The owner installed `ai-soc-ssh.service`, transferred the journal cursor fix to Ubuntu, and verified API acknowledgements from Render. The deployed SOC opened **Possible brute force against soc-lab-test** with five linked `LOGIN_FAILED` records from `10.0.2.2` to `10.0.2.15:22`. The earlier synthetic `demo-admin` incident stayed separate. At verification the dashboard showed 18 events, 2 alerts, and 2 open incidents.

## Completed: Suricata flow import

The owner validated and enabled Suricata 7.0.3 on `AI-SOC-Ubuntu`, with AF-PACKET on `enp0s3` and Emerging Threats rules installed. The owner manually imported a captured SSH flow into the Render API at commit `b8504af`, which returned `{"accepted": 1, "duplicates": 0}`. The private Network events view on Vercel displayed `2026-11-14 21:34:43.547Z`, TCP, `10.0.2.2:64620` to `10.0.2.15:22`, collector `Ubuntu Suricata`. The SSH journal service continues to deliver authentication events independently.

## Completed live Suricata alert display

The owner made a normal SSH connection after the temporary lab signature was verified in the running Suricata ruleset. The sensor wrote one EVE alert for signature `1000491` and the runner restored the original rules. Supabase persisted the alert at `2026-11-15 21:35:28.947Z` from `10.0.2.2:64491` to `10.0.2.15:22` over TCP. The owner confirmed the private Network events view showed the alert, its severity, and the flow for the same TCP endpoints and ports. The alert falls outside all existing incident windows.

## Expanded detection

The release adds three rules evaluated on new ingestion. See the [lab guide](UBUNTU_LAB.md#phase-9-enable-network-detection) for collector configuration.

| Rule | Trigger | Priority |
| --- | --- | --- |
| Password spraying | Five distinct accounts with failed logins within 120 seconds from one peer to one target and service port | High |
| Possible TCP port scan | Flow records for eight distinct destination ports within 60 seconds from one peer to one target | Medium |
| Priority Suricata alert | Sensor severity 1 or 2. Repeats of the same signature, protocol and endpoints within five minutes are suppressed | Critical or high |

Pattern detection is scoped by workspace and collector. The TCP rule uses flow event timestamps, which may differ from connection start times. Suricata severity 3 records, including the lab verification signature, remain visible as telemetry. Network incident evidence shows the collector, protocol, addresses, ports and signature when present.
