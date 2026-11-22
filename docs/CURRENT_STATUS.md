# Current checkpoint

Updated 23 November 2026. Keep credentials in ignored local configuration.

## Reliability work: encrypted backup and isolated restore verified

The owner completed the native restore check and shared its success output. An independent read-only inspection of the restored local database confirmed all nine table counts, schema version 1, RLS enabled, and the latest real-lab incident present. The recovered data includes 157 events, 5 incidents, 5 alerts, 28 evidence links and 4 audit entries. Metadata is saved in `docs/verification/restore-2026-11-23.json`. The local lab server was then cleanly stopped; recovered files and the encrypted archive remain preserved. The nine-table application recovery drill is complete; full Supabase/provider/collector recovery and an independently stored archive copy remain separate work. API limits are the next fundamental milestone.

Preparation history (superseded by the successful restore above):

The owner installed PostgreSQL 17.12 client tools. The agent verified both client versions and the live read-only preflight. The owner then created the first encrypted archive and shared terminal output confirming successful decryption/authentication, SHA-256 checksum and native table-of-contents verification. Archive creation time was 2026-11-22T23:30:27.378936Z (23 November 05:00:27 IST); its manifest includes the same nine-table counts listed below. No passphrase was disclosed. This completes archive creation/verification, not recovery testing. Keep an independently protected encrypted copy and the passphrase separately.

Restore-lab preparation found that the Command Line Tools installation includes server executables but omits `share/postgres.bki`, so those executables alone cannot initialize a cluster. The local setup attempt stopped before creating a database or starting a server; the private restore configuration was not created. The signed, already-downloaded EDB installer supports extraction-only mode for a separate local server distribution without registering a service. The isolated restore drill remains pending, and must use a hidden local backup-passphrase prompt.

Local restore target is now prepared: the signed EDB 17.12 installer was extracted without installation under `%LOCALAPPDATA%/AI-SOC/postgresql-17-lab`. The active cluster is `%LOCALAPPDATA%/AI-SOC/restore-lab-17-verified/data`, bound exclusively to `127.0.0.1:55432` with SCRAM authentication. Empty database `ai_soc_restore_test` exists; generated local-only credentials are saved in ignored, owner/SYSTEM-restricted `backend/.env.restore`. A first initialization attempt hit a Windows inherited-pipe timeout and was stopped; its unused cluster remains preserved at `restore-lab-17/data`. The active cluster was subsequently prepared successfully after correcting the address-check formatting. No archive has been decrypted/restored during preparation. Stop the active cluster with `pg_ctl -D <active-data-directory> -m fast -w stop` after the user completes the hidden-prompt restore check. This server is not registered as a Windows service.

Read-only post-deployment checks confirmed all five known incident IDs and the latest lab incident's exact five evidence IDs remain present. The evidence still spans 19.416 seconds. Table counts were 1 workspace, 1 membership, 4 sources, 157 events, 5 incidents, 5 alerts, 28 alert/evidence links, 4 audit entries and 1 schema-migration row. Schema version remains 1, all nine tables have RLS, and anon/authenticated roles remain unable to SELECT them. A metadata-only report is saved in `docs/verification/persistence-2026-11-23.json`. This verifies retained app data through the recent deployments; it is not a substitute for a restore drill or a claim that an uncreated analyst note was persisted.

The verified collector rotation fix, upgrade script and controlled lab utilities were committed as `3ecd955`. They were already applied/tested earlier; this source-control step did not touch Ubuntu, credentials, queues or checkpoints.

Prepared local maintenance commands in `app.backup`: `check`, `create`, `verify` and guarded `restore-check`. The source is the existing private backend configuration. Native pg_dump uses an exported read-only consistent snapshot for the nine application tables. The custom dump/manifest are encrypted in memory with AES-GCM and an Argon2id-derived key; no plaintext dump is saved by the tool. The hidden local passphrase is neither accepted as an argument nor stored. Encrypted files default outside OneDrive under the Windows user's Local AppData, with restricted directory permissions and Git exclusions. Optional cryptography dependency is local-maintenance/dev only; the hosted API does not import it and no web deployment or new service is needed for these commands.

Restore checks require an explicitly confirmed empty `ai_soc_restore_*` database on a literal loopback address, with a server at least as new as the source. They never use `--clean`, `--create` or a hosted target, and run in one transaction. Counts/schema version/RLS are checked afterward; no target cleanup or promotion runs automatically. This is an application-table backup only: Supabase Auth, Storage, roles/ACL ownership/provider settings and collector credentials/state require separate recovery planning. See `docs/BACKUP_RECOVERY.md` for precise scope and commands.

Validation: all 64 backend tests passed (including 21 encryption/backup/restore-guard tests), plus 21 collector tests. The corrected relation-size query and read-only snapshot export also passed against the live database (622,592 application relation bytes). PowerShell lab utilities and the collector upgrade Bash syntax passed checks. Encryption round trips, tamper/wrong-passphrase rejection, native-output secrecy, no-overwrite writes and local-only/empty-target guards use synthetic test fixtures; native restore behavior is mocked, not a completed restore drill.

The earlier missing-client prerequisite is resolved by PostgreSQL 17.12. Native archive creation and verification are complete as recorded above; an actual restore has not yet been attempted. Do not request database passwords, tokens or backup passphrases in chat. Prepare a separate local restore-test server/database; API limits remain a following milestone. AI stays deferred.

## Deployed: analyst notes and audit history

The owner authorized proceeding with analyst notes and incident audit visibility. Backend commit `ab93b2a` is pushed and introduces API `0.4.0`: incident-scoped GET/POST `/api/incidents/{incident_id}/notes` and GET `/api/incidents/{incident_id}/audit`. It reuses `soc_audit_logs` with action `incident.note_added`; no database migration is required. Notes are append-only through the API, 1–2,000 characters after trimming, authored by the verified member. Admins and analysts can read/write only within their incident's workspace. A PostgreSQL incident-row lock and actor/incident/request UUID check deduplicate identical retries; changed text with a reused UUID returns 409. Notes do not alter incident status, score, timestamps or linked evidence. Audit history returns only allowed note/status-change actions for that incident, with selected safe status metadata.

Frontend commit `f2aa507` was pushed after backend readiness was verified. Private incident details add **Analyst notes** and **Incident audit history** panels, local timestamps with exact UTC tooltips, actor identifiers (You/Member UUID prefix), empty/loading/error states and ten-entry pagination. Notes render as text. Unchanged text retries reuse their UUID, duplicate submit is blocked, and edits allocate a fresh request ID. Saving, incident Refresh and disposition changes refresh the displayed notes/history. The public demo and deferred AI draft do not invoke these endpoints.

Validation: all 43 backend tests and 12 frontend tests passed; the final frontend build passed. Tests cover membership/incident workspace boundaries, analyst authorship, append-only behavior, closed-incident follow-up, note retry/conflict behavior, source/other-workspace audit exclusion, safe metadata, pagination and invalid/spoofed/oversized bodies. No production notes, audit records or dispositions were created for testing. Existing collectors, credentials, queues and detection thresholds are untouched.

The owner manually deployed `ab93b2a`; Render auto-deploy remains disabled and that setting was not changed. External checks confirmed API `0.4.0` and database readiness both HTTP 200, with HTTP 401 for anonymous notes and audit GETs on the existing lab incident. The agent then pushed `f2aa507`. Vercel returned HTTP 200 and its production JavaScript was verified to contain Analyst notes, Incident audit history, Save note and Refresh history. Both deployments are complete. No migrations or production note/status writes were made for verification. The agent attempted an authenticated visual check through the existing SOC tab, but Windows Computer Use stopped because it could not verify the current URL confidently; no more UI input was sent after that stop. Authenticated panel display and a genuine user-written note persisting after refresh remain acceptance checks, not claimed verified results. The owner can open an existing incident to use the new panels. Do not blindly publish the deferred explanation files or modify collector state.

## Deployed: Security Events release

Implemented read-only authentication browsing at `GET /api/events/security` and `GET /api/events/security/{event_id}` using the existing membership/workspace authorization. The list supports exact username, source/destination IP, collector, outcome and inclusive timezone-aware event-time filters; paginated results include a receipt-time cutoff carried between pages. Details preserve timestamp precision and expose only allowlisted authentication method/provenance, not arbitrary raw payloads or source credentials. Real journal records and synthetic replay provenance remain distinguishable. Network endpoints and the database schema are unchanged.

The private frontend adds **Security events**, an authentication table, local-time date inputs converted to UTC, outcome/source/user/IP filters, event details with event/receipt timestamps, and 25/50/100-row pagination. Refresh requests a fresh cutoff while preserving applied filters. Requests from obsolete session/filter boundaries are ignored. No traffic generation, migrations, source changes or collector changes are needed.

Validation: 32 backend tests passed, 9 frontend tests passed, and the final frontend production build succeeded. Backend checks cover analyst access, anonymous/non-member rejection, cross-workspace list/detail/source-filter isolation, literal matching, UTC/IST date equivalence, snapshot pagination, input validation and safe metadata. Backend commit `e27dccb` was pushed and deployed manually by the owner. External checks then confirmed `/health/live` HTTP 200 with API `0.3.0`, `/health/ready` HTTP 200 and anonymous `/api/events/security` HTTP 401. Render auto-deploy remains disabled because of its existing commit-pinning configuration; that setting was not changed.

Frontend commit `47fcd32` was then pushed to the existing branch. The production Vercel site returned HTTP 200 and its JavaScript was verified to include the new Authentication activity, username filter and receipt-time detail labels. A separate read-only check ran the new scoped browsing query against Supabase PostgreSQL successfully: 82 persisted authentication records were present, with the latest records being genuine soc-lab-test failures from Ubuntu SSH journal v2. This database check is not an authenticated hosted HTTP response.

The agent's authenticated visual check was blocked by browser URL detection. The owner subsequently supplied a screenshot confirming the hosted Security events table, all filter controls, real failed-login rows and pagination count **1–25 of 82**. Individual filter/detail/page interactions were covered by automated checks but not independently observed in that screenshot. No migrations, data writes, synthetic replays or new lab traffic were used for release verification. Both deployments are complete; no Ubuntu changes are required.

The deferred explanation route/import and its three tests were removed from active integration and preserved in ignored `tmp/deferred-explanation-integration.txt` and `tmp/deferred-explanation-tests.py.txt`; their implementation files remain local. API `0.3.0` now identifies this Security Events release, not the explanation draft. Do not include the AI draft or unrelated collector repairs in this release accidentally. After Render readiness, publish the frontend and verify the hosted authentication table, filters, event detail and pagination using existing records only.

## Authoritative handoff: completed foundation and next work

The owner requested a durable recap before further development. The deployed platform uses React/TypeScript on Vercel, FastAPI on Render and Supabase PostgreSQL/Auth, with a public read-only synthetic demo and authenticated private analyst workspace. Schema 001, RLS verification, PostgreSQL TLS connectivity and administrator provisioning are completed; do not repeat setup.

Verified lab: separate Ubuntu Server 24.04.5 LTS VM **AI-SOC-Ubuntu**, 3 GB RAM, 2 CPUs, 25 GB dynamic disk, NAT, `enp0s3` / `10.0.2.15`, localhost-only SSH `127.0.0.1:2222` to guest 22, synchronized clock. Existing Wazuh/Windows VMs remain untouched. Suricata 7.0.3 and the SSH/Suricata systemd collectors are installed and running as last verified. Collectors use source-scoped authentication, persistent SQLite queues/checkpoints and retry delivery. Preserve those credentials and state.

Completed proofs: real SSH success/failure ingestion and brute-force incidents; real Suricata TCP-flow and alert delivery/display (including lab signature 1000491); synthetic authentication replay; an approved eight-flow import producing a medium-risk port-scan incident; later independent automatic delivery of a fresh non-SSH port-18080 flow; copytruncate/gzip recovery with state/code/archive backups; deployed source-freshness indicators; and a fresh live SSH incident whose authentication and related network records were opened and verified on the hosted website. The temporary TCP listener was stopped and the owner reported running NAT removal; retain the original SSH forwarding rule.

Implemented rules: brute force (5 matching failed logins / 120 seconds), password spraying (5 distinct accounts / 120 seconds), TCP port scan (8 distinct destination ports / 60 seconds), priority Suricata alerts (sensor severity 1/2, with repeat suppression). Password-spray and priority-alert incident logic have automated coverage; do not claim their genuine live attack tests are complete. Severity-3 lab alerts are telemetry/context and do not independently trigger the priority-alert rule.

Latest confirmed live incident: **Possible brute force against soc-lab-test**, `0501d95b-b053-41d0-995d-1d53fa1f6ca9`, 22 November 05:14 IST, Open / High / 50 out of 100, 5 linked genuine failed logins and 7 related Suricata flows in the hosted Evidence timeline. The five failures span 19.416 seconds. Correlation is workspace/endpoints/protocol/time based; it does not establish one-to-one session attribution behind NAT. Last observed dashboard snapshot: 5 incidents, 5 alerts, 157 security records and 4 sources; these are a checkpoint, not permanently current counts.

The agreed **Security Events** page and incident notes/audit panels are implemented and deployed as recorded above. The owner supplied a screenshot of the Security Events table. Next work is backup/recovery and API limits; the known-record deployment-persistence check is now complete, and the isolated native application-table restore drill is now complete. Queue depth and guest service status are not yet reported to the dashboard. No more failed-login or port-scan tests are needed merely to re-establish completed milestones.

AI/explanations remain explicitly deferred. A deterministic explanation draft exists locally; it is disconnected from the frontend and its backend changes are unpublished. No LLM/RAG/ML integration is complete and no AI key is needed for the next milestone.

Source-control checkpoint: backend `ab93b2a` and frontend `f2aa507` published analyst notes and audit history after the source-freshness UI. The verified collector rotation fix, upgrade script, lab utilities and correlation runner are committed as `3ecd955`. The reliability section above describes the new maintenance tooling and its remaining external prerequisites. Preserve the deferred explanation draft without publishing it. The detailed historical sections below explain how this checkpoint was reached.

## Deployed: source-freshness visibility

Frontend commit `f7786fd` adds **Telemetry freshness** to the private workspace and per-source last-ingestion contact in browser-local time and explicit UTC. States distinguish recent contact, stale (at least 15 minutes), never received, revoked and invalid/future timestamps needing review. This is an ingestion-freshness indicator, not a heartbeat or proof that a collector is offline. Idle lab/replay sources can legitimately be stale. Queue depth and guest service state are not available from the sources API.

The summary shows when its source snapshot was fetched; Refresh retrieves current source information, including on Network events. Age labels recalculate locally every 30 seconds without background API polling. Public sources remain labelled demo fixtures. The existing sources API is unchanged; no backend deployment, schema migration, credential, collector or detection-threshold change is needed for this feature.

All five frontend freshness tests pass (boundary timing, revoked/never distinction, invalid/future times, UTC/IST equivalence and age labels), and the production build succeeds. The source was pushed and the production Vercel JavaScript was verified to contain the new feature while the website returned HTTP 200. Automated browser layout inspection was blocked by URL detection. The owner subsequently provided screenshots verifying the freshness summary and all four source rows, including local/UTC timestamps. The explanation panel is disconnected from the frontend, and its backend draft remains unpublished.

## Completed: contemporary SSH/network correlation

The owner authorized proceeding with the live correlation milestone. Read-only database inspection still found four incidents and no new failed-login cluster; the Ubuntu `soc-lab-test` incident is dated 14 November UTC and cannot match today's flows within the existing two-minute context window. The isolated correlation test passed, including workspace, endpoints, protocol and time exclusions.

The prepared `scripts/test_ssh_correlation.ps1` checks API readiness, the existing non-admin test account's standard group memberships and password status, all three services, guest address/time, effective SSH password-auth configuration, and common lockout controls. It stops for review if those checks fail. The owner runs it interactively: correct `aisoc`/sudo credentials for read-only preflight, then one deliberately incorrect password for `soc-lab-test` in each of five separate connections. No passwords are captured, no events are manually ingested, and no accounts, credentials, settings or checkpoints are changed by the script. Five attempts must complete within 120 seconds. The runner stops if a connection succeeds or the window is nearly exhausted; exit code 255 alone is not treated as proof of a failed-password event. The owner should abort on missing prompts or unexpected errors and inspect evidence before any retry.

The owner executed the live test once, with five separate one-prompt connections in 26.4 seconds. Read-only database verification found exactly five `LOGIN_FAILED` records from **Ubuntu SSH journal v2**, for `soc-lab-test`, `10.0.2.2` to `10.0.2.15:22`, spanning 19.416 seconds (`2026-11-21T23:43:46.466007Z` through `23:44:05.882007Z`). A single new incident `0501d95b-b053-41d0-995d-1d53fa1f6ca9`, **Possible brute force against soc-lab-test**, was created at `2026-11-21T23:44:10.558519Z` (22 November 05:14:10 IST), open/high with score 50/100 and exactly those five linked authentication events.

At verification, the existing backend correlation query returned three **Ubuntu Suricata** TCP flow records in the same workspace and matching endpoint/time window, with source ports 63363, 53468 and 60759. Additional exported records may arrive later. This proves stored authentication detection and retrieval of contemporary network context without synthetic ingestion or threshold changes. The authentication schema does not retain the SSH peer source port, so this query alone does not establish a one-to-one mapping between every related TCP flow and a failed session; other sessions behind NAT can qualify. Hosted browser verification is now complete: the agent opened this exact incident in the signed-in production website and observed **5 linked events · 7 related** in its Evidence timeline, all five Login Failed entries for soc-lab-test, seven Related Network Flow entries from Ubuntu Suricata, HIGH severity, 50/100 risk (40 rule severity + 10 authentication evidence), the brute_force_v1 rationale and Open disposition. Four more flow records had arrived since the first three-record database check. The live SSH/network context milestone is complete through the hosted UI. No disposition, records or configuration were changed during inspection; no repeat test is needed.

## Completed: recover Suricata forwarding after copytruncate

The owner's fresh port-18080 test was captured locally at `2026-11-22T02:48:43.838647+0530`, but did not reach the API. SSH delivery continued. All three guest services were active and the clock synchronized. The forwarder repeatedly reported that EVE changed before the saved offset. The guest's logrotate policy uses `compress` and `copytruncate`: the active file retained its inode but shrank below saved offset `56857868`.

Read-only inspection confirmed that `eve.json.1.gz` matches the saved 128-byte checkpoint anchor, passes gzip EOF verification and contains exactly `56857868` uncompressed bytes. The collector was already at that archive's EOF. The current file retains the new lab flow; queue count was zero. The old collector only handled rename rotation and cannot transition safely after this truncation.

The local fix validates an immediate numbered `.1` or `.1.gz` predecessor against the saved checkpoint, resumes any unread archived tail, and transitions to the current file after verified archive EOF. Gzip integrity is checked before staging records, with a 128 MiB decompression limit. Missing/mismatched/ambiguous/corrupt archives fail without discarding state. Multiple intervening rotations need review rather than skipping files. Standard copytruncate can itself lose bytes during its copy/truncate race; archive recovery cannot restore bytes absent from both files.

All 21 collector tests pass, including archived EOF recovery, non-SSH delivery, unread tails across process restarts, queue capacity, invalid archives and transactional rollback. The targeted `collector/upgrade-suricata-rotation.sh` is prepared and Bash syntax-checked. It stops only the Suricata forwarder, backs up code/SQLite/archive and original archive ACL under a private `/var/backups/ai-soc-suricata/rotation-*` directory, re-verifies this exact EOF case, grants the existing service group archive read access, installs only the forwarder and starts it. It never restores an old database over newer state or resets a checkpoint. On failure it restores the old code/ACL and attempts to restart the forwarder. No Ubuntu changes have been executed by the agent.

The owner applied the prepared upgrade and shared its success output. A subsequent read-only Supabase check verified automatic delivery of the exact pending test flow: TCP `10.0.2.2:52439` to `10.0.2.15:18080`, event time `2026-11-21T21:18:43.838647Z` (22 November 02:48:43 IST), API receipt `2026-11-21T22:10:32.522636Z` (22 November 03:40:32 IST), source **Ubuntu Suricata**. Several backlogged SSH-port network flows arrived afterward. No manual event import or new test traffic was used. Collector recovery and automatic non-SSH delivery are verified in the database; the owner also shared a hosted Network events screenshot showing fresh Suricata flows after recovery. Keep the generated private backup directory. The upgrade output confirms the sensor, SSH collector, token, configuration and detection thresholds were not changed. AI/explanation remains deferred; no hosted application deployment was needed for this collector fix.

## Resume checkpoint: 19 November

The hosted frontend and API returned HTTP 200. Render still reports API version `0.2.0`. VirtualBox reports `AI-SOC-Ubuntu` in saved state, with only the original `SSH-local` forwarding rule. No VM changes or test connections were made during this check.

The historical local draft added `GET /api/incidents/{incident_id}/explanation` and an **Explain incident** panel. It summarizes stored rule rationale, linked evidence counts, timestamp span, existing risk, related network context, and manual investigation suggestions. Findings cite event IDs and link to timeline entries. This is a deterministic evidence summary, not an LLM integration. No AI provider was selected. The owner deferred this feature; its active integration was later archived locally before the Security Events release, as recorded above.

Validation: 20 backend tests passed, 8 collector tests passed, and the frontend production build succeeded. Backend tests cover explanation citations, correlated context, port-scan evidence, missing evidence, anonymous rejection and workspace isolation. The feature has not been verified in a hosted browser or deployed yet. No migrations, credential changes, collector updates or checkpoint resets are needed for this feature.

The owner has deferred incident explanation and AI work until the fundamentals are more complete. Keep this implementation as a local draft; do not publish it as the next release. No AI account or API key is needed for the current milestone.

Priority order:

1. Verify automatic delivery of a fresh non-SSH flow through the upgraded forwarder, without a manual import. Resume the saved Ubuntu VM and use the single-port check in the lab guide.
2. Verify a contemporary SSH incident's network context, with an explicitly authorized lab test. Older incidents cannot validate correlation with traffic outside their time windows.
3. Improve operational visibility: source freshness, collector delivery failures and queue health. Distinguish an idle source from a proven collector failure; last-received time alone cannot prove a service is down.
4. Improve the analyst workflow: searchable authentication/network evidence and useful event details, followed by notes, assignment and accessible audit history as appropriate to the existing schema.
5. Complete deployment reliability checks: persisted data after redeploy, restart/retry behavior, backup/recovery and bounded API usage before returning to AI.

Keep the existing records, sources, credentials, queues and checkpoints. Do not change detection thresholds merely to make a test pass. Any new authenticated traffic test remains subject to the owner's existing requirement to start the listener and authorize connections first.

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

The hosted TCP port scan rule was verified on 16 November 2026. Suricata captured eight TCP flows from `10.0.2.2` to `10.0.2.15:18080–18087` across 7.986 seconds. The old guest forwarder skipped those ports. The owner upgraded it and approved a one-time import of the captured EVE records using the existing Suricata source. Supabase showed one open medium-severity **Possible TCP port scan** incident with a score of 45/100 and eight linked flows. The temporary listener was stopped and the eight lab NAT rules were removed. Automatic delivery for newly captured flows on the expanded port range remains a separate check.
