# Incident investigation reports

Approved workspace members can download an incident report from the private incident's **Investigation report** panel. Public demo pages do not expose this control.

## Download and print

1. Open a private incident and locate **Investigation report**.
2. Choose **Printable HTML (.html)** for a readable offline report, or **Structured JSON (.json)** for machine-readable data.
3. Leave **Include the latest saved AI analysis** checked, or uncheck it. Export never generates an AI analysis and does not consume model quota.
4. Select **Download report** and check the browser's downloads. The filename is `aisoc-incident-<UUID>.html` or `.json`; it never uses untrusted incident titles.
5. Open HTML locally. For a PDF copy, use the browser's **Print → Save as PDF**. There is no native PDF export or automatic print invocation in this release.

Reports contain incident identity/status/severity/risk, detection rationale, normalized linked evidence, separately labeled related network context, ownership, analyst notes, status/assignment history and optional latest saved AI interpretation. Event/alert/history IDs and UTC timestamps support traceability. Saved model/knowledge/time/context-fingerprint metadata, limitations, truncation information and outdated flags are retained. AI citation links point to evidence inside the HTML; a citation absent from the current report is labeled accordingly rather than given a broken link.

The report includes private usernames, network addresses and analyst notes. It excludes collector/source credentials, token hashes, provider keys, arbitrary raw event payloads, AI retry receipts and unrelated audit metadata. Files are unencrypted copies; website access controls do not follow a shared downloaded file. Store/share them accordingly. Reports have no scripts or remote assets; untrusted text is HTML-escaped and a restrictive content policy is embedded. Reference URLs are plain text.

## Snapshot and completeness

Production PostgreSQL exports read incident, evidence, notes, ownership, history and saved AI within one read-only repeatable-read transaction. A change committed during the read appears in a subsequent report, not halfway through the first one. The authentication lookup releases its connection before the report snapshot, so even a one-connection pool can serve exports. Current membership is rechecked after rendering and before delivery. SQLite development exports are best-effort reads; the production snapshot guarantee relies on PostgreSQL.

Bounds are explicit: at most 1,000 linked events, 1,000 related network records, 500 notes, 2,000 history entries, 100 alerts and 100 authentication endpoint groups. JSON payloads are capped at 4 MiB and downloaded files at 8 MiB. Exceeding a bound returns HTTP 413 and generates no partial report. The export's related-network query is not silently capped by the dashboard's 50-record display limit. It uses the existing TCP endpoint/two-minute association semantics and excludes linked events from the contextual section.

A report is an application investigation snapshot, not a packet capture, database backup, digital signature or proof of compromise. Risk remains a rule-based priority, and saved AI remains advisory. The model context fingerprint identifies the model input version; it does not sign the report file. Report IDs are generated per download and are not persisted as new audit records.

## API

API 0.10.1 adds authorized `GET /api/incidents/{id}/report?format=html|json&include_ai=true|false` (default HTML, AI included if already saved). Format is validated, IDs become canonical UUID filenames, queries remain workspace-scoped, and responses are attachments with `no-store, private`, `nosniff` and restrictive content-security/referrer headers. Browser requests send the existing session only in the Authorization header; no token is placed in the download URL. The frontend aborts an in-flight export on incident/account boundary changes to avoid downloading a stale response after leaving the view.

Export is read-only: it does not mutate status, assignments, notes, evidence, AI quota, database schema, collector checkpoints or credentials. It uses the existing nine-table schema and needs no migration, provider account, new service or new runtime dependency.
