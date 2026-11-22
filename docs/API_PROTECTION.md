# API request protection

API version 0.5.0 adds admission control before body buffering, source-token database lookup, Supabase authentication and route execution. Authentication, workspace checks, detection rules and persistence remain unchanged. No migration, new account, paid service or collector update is required.

## Default limits

| Budget | Refill | Burst |
| --- | --- | --- |
| Dashboard/API, per supplied credential | 120 requests/minute | 30 |
| Ingestion, per supplied source token | 120 requests/minute | 30 |
| API aggregate, including invalid/rotated credentials | 600 requests/minute | 120 |
| Ingestion aggregate, independent of API budget | 600 requests/minute | 120 |
| Missing/malformed credentials, shared within each group | 30 requests/minute | 30 |
| Readiness checks, separate budget | 60 requests/minute | 10 |

These are token buckets, allowing a short burst plus continuous refill, not fixed calendar-minute quotas. All protected groups share a maximum of 16 in-flight requests, including body reads. Request bodies remain limited to 1 MiB, batches to 100 events and raw event metadata to 16 KiB. Body reception now has a total 15-second deadline, returning 408 on expiry. Chunked uploads are counted even without Content-Length. GET `/health/live` bypasses admission and body buffering so a liveness check stays lightweight. CORS preflight is handled by the existing outer CORS middleware.

The limiter fingerprints supplied credentials in memory; this step does not establish identity. It never stores/logs raw credentials, and rotating credentials is still constrained by the aggregate budget. A refreshed user access token obtains a new credential bucket; this is not a durable per-user quota. IP and forwarding headers are not used. This avoids relying on unverified proxy headers or combining all Render clients behind one proxy address.

The credential table is bounded to 2,048 entries. Fully refilled idle entries can be reclaimed; a full table rejects new entries instead of evicting exhausted credentials. All state is process-local and resets on restart. Keep the current single worker/instance. Multiple workers or instances require a reviewed shared limiter or gateway before claiming deployment-wide limits. This is application admission control, not network-level DDoS protection, transport connection limits, cost guarantees or a substitute for load/capacity testing. Readiness traffic can itself be throttled under abuse.

## Responses and client behavior

Throttled requests receive HTTP 429, an integer `Retry-After` number of seconds, `Cache-Control: no-store` and a generic JSON detail. The header is exposed to the configured frontend origin. Authentication is still required after an admission slot is granted; limits never make invalid credentials valid. Oversized source-token/Authorization headers return 401 within the anonymous budget. Rejected requests do not create records or successful ingestion acknowledgements.

The existing SSH and Suricata collectors already retain SQLite pending rows/checkpoints on HTTP errors and retry with exponential backoff from 5 to 120 seconds. Their 429 queue-preservation behavior has explicit tests. They currently use that backoff rather than parsing Retry-After. Do not reset their checkpoints, reimport rejected batches manually, or change their credentials. Browser requests show the server's error and can be retried after waiting; writes are not automatically replayed by this change. Notes retain their existing request UUID deduplication behavior.

## Configuration and deployment

Optional environment variables, with defaults that work without adding new Render variables:

```text
SOC_REQUESTS_PER_CREDENTIAL_MINUTE=120
SOC_REQUEST_POOL_PER_MINUTE=600
SOC_REQUEST_BURST=30
SOC_REQUEST_MAX_IN_FLIGHT=16
```

Per-credential rate applies separately to ingestion and API. Pool rate applies separately to each aggregate; aggregate burst is four times configured burst. Anonymous burst is capped at 30. Readiness limits stay fixed. Supported bounds are 30–6,000 per-credential requests/minute, 60–60,000 aggregate requests/minute, burst 1–1,000 and concurrency 1–64; invalid settings fail startup. Increase only after measuring database and Auth capacity.

The existing Render service is manually deployed. Select the reviewed commit on `codex/initial-soc`; leave the source connection, auth keys, origins and start command unchanged. After deployment:

1. GET `/health/live` should report version `0.5.0`; `/health/ready` should return ready.
2. An unauthenticated private request must still return 401. Sign in normally and verify the existing incident and notes views.
3. Check normal collector acknowledgements and source contact when genuine lab activity exists. Do not create repeat attack tests or replace credentials merely for this rollout.

Rate bursts, saturation, timeout and queue-retention checks run locally against synthetic fixtures. Do not flood the hosted API to test throttling. No live load test is part of this change.

Implementation follows [Starlette's ASGI middleware model and CORS handling](https://www.starlette.dev/middleware/). Render terminates inbound TLS at its load balancer as described in its [web service documentation](https://render.com/docs/web-services); this change introduces no HTTPS-redirect middleware or forwarded-IP trust configuration.
