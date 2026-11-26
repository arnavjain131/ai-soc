# Approved investigation knowledge retrieval

API 0.12.0 adds a small, versioned knowledge library for the existing incident AI assistant. It ranks approved procedure sections locally and supplies selected excerpts with the incident's authorized evidence. This is lexical retrieval, not embedding/vector search, machine-learning detection or live web browsing.

## Included knowledge

`backend/app/knowledge/approved.json` contains four AISOC-authored procedures and nine reviewed sections covering authentication patterns, successful-access checks, account authorization, port scans, service verification, Suricata flow/alert interpretation, priority and evidence gaps. Supporting primary sources were checked on 26 November 2026:

- MITRE ATT&CK password guessing: https://attack.mitre.org/techniques/T1110/001/
- MITRE ATT&CK network service discovery: https://attack.mitre.org/techniques/T1046/
- Suricata 7.0.3 EVE documentation: https://docs.suricata.io/en/suricata-7.0.3/output/eve/eve-json-output.html

The procedure text is local AISOC guidance. Supporting source links are not claims that the source contains AISOC-specific rules, thresholds, interface behavior or recommendations verbatim. Procedure text describes what an analyst may review; it is never evidence that activity occurred.

## Retrieval and provenance

Detection rule keys first determine eligible documents; shared analyst review procedures are eligible for any rule. Unique lowercase question terms are compared with section keywords and titles. Overlap ranks relevant sections, stable section IDs break ties, and unmatched questions add no unrelated sections. A summary uses a deterministic default ranking. The original rule reference remains, with at most three additional sections and four total references. Existing input/output size and evidence bounds remain in force.

Each section carries its local document ID, title, version, stable citation ID and SHA-256 content fingerprint. The corpus version includes a hash of its validated full contents. The AI response schema and validator permit only references actually selected for that request. Retrieved procedures cannot be used as event IDs. The frontend displays supporting-source links and expandable retrieved text with provenance for newly generated answers.

The library is loaded only from one repository-owned path. No upload, arbitrary file/URL ingestion, workspace-note indexing or runtime web fetch is supported. It is limited to 64 KiB, 16 documents, 64 sections and 1,200 characters of guidance per section. Duplicate IDs, invalid schema and unapproved source URLs are rejected. Missing or invalid knowledge prevents a new provider call before quota is reserved; saved AI results remain readable.

## Existing answers and cost

The new corpus and prompt version change context fingerprints. Earlier answers remain intact, readable and marked outdated. A status refresh or opening a saved answer does not regenerate it. Each explicit new generation still shares the existing daily/monthly allowance; failures count as before. Identical questions with unchanged evidence and knowledge reuse saved results. Stored-question freshness is calculated by rerunning retrieval for that exact stored question, rather than comparing it against the summary's reference selection.

No database migration, vector extension, embedding provider, extra key, quota change or collector configuration change is required. API 0.13.0 adds separate workspace-scoped historical metadata retrieval; see `AI_HISTORY.md`. A trained detector remains a separate milestone. The assistant must acknowledge missing evidence and human approval is required for any response action.

## Updating knowledge

Review changes to the approved JSON as code. Keep guidance concise, distinguish general advice from observed facts, retain stable IDs and increment the corpus/document versions when content changes. Check supporting primary sources. Run the knowledge, grounding, provider, request-recovery and report tests before deploying. Deploy the backend first, then the frontend. Existing summaries and saved questions must remain available; do not regenerate them automatically to test the release.
