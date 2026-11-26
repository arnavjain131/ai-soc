# Similar earlier incidents

API 0.13.0 adds read-only historical-case retrieval to the private incident AI panel. It uses existing tables and does not change detection thresholds, credentials or collector state.

## Matching and navigation

The panel lists up to three earlier-created incidents from the current workspace sharing at least one alert rule key. The window is the 180 days before the current incident's creation time, rather than the current date or the underlying event timestamps. The current incident, equal-time/later-created incidents, other workspaces and unrelated detection rules are excluded.

Cases rank by the number of distinct shared rule keys, then newest creation time, then incident ID. All incident and alert joins enforce workspace scope. The list displays the shared rules, stored priority, creation time and current disposition so an analyst can assess the match. Opening an earlier case uses the existing authorized incident endpoint and never invokes AI. An empty list means no matching case in this bounded query, not that no historical incidents exist.

A match is a structural rule match. It does not establish the same account, host, attacker, campaign or cause. A stored closed/false-positive disposition is not proof of a verified remediation or investigation outcome. Synthetic lab and real telemetry incidents can match the same rule; the analyst must inspect the original case rather than infer provenance from the match.

## AI input and citations

At most the first two matched cases are supplied to a new, explicitly requested AI generation. The historical context allowlist contains case ID, creation time, normalized disposition/severity, stored risk score and shared rule keys. Historical titles, usernames, addresses, analyst notes, raw events and previous AI text are not included. Arbitrary identifiers typed into a question still follow the existing question privacy warning and cannot all be recognized automatically.

Historical comparisons have a separate `historical_observations` answer field with case IDs constrained to the supplied metadata. Current-event observations retain their own event-ID citations; a case ID cannot be used as event evidence. Retrieved investigation procedures remain in the existing reference namespace. The provider schema requires the historical field (empty when irrelevant or no cases exist), while the server and frontend remain compatible with older saved answers that lack it. The server independently rejects out-of-context case citations with a sanitized error category.

Answers save their exact historical metadata snapshot. Changes to the selected case set, disposition, priority or matching rules change the context fingerprint and can mark an answer outdated. Reading status, opening a case, refreshing or reopening an answer does not regenerate anything. Existing daily/monthly quotas and request UUID recovery apply unchanged. Historical comparisons cannot mutate either incident.

## Reports and validation

HTML/JSON reports preserve historical metadata and comparisons belonging to the saved main summary, including the caveat that these are metadata rather than prior-case evidence. The HTML text is escaped. A report's current fingerprint is computed from the same bounded retrieval as interactive analysis, within its existing read-only repeatable snapshot. Export makes no model call.

Tests cover workspace isolation (including inconsistent alert links), exact time-window bounds, ranking, result/input bounds, provider privacy filtering, citation namespaces, cache freshness, disabled AI, saved metadata preservation and escaped exports. A separate opt-in PostgreSQL test verifies the grouped SQL query on the disposable loopback test database. No hosted incidents are created or changed for validation.

This feature is not semantic/vector search or unrestricted conversation memory. No schema migration, embedding API or new account is required. Deploy the backend before the frontend. First live provider acceptance should be a deliberate question using the existing allowance, rather than automatic regeneration of saved answers.
