# Incident queue

Private analysts can search all stored workspace incidents, including records beyond the former latest-100 browser list. Search is a literal, case-insensitive substring of title or incident ID. Percent signs, underscores and backslashes are treated as text, not wildcard syntax.

1. Open **Incidents** (or use the overview queue).
2. Enter a title/ID and optionally select status, severity and detection type. Creation-time bounds use your browser's local timezone and are converted to explicit UTC for the API. Bounds are inclusive and apply to incident creation, not evidence event time.
3. Choose newest, oldest or highest-risk order, then **Apply filters**. Applying/Clear resets to page 1. Clear retains the selected page size.
4. Use 10, 25, 50 or 100 incidents per page, with Previous/Next. Counts refer to all matching incidents, not just loaded rows.
5. Open an incident and return to preserve filters/page size/page position. A queue/workspace Refresh restarts at page 1 with the applied filters and a fresh creation cutoff. Account/workspace changes clear queue state. Failed list requests show an error and retry control; no demo data is substituted for private records.

Paging retains a server-issued `as_of` creation cutoff so newly created incidents do not shift existing pages. This is not an immutable database snapshot: status, risk or other updates can change matching rows/order/counts between requests. Refresh to include newly created incidents or recover an empty page after updates.

The public demo applies equivalent controls only to its fixed synthetic records. Browsing is read-only; no source, evidence, incident, audit entry, collector or model request is created by queue search.

## API compatibility

API 0.8.0 adds authorized `GET /api/incidents/search` before the dynamic incident detail route. Existing `GET /api/incidents` list responses remain unchanged. Parameters:

- `q` (maximum 200 characters); optional `status`, `severity`, `rule_key` for the four existing detections.
- `start_time`, `end_time`, `as_of`: explicit timezone timestamps. Naive/reversed ranges and future snapshot times are rejected.
- `sort`: `newest` (default), `oldest`, `risk`; ties have deterministic incident-ID ordering.
- `limit`: 1–100 (default 25); `offset`: 0–1,000,000.

Response: `items`, `total`, `offset`, `limit`, `has_more`, `as_of`. Every count, alert-existence filter and row query is scoped to the authenticated workspace. Repeated matching alerts do not duplicate incidents. No migration is required. Offset paging and literal substring search suit the current dataset; large-scale full-text search and keyset pagination are separate future optimizations.
