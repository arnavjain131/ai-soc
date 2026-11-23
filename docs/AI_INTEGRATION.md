# AI integration checkpoint

The owner requested real AI integration after administrator access management. This supersedes the earlier deferral. The existing deterministic `explanation.py` / IncidentExplanation drafts are still unused and unpublished; they are not an LLM feature.

## Completed offline groundwork

`app.ai_grounding` now prepares a bounded incident context and validates a structured answer. It contains no HTTP request, provider key, inference client, route, database mutation or command execution.

- The future route must authorize and fetch the requested incident before calling the context builder. Authorization is not delegated to a model or to this pure helper.
- Up to 50 linked events and 20 related events are selected; long incidents preserve both ends, with omitted-event counts. Event IDs/timestamps/types, destination ports, protocol and numeric sensor fields remain available for citations and interpretation. Related records are explicitly labeled contextual matches.
- Account names and IP addresses become request-local aliases that preserve grouping. Incident titles, note bodies, raw payloads, sensor signature text and free-form rule explanations are excluded. This reduces data exposure; it does not make context anonymous or prove all remaining fields non-sensitive.
- Server-approved rule IDs select versioned investigation guidance with explicit reference IDs and authoritative source links. Unknown rules use a generic AISOC review procedure. This is curated rule-based reference retrieval, not a deployed embedding/vector search or historical-case retriever.
- Context is limited to 64 KiB. A response must follow an explicit schema, stay within 16 KiB, cite only supplied event IDs and use only retrieved reference IDs for investigation steps. Extra fields such as execution commands are rejected. Schema/citation validation checks references and structure; it cannot prove that every free-text claim is logically supported.
- Instructions separate facts, hypotheses and uncertainty, treat context as data, preserve the stored rule-based risk score, and disallow autonomous actions. The eventual model will have no tool execution capability. Model text will need analyst review and safe text rendering.

Six synthetic tests cover identity/raw-text exclusion, preserved grouping, bounded selection/truncation, related-context labeling, missing evidence, unknown rules, fabricated references and schema constraints. These tests do not call a model or establish model quality.

## Next implementation slice, awaiting provider setup

1. Choose hosted API or local inference, account/model access and an explicit budget. No key should be sent through chat. Store a cloud key only in private backend configuration/Render secrets; never Vite variables or Git. Local inference needs an authorized reachable service; the hosted Render backend cannot reach the owner's localhost directly.
2. Implement the selected provider against its current official API, with bounded context/output, finite timeout and sanitized failures. No silent provider changes or fabricated AI fallback.
3. Add an on-demand, workspace-authorized analysis endpoint and record request/provenance/answer history using a reviewed persistence design. Durable per-workspace reservations/quotas must include failed calls where spending is uncertain. Application request counts/token bounds are not a guaranteed currency billing cap; provider billing controls and usage monitoring also matter.
4. Add the private incident AI panel with evidence links, approved reference links, provenance, provider/model identity, analysis timestamp, uncertainty and explicit loading/unavailable states. The button should explain which selected data is sent to the chosen provider. Do not call inference on every refresh or enable it in the public demo by default.
5. Evaluate real model responses using synthetic fixtures first: unsupported compromise claims, prompt-injection attempts, missing/contradictory evidence, incorrect citations, provider failure, cross-workspace requests and quotas. Then conduct a deliberate hosted lab-incident analysis after configuration and data-handling choices are settled.

The first model-connected milestone is grounded incident interpretation, not autonomous blocking, automatic password resets, online attack generation or automatic incident disposition. Expanded RAG over approved procedures/history and the original project's separate ML requirements remain distinct follow-on deliverables.

## Reference basis

The short procedures are original AISOC analyst guidance informed by primary references, not copied incident evidence or instructions fetched dynamically at inference time:

- [MITRE ATT&CK T1110.001 Password Guessing](https://attack.mitre.org/techniques/T1110/001/)
- [MITRE ATT&CK T1110.003 Password Spraying](https://attack.mitre.org/techniques/T1110/003/)
- [MITRE ATT&CK T1046 Network Service Discovery](https://attack.mitre.org/techniques/T1046/)
- [Suricata EVE JSON output](https://docs.suricata.io/en/latest/output/eve/eve-json-output.html)

Knowledge version `2026-11-24.1` identifies this reviewed reference set. These references describe possible behaviors and sensor fields; matching a technique or rule does not establish an adversary, compromise or intent.
