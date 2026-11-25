# Incident ownership and investigation tracking

Approved admins and analysts can assign, reassign or unassign incidents within their own workspace. Ownership tracks responsibility; it does not grant access, notify anyone, run a response action, or change incident status. Existing analyst notes and status history remain the investigation record.

## Use the website

1. Open a private incident and find **Incident ownership**.
2. Choose an approved member under **Assigned analyst**, or choose **Select myself**. Members are identified by full account UUID and role, without exposing email addresses. **Load more members** pages through the approved directory when necessary.
3. Choose **Save assignment**. Selecting a person alone does not save. The current owner and incident audit history update after success.
4. To release ownership, select **Unassigned** and save. This retains the previous ownership history.
5. Use queue **Assignee** filters: all owners, assigned to me, unassigned, inactive owner or a specific complete member UUID. The assignee column abbreviates UUIDs; its title exposes the full ID. The public demo has no ownership controls.

Assignment to a removed member is shown as inactive; it is not silently erased or counted as unassigned. Reassign or unassign such incidents. Directory results are checked again at save time; stale selections of removed or foreign-workspace members are rejected. Closed incidents may have responsibility adjusted without reopening them.

If a save reports that ownership changed, choose **Refresh ownership**, review the current owner, then select and save again. Another analyst's change is never silently overwritten. After a network error, retrying the unchanged selection reuses its request ID. A replay returns current ownership and does not reapply an old assignment after a later change. Edits after an uncertain save may require refreshing because the original write could have completed.

## Storage and API

No migration is needed. Schema version 1 and the nine application tables are unchanged. Current ownership is a projection of the latest `incident.assignment_changed` audit entry ordered by creation time and ID. New incidents with no entry are unassigned. Changed events contain before/after UUIDs, verified actor/time, expected revision and retry UUID. No-op receipts use `incident.assignment_checked` and are excluded from analyst change history. Existing application backups already include this audit state.

API 0.9.0 adds:

- `GET /api/assignment-candidates`: approved workspace member UUID/role/self flag only; bounded pagination, no Auth account/email/credential queries. Available to approved admins and analysts.
- `GET /api/incidents/{id}/assignment`: current assignee, active/self flags and revision.
- `PUT /api/incidents/{id}/assignment`: required `assignee_id` UUID or null, `expected_revision` UUID or null, `request_id` UUID. Actor/workspace fields cannot be supplied.
- `/api/incidents/search?assignee=me|unassigned|inactive|<UUID>`: scoped owner filters and batched ownership summaries. History reads include sanitized assignment changes; request IDs/receipts are not exposed there.

Assignment writers take the same workspace lock as supported membership writers, recheck the actor, then lock the incident. Eligibility, revision comparison, audit append and incident update commit atomically. Retried request IDs are payload-bound and cannot overwrite newer ownership. Pending membership revocation and assignment serialize; a revoked owner cannot remain marked active. Existing note/status/AI behavior and telemetry collection remain independent.

The creation cutoff used for queue paging does not freeze assignments; ownership changes can move matching results, just as status/risk changes can. Refresh when necessary. Audit-derived projections suit the current workload; a dedicated indexed assignment column/projection could be added in a future reviewed migration if volume warrants it. Nothing deletes existing audit history to make this feature work.
