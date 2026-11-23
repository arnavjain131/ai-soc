# Account recovery and analyst onboarding

The public demo remains available without registration. Private access requires both a Supabase Auth account and an administrator-provisioned membership. Password recovery changes the user's password; it never grants, moves or promotes a membership.

## Hosted setup required before the first recovery test

In the existing Supabase project, open Authentication's URL Configuration:

- Review the Site URL: `https://ai-soc-frontend-gamma.vercel.app`.
- Add this exact Redirect URL: `https://ai-soc-frontend-gamma.vercel.app/auth/recovery`.
- For deliberate local tests only, add `http://127.0.0.1:5173/auth/recovery` and/or `http://localhost:5173/auth/recovery` for the actual origin used. Request and consume the link on the same origin.
- Keep public sign-up disabled. Do not add broad wildcard redirects or replace unrelated, already-approved callback URLs.

Review the Reset Password email template. The standard Supabase `{{ .ConfirmationURL }}` link should remain intact; custom templates must preserve the recovery flow and redirect. Do not hardcode tokens or substitute an implicit-token flow. The dedicated callback accepts a PKCE recovery code, not invitation links, OAuth callbacks or access-token fragments.

Email delivery is an external prerequisite. Supabase's default SMTP service is intended for testing, is rate-limited (currently two messages/hour), and only sends to addresses in the project's organization team. Do not add analysts to the Supabase organization merely to bypass this restriction: organization access and SOC membership are different privileges. Configure a supported custom SMTP provider for delivery to additional analysts, enter SMTP credentials only in Supabase, and verify the sender/domain with that provider. No SMTP account, paid plan, domain purchase, email dispatch or provider-setting change was performed by this implementation. [Supabase SMTP documentation](https://supabase.com/docs/guides/auth/auth-smtp)

The callback path is handled by the existing Vercel SPA rewrite. Frontend changes publish through the existing repository integration. No Render API deployment, migration, service-role browser key or new frontend environment variable is needed. Backend API version remains 0.5.0; the owner CLI changes run from the owner's local updated checkout.

## Existing analyst: recover a password

1. Open the hosted website, choose **Analyst sign in**, then **Forgot your password?**.
2. Enter the existing account email and request recovery once. The screen avoids disclosing account existence and offers a 60-second UI cooldown; Supabase enforces its own server-side Auth/email limits. The Render request limiter does not protect direct Supabase Auth calls.
3. Open the newest recovery link in the same browser, browser profile and site origin used to request it. PKCE needs its locally stored verifier. Email-app webviews, private browsing, cleared storage and another device/browser may prevent exchange. Request a fresh link in the intended browser if necessary.
4. The dedicated recovery screen exchanges the code once per page, including React StrictMode's effect replay. Query/fragment parameters are removed from the address bar before rendering. No raw provider error, code, access token, refresh token or password is rendered/logged by the application. Referrer policy is `no-referrer`. The code is a one-time PKCE authorization code; this does not claim browser/network infrastructure never receives the initial callback URL.
5. Choose and confirm a unique 12–128 character password. Supabase's project password policy remains authoritative and may be stricter. A pre-existing session alone, expired/used link, implicit token or non-recovery exchange cannot enable this password form. Reloading the scrubbed page requires a new recovery link; it does not silently reuse an old session as recovery proof.
6. After a successful update, the app attempts global sign-out and asks the user to sign in again. A sign-out failure is shown separately from password-update success. Existing access JWTs can remain valid until expiry, so this is not a promise of instantaneous session revocation. [Supabase sign-out behavior](https://supabase.com/docs/reference/javascript/auth-signout)

The recovery page does not mount the private dashboard or fetch its data. Supabase's recovery exchange establishes an Auth session as part of its normal flow; backend membership checks still govern every private request. Do not share recovery links, browser storage, passwords, email screenshots containing links or SMTP credentials in chat.

## Owner: onboard an analyst to the existing workspace

Do not repeat administrator creation or migration 001. Do not recreate Private SOC.

1. Verify the intended analyst and their email through your normal trusted process. Check whether their Auth user already exists in Supabase Authentication → Users; do not create duplicates.
2. If a new account is needed, use the existing Supabase user-management screen to create the approved email user. Keep any owner-generated initial password random and private; do not send it through chat or reuse an administrator password. Complete any required email confirmation/verification using the configured Auth flow. The analyst can then request a recovery link from their own browser to set their own password. This release does not implement acceptance of dashboard-generated invitation links.
3. Copy the UUID from that exact verified Supabase user record. Cross-check it against any account ID supplied by the analyst. From the backend directory, grant the analyst access to the existing workspace:

   ```powershell
   .\.venv\Scripts\python.exe -m app.manage grant-member --user-id VERIFIED_AUTH_USER_UUID --role analyst --workspace-id bd0fc3bb-f387-4aac-9256-44a9bb4bbb7a
   ```

   This is an explicit owner-operated database write; run it only for the approved analyst. No grant was run during implementation/testing. The CLI defaults to analyst and refuses analyst grants without an existing workspace ID. Admin grants still require explicit `--role admin`. Existing memberships cannot be promoted/moved by rerunning the grant command. New successful grants write a `membership.granted` audit record with actor `owner-cli`; this labels the provisioning mechanism, not a verified browser identity. This record is not part of an incident's note/status history. No new audit table or schema migration is involved.

4. The analyst signs in or chooses **Check access again**. An authenticated account without membership sees **Workspace access required**, its own account UUID and administrator instructions. Membership is checked before requesting incident/stat/source data. Expired sessions and service failures display different guidance. A failed membership check clears previously loaded private records from the app state; the public demo remains separate.

This workflow supports one workspace membership per user. It does not add public sign-up, self-selected roles, a browser membership editor, automatic invitation acceptance or an offboarding endpoint. Role changes/revocations need a separately reviewed owner operation.

## Verification status

Recovery callback parsing, one-shot exchange, invalid/non-recovery/expired-code handling, password confirmation, sanitized failures and update/sign-out ordering have automated mocked coverage. Membership tests use synthetic local databases to cover default analyst role, existing-workspace requirements, duplicate-grant refusal and owner-operation audit records. TypeScript and the production build pass. Existing API workspace-boundary tests still pass.

Hosted SMTP settings, allowlisted redirects, real delivery/password changes, non-member browser behavior and signed-in regressions still require controlled owner verification. Do not claim a successful hosted password reset merely because the frontend build or mocked tests passed. Use a dedicated approved test account after SMTP is configured, rather than changing the active administrator's password as an automated test.

References: [PKCE password reset](https://supabase.com/docs/reference/javascript/auth-resetpasswordforemail), [redirect allowlists](https://supabase.com/docs/guides/auth/redirect-urls), [code exchange](https://supabase.com/docs/reference/javascript/auth-exchangecodeforsession).
