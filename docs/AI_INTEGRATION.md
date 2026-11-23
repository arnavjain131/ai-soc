# AI integration checkpoint

The owner requested real AI integration after administrator access management. This supersedes the earlier deferral. The existing deterministic `explanation.py` / IncidentExplanation drafts are still unused and unpublished; they are not an LLM feature.

As of 24 November, the OpenAI adapter, workspace-authorized analysis endpoints, persisted quotas/retry/cache handling and private incident panel are implemented. AI remains disabled by default and no real model call has been made. The owner must finish provider account/billing/key setup and a controlled inference acceptance. Follow `OPENAI_SETUP.md` for the concrete activation steps; no secret belongs in chat or the frontend.

## Completed offline groundwork

`app.ai_grounding` now prepares a bounded incident context and validates a structured answer. It contains no HTTP request, provider key, inference client, route, database mutation or command execution.

- The future route must authorize and fetch the requested incident before calling the context builder. Authorization is not delegated to a model or to this pure helper.
- Up to 50 linked events and 20 related events are selected; long incidents preserve both ends, with omitted-event counts. Event IDs/timestamps/types, destination ports, protocol and numeric sensor fields remain available for citations and interpretation. Related records are explicitly labeled contextual matches.
- Account names and IP addresses become request-local aliases that preserve grouping. Incident titles, note bodies, raw payloads, sensor signature text and free-form rule explanations are excluded. This reduces data exposure; it does not make context anonymous or prove all remaining fields non-sensitive.
- Server-approved rule IDs select versioned investigation guidance with explicit reference IDs and authoritative source links. Unknown rules use a generic AISOC review procedure. This is curated rule-based reference retrieval, not a deployed embedding/vector search or historical-case retriever.
- Context is limited to 64 KiB. A response must follow an explicit schema, stay within 16 KiB, cite only supplied event IDs and use only retrieved reference IDs for investigation steps. Extra fields such as execution commands are rejected. Schema/citation validation checks references and structure; it cannot prove that every free-text claim is logically supported.
- Instructions separate facts, hypotheses and uncertainty, treat context as data, preserve the stored rule-based risk score, and disallow autonomous actions. The eventual model will have no tool execution capability. Model text will need analyst review and safe text rendering.

Six synthetic tests cover identity/raw-text exclusion, preserved grouping, bounded selection/truncation, related-context labeling, missing evidence, unknown rules, fabricated references and schema constraints. These tests do not call a model or establish model quality.

## Model-connected slice and remaining acceptance

1. Selected: OpenAI Responses API and pinned GPT-5.4 mini. Owner account/project setup, spending limit, private key entry and data-handling review remain required. No paid account creation/purchase or inference was performed by the agent.
2. Implemented: bounded structured adapter with no tools, redirects or automatic retries, store=false, finite network timeouts and sanitized provider failures. There is no fabricated AI fallback.
3. Implemented: authorized on-demand GET/POST analysis endpoints and existing-audit persistence of reservations, failures, answers, redacted context and provenance. Durable per-workspace quotas include failed/uncertain attempts; cache receipts retain request-id semantics. Provider currency controls remain separate.
4. Implemented: private incident panel with evidence/reference links, provider/model/time/knowledge provenance, uncertainty, availability, quotas and sharing notice. No automatic generation on refresh and no public-demo activation.
5. Mocked and synthetic evaluation passes for redaction, prompt-injection text exclusion, missing evidence, invalid citations, provider failures, workspace boundaries, retries and quotas. The panel/cache/citation behavior was exercised in a local browser fixture. Real response quality and hosted billing/provider success still require the deliberate owner-controlled acceptance described in OPENAI_SETUP.md.

The first model-connected milestone is grounded incident interpretation, not autonomous blocking, automatic password resets, online attack generation or automatic incident disposition. Expanded RAG over approved procedures/history and the original project's separate ML requirements remain distinct follow-on deliverables.

## Reference basis

The short procedures are original AISOC analyst guidance informed by primary references, not copied incident evidence or instructions fetched dynamically at inference time:

- [MITRE ATT&CK T1110.001 Password Guessing](https://attack.mitre.org/techniques/T1110/001/)
- [MITRE ATT&CK T1110.003 Password Spraying](https://attack.mitre.org/techniques/T1110/003/)
- [MITRE ATT&CK T1046 Network Service Discovery](https://attack.mitre.org/techniques/T1046/)
- [Suricata EVE JSON output](https://docs.suricata.io/en/latest/output/eve/eve-json-output.html)

Knowledge version `2026-11-24.1` identifies this reviewed reference set. These references describe possible behaviors and sensor fields; matching a technique or rule does not establish an adversary, compromise or intent.
