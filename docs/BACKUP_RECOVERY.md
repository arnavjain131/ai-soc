# Application backup and isolated recovery

This workflow protects the nine application tables in Supabase PostgreSQL. It is a local maintenance command, not a website endpoint. It does not change the hosted API or collectors.

## Scope and current verification

The archive contains native PostgreSQL custom-format definitions/data for `public.soc_workspaces`, `soc_memberships`, `soc_sources`, `soc_events`, `soc_incidents`, `soc_alerts`, `soc_alert_events`, `soc_audit_logs` and `soc_schema_migrations`. It includes stored source-token hashes and membership identifiers, so treat it as private. It does not contain plaintext collector tokens unless somebody manually put credentials in their own event/note text.

Supabase Auth users, Storage files, project settings, database roles/ACL ownership, local environment files, Ubuntu credentials and collector queues/checkpoints are outside this backup. Keep provider recovery and VM/credential recovery as separate procedures. A nine-table application backup is not a full Supabase project backup.

The tool uses `pg_dump` and an exported repeatable-read snapshot so the manifest counts and dump share one database view. Dump bytes are packaged and encrypted in memory with AES-256-GCM and an Argon2id-derived passphrase key (16-byte random salt, 12-byte random nonce, 64 MiB KDF memory, three passes, four lanes). Plaintext dump files are not written by this tool. Version 1 supports archives up to 64 MiB and rejects larger source relations before capture. Use a reviewed streaming workflow when the project outgrows this limit.

As of 23 November, encryption/packaging and restore guards have automated coverage; the live read-only inventory passed. PostgreSQL clients are not yet installed, so no native production archive has been created and no real restore drill has passed. Mocked restore tests and archive inspection are not substitutes for that drill.

## Local prerequisites

1. Install **PostgreSQL 17 Command Line Tools** using the [official Windows distribution](https://www.postgresql.org/download/windows/). The source server was verified as 17.11. A 17.x client of the same major version is required by this workflow. For the first backup, select only the Command Line Tools component; a local database service is unnecessary.
2. The tool searches PATH and `C:\Program Files\PostgreSQL\17\bin`. For another location, set `SOC_PG_BIN` to its `bin` directory. This value is a path, not a credential.
3. From the existing backend directory, install optional maintenance dependencies if needed:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-maintenance.txt
   .\.venv\Scripts\python.exe -m app.backup check
   ```

The configured backend `.env` already supplies the source connection. Do not recreate it, print it, rerun migration 001 or re-provision membership. Native database passwords are supplied only in a child process environment, never through command-line arguments. Child stderr is not printed because it can contain connection details.

## Create and verify an encrypted backup

Run in your own interactive Windows PowerShell, from the backend directory:

```powershell
.\.venv\Scripts\python.exe -m app.backup create
```

Enter and confirm a strong, unique backup passphrase of at least 16 characters at the hidden local prompts. This is not the database password. The tool does not accept it through arguments or environment variables and refuses a noninteractive fallback prompt. Save the passphrase separately in your password manager; losing it makes that archive unrecoverable. Never send it in chat.

The encrypted `.aisocbak` file is saved under `%LOCALAPPDATA%\AI-SOC\backups`, outside the project's OneDrive directory. The tool restricts that directory to the current Windows user and SYSTEM. It uses exclusive creation and does not overwrite existing files. Archives and native dumps are ignored by Git. No cloud upload, scheduled job or automatic retention deletion is configured.

Use the exact printed filename to verify:

```powershell
.\.venv\Scripts\python.exe -m app.backup verify "C:\Users\DELL\AppData\Local\AI-SOC\backups\YOUR-PRINTED-FILENAME.aisocbak"
```

Verification authenticates/decrypts the package, checks its SHA-256 dump checksum, and uses `pg_restore --list` to check all nine expected table/data sections. Only manifest metadata/counts are printed. This command does not contact a restore target or write plaintext data. Keep an encrypted copy on a separately protected device once verified; a copy on the same disk alone does not cover disk failure. Any transfer is a deliberate owner action, not performed by this tool.

## Restore drill: empty, disposable local database only

This step needs a separate local PostgreSQL server and an explicitly prepared empty database such as `ai_soc_restore_test`. Installing client tools alone does not supply that running server. Arrange this target separately; do not create a new paid cloud project merely for this test.

Create `backend/.env.restore` from `restore.env.example` only if missing, then edit its target credentials privately. `.env.restore` is ignored by Git. Leave the source `.env` unchanged. The target must use a literal loopback IP (`127.0.0.1` or `::1`), a database named `ai_soc_restore_*`, no URL options, and an explicit matching confirmation name. The server must itself report a loopback address and must not be older than the source major version. Existing non-system relations/functions cause refusal. Review your local endpoint and any forwarding before using it.

```powershell
.\.venv\Scripts\python.exe -m app.backup restore-check "C:\Users\DELL\AppData\Local\AI-SOC\backups\YOUR-PRINTED-FILENAME.aisocbak" --confirm-database ai_soc_restore_test
```

The drill performs a single-transaction, exit-on-error restore without `--clean`, `--create`, owner restoration or privilege restoration. It never drops a target or deletes existing objects. It compares row counts/schema version and checks RLS is enabled on the restored application tables. PostgreSQL also creates/validates the archived constraints during restoration. The isolated database is retained for review; there is no automatic cleanup or production promotion.

Production disaster recovery requires a separate reviewed plan covering Supabase Auth identities, project settings, credentials, storage, original grants/browser-role restrictions and application validation. This local command intentionally cannot restore to the hosted Supabase endpoint. Do not run the initial migration over restored tables.

## Source references

- [PostgreSQL 17 pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html): consistent native backups, custom format and exported snapshots.
- [PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html): archive inspection, single-transaction restore and owner/ACL options.
- [Cryptography authenticated encryption](https://cryptography.io/en/latest/hazmat/primitives/aead/): AES-GCM integrity/confidentiality and nonce requirements.
- [Cryptography Argon2id](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/): password-based key derivation.
