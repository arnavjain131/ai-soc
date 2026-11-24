# Enable AISOC incident AI with OpenAI

The implementation uses the OpenAI Responses API with a pinned `gpt-5.4-mini-2026-03-17` model, structured output, no tools, no automatic retries and `store:false`. It is disabled by default. This is on-demand incident interpretation using selected evidence and curated investigation references, not autonomous response or full historical/vector-search RAG.

## Owner setup: account, spending and private key

1. Open the [API platform](https://platform.openai.com/) and sign in or create your own account. Complete any account agreement/verification yourself. Create a project named **AISOC**. No organization administrator credential is needed by this app.
2. Review your available API credits and billing access. Some eligible subscriptions can have API-credit benefits; do not assume a ChatGPT login alone funds API requests. If purchasing prepaid credits, choose an amount you approve; the current documented minimum is $5. Keep auto-reload disabled for the initial lab unless you deliberately choose it. Payment and credit purchases are owner actions, not performed by this integration. [Prepaid billing](https://help.openai.com/en/articles/8264644-what-is-prepaid-billing)
3. In project Limits, choose an explicit monthly spending amount you approve and enable **Enforce a hard limit**, with alerts below it. Alerts alone do not stop traffic; even hard-limit enforcement can lag slightly. These controls are separate from AISOC's request quotas. [Spend controls](https://developers.openai.com/api/docs/guides/spend-limits)
4. Create a project API key named **AISOC Render**. Where restricted permissions are offered, permit only the Responses creation operation this backend requires. Save the key privately. Never send it in chat, paste it into Vite/frontend variables, commit it or display it in a screenshot. You can revoke this key from the provider dashboard if necessary.

The [OpenAI Developers plugin](https://developers.openai.com/) is an optional documentation aid for further development; it does not replace this project's provider account, private key or usage controls.

## Render configuration

After deploying the reviewed backend commit, add the following to the **existing ai-soc-api** service's private environment settings. Leave all database, Supabase, origin, source and collector settings intact.

```text
SOC_AI_ENABLED=false
OPENAI_API_KEY=<enter privately in Render>
SOC_AI_MODEL=gpt-5.4-mini-2026-03-17
SOC_AI_DAILY_LIMIT=3
SOC_AI_MONTHLY_LIMIT=30
SOC_AI_MAX_OUTPUT_TOKENS=2000
```

Save the key only in Render. `SOC_AI_ENABLED=false` prevents inference even when a key is present. Once billing controls, intended data sharing and the chosen test incident are reviewed, the owner can set `SOC_AI_ENABLED=true` and save/redeploy. The app refuses startup if enabled with no key, unsupported model or invalid limits. No database migration or frontend API key is required. For deliberate local development, the optional equivalent is the ignored `backend/.env`; automated tests force synthetic/offline settings.

## What the model sees and stores

Only an authorized incident's selected context is sent. Up to 50 linked and 20 related events include timestamps, event UUIDs/types, destination ports, protocol, numeric sensor fields, stored rule priority and selected versioned investigation references. Account names/IPs become request-local aliases. Raw event payloads, incident titles, note bodies, free-text sensor signatures and source credentials are excluded. Aliasing reduces identity exposure but does not make context anonymous. The private AI panel explains this before its generate button.

The adapter contacts only `https://api.openai.com/v1/responses`, refuses redirects, sends no tools, bounds input/output, and rejects incomplete, refused, oversized or invalidly cited answers. API data is not used for training by default. `store:false` avoids default Responses state storage; separate abuse-monitoring retention can still apply, normally up to 30 days depending on account controls. Review provider policy for real organizational use. [Data controls](https://developers.openai.com/api/docs/guides/your-data)

Successful analyses and redacted context/provenance are stored in existing workspace-scoped audit storage. Failed/pending attempts are also recorded with safe status codes. No raw provider error or key is logged. All members authorized for the incident can view its saved analysis. A model's text remains fallible: valid citation IDs do not prove every statement follows from the evidence. Analysts must review the original timeline.

## Cost, retries and caching

- Limits default to **3 generation attempts per UTC day and 30 per UTC month per workspace**. These persist across backend restarts through audit reservations and shared workspace-row locking. Different workspaces have separate budgets, so total provider spending can grow if the owner creates more workspaces.
- A request UUID reserves quota before contacting OpenAI. Repeating that request never starts a second model call. A completed identical context/model/prompt/schema is reused; a cache-hit receipt preserves its retry semantics without spending another generation allowance.
- Failed or uncertain attempts still count, including authentication errors, provider quota failures, connection failures and interrupted requests. A successful provider request whose database save fails can incur cost without a saved result. The reservation remains, and the same request is not automatically regenerated.
- Only one unfinished analysis reservation can be started per workspace within the 90-second pending window. A stale reservation remains charged against quota. Saved analyses remain readable if inference is disabled or quota is exhausted.
- The transport has finite connect/read timeouts and checks an overall deadline between incoming chunks; it does not stream model text to the browser. The frontend allows up to 65 seconds and preserves a failed request's ID. After an interrupted/server/pending response it automatically checks the original request receipt through bounded GET-only polling, displays its saved result/quota and clears the pending state. These reads never invoke the provider. If connectivity stays unavailable, the same-ID retry remains available. Starting a new request is explicit and may consume another quota unit.
- Output is capped at 2,000 tokens by default; input context at 64 KiB. Request counts are not currency billing caps. Check the model's [current pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini) and provider usage dashboard. No paid inference has been run during implementation.

## First controlled test, after activation

1. Sign in to the hosted private workspace and open an existing lab incident. Do not generate more attacks merely for this test.
2. Review the panel's provider/model, transmitted-data notice and remaining quota. Select **Analyze incident** once.
3. Verify that the returned summary, observations, interpretation, suggested investigation, evidence links, references, model/time and limitations display correctly. A fabricated citation, provider refusal or truncated response should produce an error rather than an accepted analysis.
4. Confirm the stored incident's status, risk score, evidence and collectors are unchanged. Refresh saved analysis and confirm it persists. Clicking Analyze again for identical evidence should report reuse, with no new model call.
5. Report success or a sanitized error code. Do not share the key, browser storage, raw response or private credentials. A real model's output and spending still need this owner-controlled acceptance; mocked tests are not that verification.

The AI is advisory. It cannot block IPs, run shell commands, reset passwords, revoke access, change a disposition, generate lab traffic or call external tools. Existing detections and evidence remain operational when the AI is disabled or unavailable.

API endpoints: authorized `GET` and `POST /api/incidents/{incident_id}/ai-analysis`; POST accepts only a UUID `request_id`. GET optionally accepts that UUID as a query parameter for the requesting actor's read-only receipt, including an allowlisted failure code. Strict provider schemas restrict citation fields to the selected incident's event/reference IDs; application validation still independently rejects invalid citations and structure. Prompt version 2 and context-specific schemas are included in cache fingerprints. Old analyses remain readable but can become outdated; no automatic regeneration occurs. Terminal failures use GET-only status checks in the panel; a fresh generation always needs an explicit new attempt. API version is 0.7.2.
