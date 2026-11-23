# Workspace access management

API 0.6.0 adds admin-only membership listing, access-audit listing and workspace revocation. New grants remain owner-operated through the reviewed CLI. No browser role selection, public registration, Auth-user deletion or schema migration is added.

## Administrator website

The private **Workspace access** tab is visible to administrators. It lists account UUIDs/roles and paginated membership audit history for the current workspace only. No Auth email directory or secret metadata is returned. Older provisioning can predate audit records.

Review the exact account ID before revocation. The confirmation panel requires typing the full ID. The server independently rechecks the administrator under a workspace row lock, refuses self-revocation, refuses removal of the last administrator, and rejects other-workspace or missing users. After a successful removal it commits the membership deletion and `membership.revoked` audit entry together. A repeated deletion returns 404 rather than recording a second success. The screen refreshes member/history pages after acknowledgement.

Revocation affects subsequent private API authorization checks, even if the person still holds a valid Supabase session. An already authorized in-flight request can complete, and downloaded data cannot be recalled. Auth accounts, incidents, notes, evidence and telemetry sources remain present. Ingestion tokens are separate credentials: membership removal does not invalidate a token the person previously obtained. Review affected source tokens separately through the existing source controls; never reset operational collectors merely for this feature test.

## Owner commands

Run from `backend`, using the existing private environment. Verify the Supabase Auth user's UUID and workspace before granting access. Additional analysts join the existing workspace:

```powershell
.\.venv\Scripts\python.exe -m app.manage grant-member --user-id VERIFIED_AUTH_USER_UUID --role analyst --workspace-id EXISTING_WORKSPACE_UUID
```

Defaults remain analyst and an existing workspace is required for that role. Only explicit `--role admin` can provision an administrator. Duplicate memberships are refused. There is no role-promotion or workspace-move shortcut. Existing-workspace grants take the same workspace lock as revocations.

Owner-only revocation needs the exact user ID twice:

```powershell
.\.venv\Scripts\python.exe -m app.manage revoke-member --user-id VERIFIED_AUTH_USER_UUID --workspace-id EXISTING_WORKSPACE_UUID --confirm-user-id VERIFIED_AUTH_USER_UUID
```

This local operator command records actor `owner-cli` and also protects the last administrator. The website additionally protects an administrator's own access. The owner CLI is an operation authorized by possession of the private database configuration, not a browser login or an authenticated human identity in the audit record. Do not run a live removal as a demonstration; use a dedicated approved test analyst if a controlled hosted acceptance is needed.

## API and deployment

- `GET /api/members?limit=25&offset=0`
- `GET /api/members/audit?limit=25&offset=0`
- `DELETE /api/members/{user_id}`

All require authenticated administrator membership. Pagination is bounded, audit actions/fields are allowlisted and workspace-scoped, and mutations use existing request admission controls. DELETE is added to the exact-origin CORS configuration. Grants have no new HTTP endpoint.

Deploy the backend before publishing the administrator tab. The frontend handles an older API's 404 with an upgrade message, but the release should still be staged in order. Verify API version 0.6.0, readiness and anonymous 401 responses; then publish the frontend and inspect the administrator screen without revoking the real owner. Existing schema version remains 1. No secrets or extra environment variables are required.

## Validation

Synthetic tests cover admin-only access, workspace boundaries, pagination, bounded safe audit fields, last-admin protection, self-protection with multiple admins, stale administrator rechecks, failed/repeated removal behavior, post-revocation denial, unchanged telemetry sources and exact CLI confirmation before a database connection.

A separate real PostgreSQL 17.12 concurrency test used a newly created disposable local database. Two owner operations simultaneously attempted to remove the two synthetic administrators; exactly one succeeded and the other was refused as the last administrator. One administrator and one audit entry remained. The disposable database was removed and the local lab stopped. The previously restored database and hosted Supabase were untouched. This verifies the supported shared-workspace-lock path, not arbitrary out-of-band SQL modifications that bypass these tools.

To rerun the opt-in test, explicitly prepare an empty disposable local database named `ai_soc_membership_test_` followed by eight lowercase hexadecimal characters on `127.0.0.1:55432`, privately set `SOC_TEST_POSTGRES_URL`, and run `tests/test_memberships_postgres.py`. The test refuses other endpoint/name patterns. Never point this test at Supabase or the recovered archive database.
