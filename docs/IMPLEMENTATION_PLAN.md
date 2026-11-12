# AI SOC Assistant: implementation plan

Prepared 11 November 2026 after reviewing all 26 rendered pages of AI_SOC.pdf. Several pages contain content absent from PDF text extraction; the plan includes that content.

## 1. Product and scope

Build a miniature, explainable SOC for an academic demonstration, with a publicly reachable website. The owner confirmed a public demo plus a private analyst workspace. This is not a replacement for an enterprise SOC or a promise to detect every attack.

The complete pipeline is:

`Lab sensors -> collector -> authenticated ingestion -> normalization -> durable events -> rules -> alerts -> correlation -> scored incidents -> analyst dashboard -> evidence retrieval -> AI explanation -> human decision -> audit trail`

Public access means anyone can explore the demo. It does not give visitors permission to read private telemetry, ingest data, change rules, invoke unlimited paid AI, or administer the application.

## 2. Requirements traceability

| Document pages | Requirement | Planned implementation / proof |
| --- | --- | --- |
| 1-6 | SOC workflow; analyst and admin roles | Public demo, invite-only analyst login, administrator settings; complete investigation walkthrough |
| 6-9 | Real telemetry, network and application logs | Suricata EVE JSON plus target authentication logs; collector and parser fixtures; reproducible authorized lab capture |
| 9-12 | Normalization and transparent detection | Typed normalized event schema; versioned deterministic rules; supporting event IDs on every alert |
| 10 | ML trained/evaluated on security datasets | Separate research milestone, with feature compatibility and honest evaluation; do not claim implemented ML in a rules-only release |
| 13-14 | Correlation and risk | Time/entity-aware incident grouping; documented bounded score with visible component contributions |
| 14-18 | Evidence-grounded AI and human decisions | Authorized incident retrieval, knowledge search, citations, limited recommendations, persisted investigations |
| 18-20 | Dashboard, incident details, timeline | Search, filters, severity counts, event timeline, evidence panel, assistant, analyst dispositions |
| 20-25 | React, FastAPI, PostgreSQL, APIs, authentication, Docker | Monorepo, migrations, managed auth, role checks, containers, deployed frontend/API |
| 25-26 | Build vertically and demonstrate | Milestone gates below; no hard-coded dashboard presented as completed backend |

The document repeats/overlaps section numbers and only begins its week-by-week schedule. Its exact thresholds, correlation algorithm, ML scope, and risk formula are not specified. Values below are proposed starting defaults and must be validated.

## 3. Recommended architecture

| Component | Choice | Responsibility |
| --- | --- | --- |
| Website | React + TypeScript + Vite | Public demo, login, dashboard, incidents, investigation chat, admin pages |
| Frontend hosting | Vercel | Static application hosting, HTTPS, preview deployments |
| API | Python + FastAPI | Validation, authorization, ingestion, incident APIs, AI orchestration |
| API hosting | Render web service | Runs the Python service; upgrade from free compute for continuous availability |
| Database | Supabase PostgreSQL | Durable events, incidents, rules, investigations, memberships, audit |
| Identity | Supabase Auth | Login/session management; backend verifies tokens and roles |
| Retrieval | PostgreSQL + pgvector | Knowledge chunks and historical incident similarity, with access filters |
| AI | Hosted LLM and embedding provider, chosen later | Backend-only calls; citations and usage limits |
| Initial sensor | Suricata in a Linux lab | Network alerts and flow records |
| Additional telemetry | Target app/auth logs | Login outcomes, user identity, application privilege and access events |
| Collector | Small Python agent in the lab | Read logs, checkpoint offsets, batch/retry delivery over HTTPS |
| Local development | Python/Node; Docker Compose when available | Reproducible services and test database |

Supabase supplies PostgreSQL, authentication, and vector support. It does not by itself deploy this proposed FastAPI process or observe traffic on your computer. A static website cannot capture arbitrary network traffic. Sensors run where they can see the monitored traffic.

Sites hosting was considered. Its Worker runtime is a different server model from the PDF's Python/FastAPI backend. The recommended initial deployment keeps the PDF's stack on a Python host rather than translating the backend merely to fit that runtime.

Start without Redis, Kafka, Kubernetes, or a separate vector database. At low event volume, persist a processing job in PostgreSQL in the same transaction as ingestion; process through a durable worker with leases/retries. A local worker runs alongside the API. A hosted worker needs its own runtime, so account for that expense before claiming continuous processing. An initial bounded synchronous processing path is acceptable for a small demo if events remain durable and replayable; never rely on untracked in-memory background tasks.

## 4. Public demo and private workspace

- Public demo: fixed, sanitized, clearly labelled demonstration data; locally simulated investigation interactions or precomputed AI answers. No shared editable analyst account and no unrestricted paid AI endpoint.
- Private workspace: invite-only membership. Analysts investigate and record dispositions; admins additionally manage members, sources, and rules.
- Prefer separate demo and private databases/projects. If sharing infrastructure, isolate namespaces, database permissions, queries, caches, and retrieval. Test that a guessed ID cannot cross the boundary.
- UI labels distinguish synthetic seed data, replayed lab telemetry, and live telemetry. Replay is useful but does not prove live collection.
- Deployment uses a provider-generated HTTPS URL initially. A paid custom domain is optional.

## 5. Screens

1. Landing/demo entry with a plain description and link to the public dashboard.
2. Login and account recovery; invitation-based private access.
3. Dashboard: computed event/alert/incident counts, severity distribution, activity chart, sensor health.
4. Incidents: search, severity/status filters, pagination, ownership, most recent activity.
5. Incident details: score explanation, source/asset/user, evidence, ordered timeline, related alerts, analyst notes, disposition.
6. Investigation assistant: current incident context, cited answers, similar cases, actionable investigation suggestions, provider error states.
7. Events/alerts: source filters, raw versus normalized record, detection explanation.
8. Administration: source credentials and revocation, rule configuration/versioning, memberships, audit history.

Design responsive layouts and accessible controls. Display empty/loading/error states; do not display invented metrics as live results.

## 6. Data model

Use UUID identifiers, UTC timestamps, database constraints, paginated APIs, and indexed query paths. Keep event time separate from ingestion time.

| Table | Important fields |
| --- | --- |
| workspaces | id, name, access mode |
| profiles / memberships | auth user ID, workspace ID, role; no duplicate password storage |
| sources | workspace ID, sensor identity, type, last_seen_at, enabled |
| source_credentials | source ID, hashed token, expiry, revoked_at |
| assets | workspace ID, hostname/IP, criticality |
| security_events | workspace/source IDs, external ID, event_time, ingested_at, type, IPs/ports, user, protocol, bytes, normalized data, raw JSON, schema version |
| processing_jobs | event/batch ID, state, attempts, lease expiry, next retry, error |
| detection_rules | workspace ID, rule key/version, enabled, threshold, time window, configuration |
| alerts / alert_events | rule/version, severity, evidence links, deduplication key |
| incidents / incident_alerts / incident_events | title, state, owner, entities, score components, links, first/last seen |
| investigations / messages | incident/user IDs, question, answer, cited evidence, model/version, usage |
| knowledge_documents / knowledge_chunks | workspace or approved shared scope, source URL/version, chunk text, embedding |
| recommendations | incident ID, suggested action, priority, approval/disposition, actor |
| audit_logs | workspace/user/source IDs, action, target, timestamp, redacted change details |

Unique `(source_id, external_event_id)` or a documented stable content identity prevents retry duplicates. Raw evidence must not be silently edited. Use an explicit retention policy, restricted deletion, and exports/backups; unlimited raw telemetry will outgrow small free databases.

RLS protects tables exposed through Supabase's Data API. A backend connection using privileged credentials may bypass RLS: implement explicit authorization/scoping and preferably a restricted database role. Never assume enabling RLS alone secures a privileged backend query.

## 7. Ingestion and real lab

First lab: a Linux target with a test application/SSH, a traffic source VM, and Suricata positioned to observe their traffic. Depending on topology the sensor may run on the target; a third VM is not mandatory. VM memory requirements depend on the chosen topology; inspect the host before allocating resources.

Use an isolated virtual network and only systems you own or have permission to test. The collector makes outbound HTTPS requests to the cloud API; the cloud does not need an inbound path into the lab.

Suricata does not magically expose successful logins or privilege changes inside encrypted sessions. Collect those from the target application/system. Add Zeek later when its protocol telemetry has a demonstrated use.

Collector requirements: durable offsets; handle rotation and partial JSON lines; spool unsent batches locally with size limits; exponential backoff; validate timestamps; reject/review oversized malformed records; never send the Supabase database key to a sensor. Use a revocable source token scoped only to ingestion.

Initial event contract: schema_version, external_event_id, event_time, event_type, source/destination IP and port, username (nullable), protocol (nullable), byte counts, asset ID if known, raw event. The server derives workspace/source from the credential rather than trusting a client-supplied workspace ID.

## 8. Proposed detection and correlation

These defaults are hypotheses for lab validation, not established detection accuracy.

| Rule | Initial definition | Caveat |
| --- | --- | --- |
| Brute force | At least 5 failed logins for the same user, service, destination, and source within 2 minutes | Also evaluate distributed attempts separately later |
| Port scan | At least 20 distinct destination ports from one source to one target within 60 seconds | Legitimate scanners can trigger it |
| Suspected account compromise | Login success after the brute-force pattern within 10 minutes for the matching entities | Success alone does not prove compromise |
| Suspicious privilege activity | Privileged action after suspicious authentication for the same user/asset within 15 minutes | Requires application/system audit evidence |
| Possible exfiltration | More than a configurable outbound-byte threshold, initially 100 MB in 5 minutes, linked to an incident/asset | Requires flow direction and context; volume alone is weak evidence |
| IDS signature | Relevant Suricata signature, mapped to internal severity with original signature retained | Sensor severity is evidence, not certainty |

Keep state in durable queries/processing, not process-global arrays. Handle late events with a documented lateness allowance and bounded replay. Tests must cover time-window edges, duplicates, out-of-order arrival, benign activity, and disabled rules.

Correlate using workspace, matching target/asset and user/source relationships, and an initial 15-minute window. Do not group solely by source IP; NAT/shared infrastructure would merge unrelated activity. Link every merged alert and preserve the rationale. Never automatically reopen a closed incident without an explicit policy; create a related incident when appropriate.

Proposed score: `min(100, highest_rule_severity + alert_diversity + asset_criticality + sequence_evidence + privilege_or_data_impact)`. Cap each component: 40, 15, 15, 20, 10 respectively. Severity bands: low 0-29, medium 30-49, high 50-74, critical 75-100. Repeated identical alerts should not inflate the diversity component. Show the actual contributions. This score is prioritization, not a probability or a calibrated '94% confidence'.

## 9. RAG and AI

1. Authenticate the analyst; authorize the requested incident.
2. Fetch exact current incident evidence from SQL, including event IDs and rule rationale. Do not rely on vector similarity to reconstruct event facts.
3. Retrieve approved response procedures, security references, and authorized historical cases. Filter access before selecting passages.
4. Construct a bounded context, treating log text and retrieved documents as untrusted data, never executable instructions.
5. Ask the LLM for a structured answer: observed facts, interpretation, uncertainty, recommended investigations, evidence citations.
6. Validate cited IDs against the context, persist question/answer/provenance, and show linked source material.

Keep embeddings/model configuration versioned; vector dimensions must match the embedding model. Redact unnecessary secrets and personal data before sending context to a provider. Decide retention/provider data handling before using real organizational logs.

No shell execution, blocking IPs, resetting credentials, or revoking sessions in the first release. Record analyst decisions. Recommendations do not imply actions were performed. If evidence is missing or the model provider is unavailable, display that clearly; an evidence-only fallback must be labelled.

Evaluation: build a small reviewed incident-question set with expected evidence and unsupported-claim checks. Include missing evidence, contradictory logs, malicious instructions embedded in logs, cross-workspace retrieval attempts, provider failures, and rate/cost limits.

## 10. ML milestone

The PDF names CICIDS2017 and UNSW-NB15. Confirm whether your academic rubric requires an implemented model. Until resolved, track ML as a separate required-scope decision, not a silently completed feature.

Choose one dataset, verify usage terms/provenance, document features, avoid train/test leakage, and report precision/recall/F1 plus class-wise errors. Split by time/session/source appropriately rather than leaking near-duplicate flows across random splits. Do not equate dataset accuracy with real network accuracy. A live model requires the same feature extraction used in training and explicit handling of distribution shift. Retain rules and explain any additional ML alert source separately.

## 11. API plan

Supabase handles authentication flows; do not recreate password handling merely to copy illustrative PDF endpoints.

- `GET /health/live`, `GET /health/ready`
- `GET /api/me`
- `POST /api/events/batch` (source credential; bounded batch; idempotent acknowledgement)
- `GET /api/events`, `GET /api/events/{id}`
- `GET /api/alerts`, `GET /api/alerts/{id}`
- `GET /api/incidents`, `GET /api/incidents/{id}`
- `PATCH /api/incidents/{id}` (allowed state transitions, assignment, notes)
- `POST /api/incidents/{id}/investigations`
- `GET /api/dashboard/stats`
- Admin-only source/rule/member management and audit retrieval

Define request/response schemas before frontend integration. All private queries and mutations authorize workspace membership and role. Public demo endpoints read only demo data. Add bounded pagination, rate limits, request IDs, and non-sensitive error responses.

## 12. Delivery milestones and acceptance gates

| Milestone | Deliverable | Gate before moving on |
| --- | --- | --- |
| 1. Foundation | Monorepo, local API/frontend, migrations, login, roles, initial cloud deploy | User can sign in; API rejects invalid tokens; health checks work; private data is inaccessible anonymously |
| 2. First vertical slice | Ingest -> database -> one brute-force rule -> incident -> UI timeline | Known event batch creates exactly the expected result; resending creates no duplicates |
| 3. Real telemetry | Collector, Suricata, authentication logs | Trace a real authorized lab event through raw evidence, normalized record, alert, and dashboard |
| 4. Detection/correlation | Rules, relationship logic, explainable score | Positive/negative and late-event cases pass; unrelated users/assets stay separate |
| 5. Investigation workflow | Filters, notes, ownership, false-positive/closed states, audit | Analyst can complete and audit a full investigation |
| 6. RAG/AI | Knowledge ingestion, cited answers, similar cases, usage limits | Evidence review passes; no cross-boundary retrieval; missing evidence and outages handled |
| 7. ML if required | Reproducible model evaluation and compatible inference | Honest held-out metrics and documented live limitations |
| 8. Public release | Sanitized demo, private workspace, deployment docs, backups, monitoring | Anonymous visitor can use demo; private access tests pass; restart/redeploy preserves records; restore tested |

Indicative planning range for one developer learning the stack: 6-10 weeks part-time for a credible academic version, with substantial uncertainty for lab/ML scope. This is an estimate, not a committed deadline. Deliver each milestone as a working slice rather than waiting until the end to connect components.

Proposed repository layout: `frontend/`, `backend/app/`, `backend/tests/`, `collector/`, `supabase/migrations/`, `knowledge/`, `fixtures/`, `infra/`, `docs/`. Commit lockfiles, migrations, and sanitized examples. Exclude credentials and raw private telemetry.

## 13. Release verification

- Automated: rule boundaries, normalization, idempotency, correlation isolation, API permissions, lifecycle transitions, citation validation.
- Browser: demo/login, dashboard, filters, timeline, investigation, mobile layout, loading/error states.
- Operational: collector restart/rotation, API downtime/retry, worker retry, database migration, backup restore, deployment rollback, sensor health/staleness.
- Security: unauthenticated access, unauthorized IDs, analyst/admin separation, revoked source token, excessive batch size, secret exposure, prompt injection, AI quota enforcement.
- Demonstration: a recorded authorized lab sequence from collection to human closure, plus a benign sequence that does not produce the same incident.

At the initial planning stage none of these components existed. Update after the next work session: the first local API/frontend slice now exists, with 12 passing API tests and a successful frontend production build. The public demo was checked in a desktop browser. Cloud login, PostgreSQL migration execution, public deployment, real sensors, multistage correlation, trained ML, and evaluated AI remain unverified or unimplemented. See the root README for current implementation limits.

## 14. Technical references checked

- Supabase JWTs: https://supabase.com/docs/guides/auth/jwts
- Supabase RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase pgvector: https://supabase.com/docs/guides/database/extensions/pgvector
- PostgreSQL connections: https://supabase.com/docs/guides/database/connecting-to-postgres
- Render FastAPI: https://render.com/docs/deploy-fastapi
- Render free service limits: https://render.com/docs/free
- Vite on Vercel: https://vercel.com/docs/frameworks/frontend/vite
- Vite client environment exposure: https://vite.dev/guide/env-and-mode.html
- Suricata EVE reference: https://docs.suricata.io/en/latest/output/eve/eve-json-output.html (latest includes development documentation; pin a stable release when implementing)
