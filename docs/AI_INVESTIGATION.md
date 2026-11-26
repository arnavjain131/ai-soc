# Incident investigation questions

API 0.11.0 extends the existing authorized AI analysis flow with incident-specific questions. No schema migration, new key, provider setting, quota change or collector update is required.

## Analyst workflow

Open a private incident and find **AI incident analysis → Ask about this incident**. Choose a starter question or enter a question of 3–500 characters. Submitting is explicit and uses the same workspace generation allowance as summaries (including failed attempts). Merely selecting a starter does not generate anything.

The answer appears with linked evidence, approved investigation references and limitations. **Saved questions** shows the most recent 20 completed answers. Opening saved answers and refreshing status make no model call. The main summary remains separate, and incident reports continue to include only the main summary.

Each question is independent and uses the current authorized incident context. Earlier conversation turns are not sent. API 0.13.0 additionally retrieves up to two earlier-case metadata summaries from the same workspace; see `AI_HISTORY.md` for matching, privacy and citation limits. Uploaded-document retrieval and live external searches are not implemented. Answers cannot execute actions or change incident disposition.

## Data and access

The existing `POST /api/incidents/{incident_id}/ai-analysis` accepts an optional `question` alongside `request_id`. Existing summary requests remain compatible. `GET` returns `latest` for the summary and `questions` for saved answers; exact actor request receipts support read-only recovery for both.

Questions are sent in the provider input as untrusted data. Known usernames and IPs from selected incident evidence are replaced with the same account/host aliases as the evidence. Other identifiers or secrets in arbitrary prose cannot reliably be recognized or removed. The form explains that questions go to OpenAI and are saved for authorized workspace members; analysts must not include secrets. Only the transformed question is stored in AI audit context. No question is placed in a URL.

Cache fingerprints include the question, evidence, references, model, instructions and schema. Different questions cannot reuse unrelated answers. Repeating an identical question with unchanged context reuses the saved answer without another debit. Changing the question or evidence while reusing a request UUID returns a conflict. Lost-response checks retain the original UUID and question; they do not automatically generate or retry inference. Membership is checked before access and again before delivering newly generated output.

Existing bounded context, citation validation, provider timeout, no-tools configuration, output limits and daily/monthly quotas continue to apply. These checks restrict format and citation provenance; they cannot guarantee that model interpretation is correct. Analyst review remains required.

## Release and verification

Deploy the backend before the frontend. Do not change environment variables or run migrations. Existing saved summaries remain readable and retain their original cache fingerprints.

Local tests use mocked provider output without paid API calls. After deployment, open an existing incident, ask one question explicitly, verify that the answer cites that incident's evidence, and reload the incident. The saved question should reopen without another generation. Check that the normal summary and exported report still show the main incident summary. A new uncached question consumes one attempt from the existing allowance.
