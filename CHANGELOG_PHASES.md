# Phase 1 SYNCFIX

## Baseline

- Branch: `phase-1-syncfix`
- Base commit: `506cdb8744bd2b5ede28d8a712df28b77e181bed`
- Commit: this report is included in the commit titled `Phase 1 SYNCFIX`; the resulting hash is reported in chat.

## Files changed

- `.env.example` — documents backend settings, mail providers, Gunicorn, super-admin provisioning, and the isolated test database variable.
- `README.md` — adds local backend/frontend startup steps and warns that backend tests drop and recreate their database schema.
- `ai-calling-frontend/.env.example` — documents live/mock mode and frontend backend URL variables.
- `ai-calling-frontend/README.md` — replaces obsolete mock-switch instructions with `NEXT_PUBLIC_API_MODE`.
- `app/otp_service.py` — defers Resend configuration reads until an OTP send is requested and raises a specific missing-key error.
- `app/otp_routes.py` — maps missing OTP Resend configuration to HTTP 503.
- `app/services/email_service.py` — adds a production-console configuration warning helper.
- `app/main.py` — invokes the warning helper at application startup.
- `ai-calling-frontend/src/features/dashboard/api.ts` — corrects minute-pack and approval response types, validates appointment customer IDs, and adds call-detail fetching.
- `ai-calling-frontend/src/features/dashboard/views-tenant.tsx` — refreshes call details when opened, instead of relying on list fields for recordings/transcripts.

No files were deleted. `ai-calling-frontend/next.config.mjs` was already using `http://127.0.0.1:8000` as its fallback and was left unchanged.

## Database and API

- No migrations, tables, or columns changed.
- No backend route paths were added, removed, or changed. The existing `/auth/send-otp` route now returns HTTP 503 when `RESEND_API_KEY` is missing.
- The frontend now calls the existing `GET /api/v1/calls/{id}` endpoint when a call-detail view is opened.
- Minute-pack and access-approval results are treated as action responses; existing callers reload dashboard data so updated values appear.
- Live appointment creation no longer substitutes customer ID `1`; invalid or missing IDs produce a user-visible validation error.
- Appointment ordering remains unchanged: the backend accepts no sort/order parameter and returns appointments in ascending date/time order, while the dashboard fetches at most 100. Newer appointments can therefore be omitted.

## Configuration and behavior

- The root environment example documents the variables read by backend settings, the super-admin seeder, tests, and Gunicorn. The frontend example documents its public API/mode variables and server-side backend URL.
- Configure a local PostgreSQL `DATABASE_URL`, apply migrations, then start `uvicorn` on port 8000. Resend credentials are not required to import/start the app; requests to the standalone OTP send route need `RESEND_API_KEY`.
- In production, `EMAIL_BACKEND=console` now emits a startup warning and still does not send email. Defaults were not changed.
- Minute-pack results are refreshed after the action; approval refreshes both the access request and business data. Call details display loading/error states, recording links when available, and transcript text from the detail response.
- A valid live appointment requires a positive safe-integer customer ID. Existing mock appointment behavior remains unchanged.

## Verification

- `npm install` in `ai-calling-frontend/` — succeeded. npm reported 6 dependency audit findings (1 moderate, 4 high, 1 critical); dependencies were not updated.
- `npm run build` in `ai-calling-frontend/` — succeeded; Next.js compiled, lint/type checks completed, and static pages generated.
- `git diff --check` — passed.
- Python AST syntax check for the modified backend files — passed.
- `python -m pip install -r requirements.txt` — could not complete: only Python 3.14 is installed, and the pinned `psycopg2-binary` package attempted a source build that requires unavailable `pg_config`.
- `python -c "import app.main"` — not verified successfully; it stopped with `ModuleNotFoundError: No module named 'jose'` after the requirements installation failure. `RESEND_API_KEY` and `MAIL_FROM` were unset, and no root `.env` file was present during the check.
- Backend tests were skipped because `TEST_DATABASE_URL` is unset and no separate empty PostgreSQL test database is configured.

## Manual checks

1. With Python 3.12 and dependencies installed, unset `RESEND_API_KEY` and `MAIL_FROM`, then run `python -c "import app.main"` from the repository root; the app should import. Posting to `/auth/send-otp` without the key should return HTTP 503.
2. Start the backend and frontend using the root `README.md`; sign in with an existing provisioned account.
3. In a tenant with a customer, create an appointment and confirm it appears. In a tenant with no appointment/customer available, submit the new-appointment form and confirm the invalid-customer message is shown rather than sending customer ID `1`.
4. Cancel the appointment, then create or select another active appointment, reschedule it, and confirm both changes after the dashboard refreshes.
5. As a super admin, add a minute pack and confirm the business minutes refresh.
6. As a super admin, approve a pending access request and confirm the request and business status refresh.
7. Open a call's details and confirm the browser requests `GET /api/v1/calls/{id}` and displays the returned transcript/recording when available.

## OTP flow distinction

- The existing database-backed flow is `/api/v1/auth/verify-email/send` and `/api/v1/auth/verify-email/confirm`; it is separate from the new OTP module and remains unchanged.
- The standalone `/auth/send-otp` and `/auth/verify-otp` flow uses a six-digit code, an in-memory hashed-code store, a 10-minute expiry, a 60-second resend cooldown, and a five-attempt limit. Its verification handler still has a TODO instead of marking the user verified in the database, and `OtpStep.tsx` is not wired into signup. It calls Resend directly and does not use `EMAIL_BACKEND`.

# Phase 1.5 CI

## Change report

- Branch: `phase-1-syncfix`
- Base commit: `18280d903eac8d1611875474eddc3b854ab3ce3f`
- Commit: this report is included in the commit titled `Phase 1.5 CI`; its resulting hash is reported in chat.

### Files changed

- `.github/workflows/ci.yml` — adds push and pull-request CI jobs for backend startup, migrations, tests, and frontend production build.
- `CHANGELOG_PHASES.md` — records this CI setup and its verification limits.

No files were deleted or otherwise changed.

### Database and API

- Database changes: none.
- API changes: none.
- The backend workflow uses only a disposable PostgreSQL 16 service database. Both `DATABASE_URL` and `TEST_DATABASE_URL` point to that service; the test fixture is therefore isolated from any developer or production database.

### Workflow environment and behavior

- Backend CI sets `DATABASE_URL` and `TEST_DATABASE_URL` to the disposable service database URL and `JWT_SECRET_KEY` to a dummy test value. `tests/conftest.py` sets `APP_ENV`, rate limiting, and Sarvam webhook test settings itself.
- The startup command explicitly unsets `RESEND_API_KEY` and `MAIL_FROM` before importing the application.
- Frontend CI uses Node 20, `npm ci`, and `npm run build`, with `NEXT_PUBLIC_API_MODE=live`; no API key or GitHub secret is used.
- No GitHub secrets or repository settings need to be configured.
- No application behavior changes; this adds CI verification only.

### Verification

- The workflow YAML and commands were reviewed against `app/core/config.py`, `tests/conftest.py`, and the frontend lockfile.
- The workflow YAML parsed successfully with the existing Node.js YAML parser; both jobs and the trigger were present.
- CI itself has not yet run on GitHub in this session. The backend tests, migration against PostgreSQL, and CI-hosted startup check therefore remain unverified here.
- No application source, dependency manifest, or test file was changed.

# Phase 1.6 TESTFIX

## Change report

- Branch: `phase-1-6-testfix`
- Base commit: `fa88f28a6f772aea28c86a282a2bc3bc05d078f1`
- Commit: this report is included in the commit titled `Phase 1.6 TESTFIX`; its resulting hash is reported in chat.

### The 16 CI failures

| # | Test | Root cause | Changed side | File(s) changed |
|---|---|---|---|---|
| 1 | `test_admin_businesses_listing_and_pin_isolation` | `PinService` lacked the encryption method used to set up a PIN. | App code | `app/services/pin_service.py` |
| 2 | `test_admin_minute_pack_and_pin_operations` | PIN reset called a missing encrypt method and PIN view called a missing decrypt method. | App code | `app/services/pin_service.py` |
| 3 | `test_get_plans_public` | Per-test cleanup removed the global catalog and no fixture reseeded it. | Test fixture | `tests/conftest.py`, `tests/helpers.py` |
| 4 | `test_approve_and_decline_access_flow` | The approval flow requires the missing Growth plan row. | Test fixture | `tests/conftest.py`, `tests/helpers.py` |
| 5 | `test_manual_submit_payment_success` | Manual payment setup requires the missing plan catalog. | Test fixture | `tests/conftest.py`, `tests/helpers.py` |
| 6 | `test_manual_submit_payment_amount_mismatch_and_validations` | Plan rows were absent, and ordinary `AppError` responses use `error_code`, not `code`. | Test fixture and test | `tests/conftest.py`, `tests/helpers.py`, `tests/test_b3_features.py` |
| 7 | `test_onboarding_status_lifecycle_and_tenant_isolation` | The onboarding payment path requires the missing plan row. | Test fixture | `tests/conftest.py`, `tests/helpers.py` |
| 8 | `test_billing_me_success_and_alerts` | The test inserted calls without the model's required `phone_number`; valid webhook schema requires it. | Test | `tests/test_b2_features.py` |
| 9 | `test_billing_me_tenant_isolation` | The test inserted a call without the required `phone_number`; valid webhook schema requires it. | Test | `tests/test_b2_features.py` |
| 10 | `test_patch_business_rbac` | Test passed a display label instead of `client_staff` and treated the created-user response as login tokens. | Test | `tests/test_b2_features.py` |
| 11 | `test_manual_submit_payment_auth_and_roles` | Test read tokens from the created-user response and expected `code` instead of `error_code`. | Test | `tests/test_b3_features.py` |
| 12 | `test_get_business_bundle` | New-client default timezone was configured as UTC despite the expected Asia/Kolkata default. | App code | `app/core/config.py`, `.env.example` |
| 13 | `test_patch_business_atomic_replacement_and_audit_log` | The business audit details did not include `updated_fields`. | App code | `app/services/business_service.py` |
| 14 | `test_every_table_has_client_id` | The global `plans` catalog was incorrectly checked as tenant-owned data. | Test | `tests/test_multi_tenant_security.py` |
| 15 | `test_tenant_tables_have_client_id_index_or_fk` | The global `plans` catalog was incorrectly checked for a tenant FK. | Test | `tests/test_multi_tenant_security.py` |
| 16 | `test_every_api_route_requires_authentication_unless_allowlisted` | Logout intentionally revokes a refresh token from its body and does not require an access token. | Test | `tests/test_multi_tenant_security.py` |

### Files changed

- `app/services/pin_service.py` — adds `PinService.encrypt_pin` and `decrypt_pin`, using the existing Fernet scheme and configured key path.
- `app/core/config.py` — changes the default timezone for newly provisioned businesses to Asia/Kolkata.
- `.env.example` — aligns the documented `DEFAULT_TIMEZONE` with the application default.
- `app/services/business_service.py` — adds ordered `updated_fields` to audit details while retaining the existing `updated` key; lists only values that actually differ.
- `tests/helpers.py` — adds a shared idempotent plan-catalog seed helper with migration-equivalent values.
- `tests/conftest.py` — seeds the four global plans before each test and after cleanup truncates the test data.
- `tests/test_b2_features.py` — fixes the staff role/token assumptions, adds required call phone numbers, and updates timezone expectations.
- `tests/test_b3_features.py` — logs the created staff user in and checks the standard `error_code` field for ordinary API errors.
- `tests/test_calls.py` — updates the date-filter test to cover the new Asia/Kolkata default and a UTC override.
- `tests/test_multi_tenant_security.py` — excludes only the global plans catalog from tenant-table guards and allowlists unauthenticated logout.
- `CHANGELOG_PHASES.md` — records this phase and its diagnosis.

No files were created or deleted. No migration or CI workflow was changed.

### Database, API, and environment

- Database changes: none; no migration was added. Existing client rows are not updated.
- API changes: no route, request, or response contract changed. Working PIN reset/view is a bug fix.
- Environment changes: `DEFAULT_TIMEZONE`'s application and example default is now `Asia/Kolkata`. No CI environment variables or GitHub secrets were added; PIN encryption continues to use the existing configured key or the existing development/test fallback.
- Test plan seeding mirrors migration `0006`: Starter (2250/25200, 300 minutes), Growth (5700/66000, 1000), Business (14250/165000, 2500), and custom Enterprise (no fixed prices, 0 included minutes).
- Global table exclusion is exactly `GLOBAL_TABLES = {"plans"}`; no other table was silently excluded.

### User-visible behavior and verification

- Admin PIN reset and pin-view now use the same Fernet configuration and encryption scheme as PIN verification.
- Newly provisioned businesses default to `Asia/Kolkata`; existing businesses retain their stored timezone.
- Business-update audit details now retain `updated` and also include `updated_fields` in hours/services/staff order, limited to values that changed.
- As requested, pytest and database commands were not run locally. Only `python -m compileall app tests` was run as a syntax check; the CI suite remains to be verified after push.
- Remaining CI risk: tests could expose failures outside the 16 diagnoses or fixture-order assumptions that cannot be checked without running against the CI PostgreSQL service.

# Phase 1.7 TESTFIX2

## Change report

- Branch: `phase-1-6-testfix` (continued current branch; no branch created).
- Base commit: `9767eede85e04da31ebb6407abcb3ca37179426a`.
- Commit: this report is included in the commit titled `Phase 1.7 TESTFIX2`; its resulting hash is reported in chat.

### The 7 CI failures

| # | Test | Root cause | Changed side | File(s) changed |
|---|---|---|---|---|
| 1 | `test_admin_businesses_listing_and_pin_isolation` | `BillingService.get_billing_me()` returns a dictionary, but the admin list accessed it as an object; the intended response fields were otherwise correct. | App code | `app/services/admin_service.py` |
| 2 | `test_get_business_bundle` | `register_ok()` registers a business named `Biz`; the test expected a suffix that the helper and registration route never send. | Test | `tests/test_b2_features.py` |
| 3 | `test_manual_submit_payment_amount_mismatch_and_validations` | Duplicate transaction errors had a custom `detail`/`code` shape rather than the standard `success`/`message`/`error_code` body. The frontend accepts both code keys and displays the message, so the app response was standardized. | App code | `app/core/exceptions.py` |
| 4 | `test_onboarding_status_lifecycle_and_tenant_isolation` | The fixture transaction ID contained underscores and failed the alphanumeric validation before payment submission. | Test | `tests/test_b3_features.py` |
| 5 | `test_every_table_has_client_id` | `email_verifications` belongs to a user and has no direct `client_id`; the test incorrectly treated it as a tenant-owned table. | Test | `tests/test_multi_tenant_security.py` |
| 6 | `test_tenant_tables_have_client_id_index_or_fk` | The same user-scoped table is keyed through `user_id`, not `client_id`. The test now verifies its FK to `users`. | Test | `tests/test_multi_tenant_security.py` |
| 7 | `test_every_api_route_requires_authentication_unless_allowlisted` | Forgot-password is intentionally public and rate-limited; it was missing from the test allowlist. | Test | `tests/test_multi_tenant_security.py` |

### Files changed

- `app/services/admin_service.py` — indexes the billing dictionary fields, preserving the `AdminBusinessItem` response fields and values.
- `app/core/exceptions.py` — formats duplicate-transaction errors using the standard error body.
- `tests/test_b2_features.py` — expects the business name actually produced by `register_ok()`.
- `tests/test_b3_features.py` — uses a valid alphanumeric transaction reference and asserts the payment submission returned HTTP 200.
- `tests/test_multi_tenant_security.py` — identifies the user-scoped email-verification table, checks its `user_id` foreign key, and allowlists public forgot-password.
- `CHANGELOG_PHASES.md` — records this phase and its diagnosis.

No files were created or deleted. No other tables were excluded from the tenant-structure checks beyond the already documented global `plans` catalog and user-scoped `email_verifications`.

### Database, API, and environment

- Database changes: none; no migration, table, or column changes.
- Routes and request formats: unchanged.
- Response change: duplicate transaction errors now return HTTP 400 with `{"success": false, "message": "Transaction ID already submitted", "error_code": "TRANSACTION_DUPLICATE"}`. The frontend HTTP helper reads both `code` and `error_code` and displays the message, so it does not depend on the old custom shape.
- Environment/configuration changes: none.

### Forgot-password review and behavior

- `POST /api/v1/auth/forgot-password` is limited to 10 requests per minute per remote IP. It does not impose a per-email limit.
- For ordinary existing and nonexistent email addresses, it returns the same generic response. Protected accounts are rejected with HTTP 403 by `assert_user_not_protected`, which can reveal that a protected account exists.
- There is no password-reset token generation, storage (hashed or otherwise), expiry, single-use handling, or reset email in this flow. The response says instructions were sent, but this implementation only records an audit event for a found, non-protected user; it does not send an email.
- No public reset-password route exists. `/api/v1/admin/users/{user_id}/reset-password` is a separate super-admin-protected operation and was not allowlisted.
- Admin businesses continue to expose `plan`, `minutes_used`, `minutes_limit`, `status`, `renews_on`, `last_login`, and `has_pin` as before; dictionary access fixes the runtime error without changing the schema.

### Verification and remaining uncertainty

- `python -m compileall app tests` — passed (syntax check only).
- `pytest` and database commands were not run, as requested; all seven fixes still require confirmation in GitHub CI.
- No other matching billing method caller was found using object attributes; `BusinessService` already uses dictionary access.

# Phase 1.8 TESTFIX3

## Change report

- Branch: `phase-1-6-testfix` (continued; no branch created).
- Base commit: `509734ff4af3d95c3f431138a8f866a6a84fc344`.
- Commit: this report is included in the commit titled `Phase 1.8 TESTFIX3`; its resulting hash is reported in chat.

### Part A — complete guard inventory

All 23 mapped tables across `app/models` and all route modules under `app/api/routes` were inspected.

| Test | Every table/route that would fail | Resolution |
|---|---|---|
| `test_every_table_has_client_id` | `enquiries`: nullable `client_id`; `refresh_tokens`: no `client_id` column. | `enquiries` is explicitly documented in `NULLABLE_TENANT_TABLES` as a platform contact-form table. `refresh_tokens` is explicitly classified as user-scoped. |
| `test_tenant_tables_have_client_id_index_or_fk` | `refresh_tokens`: no `client_id` to reference; it is scoped through `user_id`. | Added it to `USER_SCOPED_TABLES` and verify each such table has a `user_id` foreign key to `users`. All other tenant tables have a client FK; `enquiries.client_id` has a direct client FK and a composite customer/client FK. |
| `test_every_api_route_requires_authentication_unless_allowlisted` | `GET /api/v1/plans` and `POST /api/v1/contact` were missing from `PUBLIC_ROUTES`. | Added both with a comment identifying their pre-authentication purpose. All remaining routes either require JWT authentication or use an already allowlisted public/provider-authenticated flow. |

Other table classifications: `clients` is the tenant root; `plans` is the existing global catalog; `email_verifications` is user-scoped. Other nullable `client_id` tables remain the documented `users`, `audit_logs`, `webhook_events`, and `call_attempts`. No other table was excluded or newly exempted.

The complete `PUBLIC_ROUTES` set now contains:

- `/api/v1/health` — public health/readiness endpoint.
- `/api/v1/auth/register` and `/api/v1/auth/login` — public account entry points.
- `/api/v1/auth/refresh` and `/api/v1/auth/logout` — authenticate through refresh-token request bodies.
- `/api/v1/auth/forgot-password` — public password-help request, rate-limited per IP.
- `/api/v1/plans` — public pricing/signup catalog.
- `/api/v1/contact` — public contact form, protected by a honeypot and a 5-per-hour IP limit.
- `/api/v1/webhooks/sarvam` — authenticated by Sarvam request signature.
- `/api/v1/webhooks/sarvam/{token}/outbound` and `/api/v1/webhooks/sarvam/{token}/{client_id}/appointments/{check-slot,book,reschedule,cancel}` — authenticated by the configured secret token in the URL.

### Part B — model and route findings

- `enquiries.client_id` is nullable and is explicitly set to `None` by the public contact submission path. The contact form does not provide a customer ID. For enquiries with a customer, the composite FK on `(client_id, customer_id)` ensures the referenced customer belongs to that same client; the separate FK also validates `client_id` against `clients`.
- Contact enquiries are read and updated through `/api/v1/admin/messages` and `/api/v1/admin/messages/{message_id}`, both requiring a `SuperAdminUser`. Tenant users therefore cannot read platform-level or other tenants' enquiries through these routes.
- `refresh_tokens` has no `client_id`; its non-null `user_id` is a foreign key to `users`. It is now checked as user-scoped rather than being assigned a new tenant column.
- `/api/v1/plans` returns `PlanOut`: catalog ID/key/name, public prices, included and max call minutes, and custom-plan status. It returns no internal costs or tenant-specific data.
- The other unallowlisted public route found during the full scan was `/api/v1/contact`; it is designed for anonymous contact submissions and is rate-limited with a honeypot. The remaining app routes require authenticated user dependencies, except the already allowlisted signature- or token-authenticated provider endpoints.

### Files, database, API, and behavior

- `tests/test_multi_tenant_security.py` — adds the documented user-scoped and nullable-table exceptions, validates `user_id` FKs for both user-scoped tables, and allowlists public plans/contact routes.
- `CHANGELOG_PHASES.md` — records this phase and its complete table/route analysis.
- No files were created or deleted.
- Database changes: none; no migration or schema change.
- API changes: none; no route or response contract changed.
- Environment/configuration changes: none.
- User-visible behavior changes: none.

### Verification and remaining uncertainty

- `python -m compileall app tests` — passed; syntax check only.
- `pytest` and database commands were not run, as requested. The three structural/auth tests and the CI suite still need execution in GitHub CI.
- The failure inventory is based on the current model metadata and registered route modules; CI remains the final confirmation that no test environment-specific issue is hidden behind these failures.

## Phase 2A LOGWATCH-API

### Change report

- Branch: `phase-2`; base commit: `f31c3b6536fc7a69db3d1e5434cbe5a4021e43e6`. This entry is included in the commit titled `Phase 2A LOGWATCH-API`; the exact commit hash is reported in the completion message.
- Database: added reversible Alembic migration `0010_logwatch_indexes_and_request_id.py`. It adds nullable `webhook_events.request_id` (`TEXT`) and conditionally creates indexes on `webhook_events(status, created_at)`, `webhook_events(client_id, created_at)`, and `audit_logs(action, created_at)`. Tool-call records reuse `audit_logs`; no new table is added. CI runs `alembic upgrade head`; test fixtures subsequently drop and recreate tables through SQLAlchemy `create_all`.
- Webhook processing now sets `processed_at`, status, and failure details on processed, failed, and duplicate outcomes; known-agent failures retain the agent's client ID, and an existing client ID in failure metadata may attribute an otherwise unknown-agent event. Duplicate deliveries still receive the same Sarvam response while the stored event is marked duplicate. The middleware's existing `X-Request-ID` response header behavior is unchanged; request IDs are stored on webhook events and tool audit details.
- Tool calls for `check-slot`, `book`, `reschedule`, and `cancel` now create best-effort `sarvam_tool.*` audit rows after token verification. Rows include URL client ID (including the requested ID in details for unknown clients), action, outcome, error code/message, appointment ID, duration, and request ID. A transaction-serialized per-minute cap applies per client and to a shared null-client bucket. Invalid/missing token attempts are bounded application logs only; they do not create audit rows. Tool responses are not changed if logging fails.
- New super-admin read APIs: `GET /api/v1/admin/webhook-events` (status, client, event-type, date filters; paginated); `GET /api/v1/admin/webhook-events/{id}` (same fields plus sanitized payload); `GET /api/v1/admin/tool-calls` (client, tool, success, date filters; paginated); `GET /api/v1/admin/appointments` (client, status, source, date filters; paginated); `GET /api/v1/admin/monitoring` (paginated cross-client operational/billing summary); and `GET /api/v1/admin/health/details` (database status, last webhook time, configuration-presence booleans, email backend name). All require `SuperAdminUser`.
- Tenant `GET /api/v1/appointments` accepts optional `order=asc|desc`; the default remains ascending and `desc` orders newest appointment date/time first. Its response shape is unchanged. The public `/api/v1/health` route is unchanged.
- Security: webhook detail payloads are recursively scrubbed of keys containing token, secret, password, authorization, api-key, or signature markers; phone-like values are masked to their last four digits, and configured secret values are redacted. Tool-call logs do not contain request bodies or phone numbers. No URL token is stored. Monitoring exposes only whether a provider agent ID exists, never its value.

### Files changed

- `app/api/routes/admin.py` — registered the six super-admin Logwatch routes with existing authentication and pagination patterns.
- `app/api/routes/appointments.py` — added the optional appointment ordering query parameter.
- `app/api/routes/sarvam_webhooks.py` — wrapped all four tool routes with best-effort audit logging and bounded invalid-token logs.
- `app/api/routes/webhooks.py` — passed middleware request IDs into webhook processing.
- `app/core/exceptions.py` — audited valid-token schema failures and bounded missing-token application logs without changing error responses.
- `app/models/audit_log.py` — declared the action/created-time index.
- `app/models/webhook_event.py` — added nullable request ID and webhook query indexes.
- `app/schemas/admin.py` — added response models for event, tool-call, appointment, monitoring, and health details.
- `app/services/admin_service.py` — implemented filtered, paginated Logwatch queries and monitoring/health summaries.
- `app/services/appointment_service.py` — added descending ordering while retaining the existing default.
- `app/services/billing_service.py` — added shared summary and batched, read-only billing calculations for monitoring, without changing existing billing calls.
- `app/services/tool_call_log_service.py` — added capped audit persistence, token-safe logging, recursive masking, and payload sanitization.
- `app/services/webhook_service.py` — recorded event completion state, failure attribution, duplicate status, and request IDs.
- `alembic/versions/0010_logwatch_indexes_and_request_id.py` — added the reversible request-ID column and conditional indexes.
- `tests/test_logwatch_api.py` — added endpoint authorization/filtering/redaction, monitoring scoping, tool logging/cap/failure, webhook outcome, and ordering tests.
- `CHANGELOG_PHASES.md` — documented Phase 2A implementation and operational notes.

### Tests, configuration, and remaining work

- Added tests: `test_all_logwatch_routes_enforce_super_admin_authentication` covers 401/403/200 role boundaries; `test_webhook_event_filters_pagination_and_detail_redaction`, `test_tool_call_filters_pagination_and_no_sensitive_data`, and `test_admin_appointments_filters_order_and_pagination` cover list filters/pagination and response contents; `test_monitoring_is_tenant_scoped_and_paginated` covers cross-tenant metrics; `test_health_details_exposes_presence_booleans_not_secret_values` covers configuration redaction; `test_tool_call_audit_records_success_failure_masking_and_request_id`, `test_invalid_tool_token_creates_no_audit_row`, `test_valid_tool_failures_are_capped_without_changing_response`, `test_valid_token_schema_validation_failure_is_audited`, `test_unknown_client_failure_uses_shared_null_tenant_log_bucket`, `test_unknown_client_tool_audits_share_the_cap`, and `test_tool_logging_failure_does_not_change_tool_response` cover tool logging and failure isolation; `test_webhook_events_capture_processing_outcomes_and_request_ids` covers webhook statuses/attribution/correlation; and `test_tenant_appointment_desc_order_is_opt_in` covers descending order plus the unchanged default.
- No dependencies or environment variables were added or changed. Plan prices, included minutes, and Sarvam response shapes/status codes are unchanged.
- Local `pytest`, database startup, and migration execution were not run as requested. `python -m compileall app tests` is the only local validation; GitHub CI remains responsible for migration and test execution.
- No frontend files were touched, and no push was performed.

## Phase 2B LOGWATCH-UI

### Change report

- Branch: `phase-2`; base commit: `9a7a5cc26f92deee9f8c46153f620e25baea62ed`. The implementation is committed as `Phase 2B LOGWATCH-UI`; the resulting commit hash is included in the delivery message.
- `ai-calling-frontend/src/features/dashboard/types.ts` — added typed webhook event, tool-call, all-client appointment, monitoring, health, and paginated result models matching the admin API fields.
- `ai-calling-frontend/src/features/dashboard/api.ts` — added six admin API adapters; retained pagination metadata, added nested payload sanitization, and added mock paging/filtering; live tenant appointment fetches now request `order=desc`.
- `ai-calling-frontend/src/lib/http.ts` — added opt-in envelope preservation for paginated admin responses; existing callers still unwrap responses by default.
- `ai-calling-frontend/src/features/dashboard/mock.ts` — added realistic sanitized logwatch samples, including unknown-agent and slot-conflict failures, near/over-limit clients, and enough list rows to exercise pagination.
- `ai-calling-frontend/src/features/dashboard/views-logwatch.tsx` — added the four role-guarded, lazy-fetch platform views, filters, pagination, retries/empty/error states, sanitized event detail modal, copy controls, health panel, and attention indicators.
- `ai-calling-frontend/src/features/dashboard/shell.tsx` — added four platform-only navigation links.
- `ai-calling-frontend/src/features/dashboard/dashboard.css` — added responsive horizontal table scrolling and styles for the new filters, health panel, modal payload, and attention rows.
- `ai-calling-frontend/src/app/dashboard/platform/monitoring/page.tsx` — registered the Monitoring screen under the platform route tree.
- `ai-calling-frontend/src/app/dashboard/platform/webhook-events/page.tsx` — registered the Webhook events screen under the platform route tree.
- `ai-calling-frontend/src/app/dashboard/platform/tool-calls/page.tsx` — registered the Tool calls screen under the platform route tree.
- `ai-calling-frontend/src/app/dashboard/platform/appointments/page.tsx` — registered the cross-client appointments screen under the platform route tree.
- `CHANGELOG_PHASES.md` — recorded the Phase 2B implementation, verification limitation, and mock-mode test steps.

### Database, API, and behavior

- Database changes: none. No backend file changed.
- New calls, made only when the corresponding screen opens: `GET /api/v1/admin/monitoring` and `GET /api/v1/admin/health/details` on Monitoring; `GET /api/v1/admin/webhook-events` on Webhook events and `GET /api/v1/admin/webhook-events/{id}` only when an event is opened; `GET /api/v1/admin/tool-calls` on Tool calls; `GET /api/v1/admin/appointments` on All appointments. Each list sends its supported filters plus `page` and `limit`. These calls are not added to dashboard initialization.
- Existing live appointment reads used by initial dashboard loading and polling now call `GET /api/v1/appointments?limit=100&order=desc`. Mock appointment behavior is unchanged. No other existing response shape changed.
- Platform navigation is shown only to the super-admin role; the existing platform route middleware remains in place, and the new views do not fetch or render data for other roles. API adapters also enforce the frontend role check outside mock mode.
- Payload display recursively removes keys containing `token`, `secret`, `password`, `authorization`, `api_key`, or `signature`, and masks phone-like values to their last four digits. No log records are stored in localStorage. Health displays configuration presence booleans and the email backend name, not configuration values.
- Environment variables and configuration: none added or changed. Mock behavior uses the existing `NEXT_PUBLIC_API_MODE=mock`.
- No new automated tests were added in this frontend phase.

### Build and manual mock checks

- Build command from `ai-calling-frontend`: `npm run build`. It could not complete because the local frontend dependencies are absent: `next` is not recognized as a command and `ai-calling-frontend/node_modules/.bin/next` does not exist. No packages were installed, as requested. `git diff --check` passed.
- Manual mock-mode check: in PowerShell, run `Set-Location C:\dev\talkaor-u2\ai-calling-frontend`, set `$env:NEXT_PUBLIC_API_MODE='mock'` and `$env:NEXT_PUBLIC_DASH_SIMULATE='1'`, then run `npm run dev`. In the super-admin dashboard use the new sidebar links or open `/dashboard/platform/monitoring`, `/dashboard/platform/webhook-events`, `/dashboard/platform/tool-calls`, and `/dashboard/platform/appointments`.
- Monitoring: verify all four client cards, especially Kale Wellness Studio near its limit and Patil Auto Care over its limit; check the health presence badges.
- Webhook events: filter status `failed`, client ID `2`, event type `call.completed`, and date `2026-10-24`; open the event row to inspect/copy the sanitized payload. Also clear the client filter and inspect the unknown-agent failure; try Next to exercise pagination.
- Tool calls: filter client ID `2` and outcome `Failure` to see the slot conflict; clear the client filter to see an unresolved-client failure. Copy a request ID and try Next.
- All appointments: filter client ID `2`, source `manual`, and date `2026-10-24` through `2026-10-30`; verify AI-agent/manual badges and newest-created ordering, then try Next.
- In the development role switcher, select Staff or Admin and confirm the platform links disappear and platform URLs redirect away. The build remains unverified until dependencies are available in CI or another configured environment.

## Phase 3A AGENTLINK-API

### Change report

- Branch: `phase-2`; base commit: `e50e90d052d89399287e4eb0020d3a0dbd87c621`. The implementation is committed as `Phase 3A AGENTLINK-API`; the resulting commit hash is included in the delivery message.
- `app/models/agent.py` — added the partial unique phone-number index; the nullable phone column and platform-wide `(provider, provider_agent_id)` uniqueness already existed.
- `app/models/client_tool_credential.py` — added the tenant-scoped credential model with hashed token and lifecycle timestamps.
- `app/models/__init__.py` — registered the credential model for metadata and schema creation.
- `alembic/versions/0011_agent_links_and_client_tool_credentials.py` — added the reversible credential table/indexes and phone-number uniqueness migration.
- `app/schemas/agent_link.py` — added super-admin agent-link, update, integration, and one-time token response schemas with E.164 validation.
- `app/schemas/admin.py` — added `phone_number` to the existing cross-client admin agent response.
- `app/core/config.py` — added `PUBLIC_API_BASE_URL` and `SARVAM_LEGACY_SHARED_TOKEN_ENABLED` settings.
- `.env.example` — documented the optional public API origin and the legacy-token cutover flag.
- `app/services/admin_agent_service.py` — implemented super-admin agent create/update/soft-unlink, conflict handling, and field-level audit records.
- `app/services/client_tool_credential_service.py` — implemented credential creation/rotation, integration details, token hashing, and best-effort last-used updates.
- `app/services/tool_call_log_service.py` — added bounded legacy-token warnings and capped audit logging integration.
- `app/services/admin_service.py` — included `phone_number` in the existing super-admin agent list.
- `app/api/routes/admin.py` — added super-admin-only agent-link, unlink, token, and integration endpoints.
- `app/api/routes/agents.py` — restricted tenant create/delete and non-status updates; retained tenant status toggles and tenant-scoped agent reads.
- `app/api/routes/sarvam_webhooks.py` — changed the four appointment tool routes to validate per-client credentials, with gated legacy-token compatibility and no token in audit/log messages.
- `tests/helpers.py` — added test helpers for super-admin agent creation and authentication.
- `tests/test_agentlink_api.py` — added tests for route authorization, linking and duplicate checks, tenant boundaries, credential rotation/scope, secret non-disclosure, and legacy compatibility.
- `tests/test_agents.py` — moved agent management assertions to super-admin endpoints and verified soft unlink and retained tenant power toggles.
- `tests/test_b1_features.py` — updated staff elevation assertions for the new restricted agent permissions.
- `tests/test_multi_tenant_security.py` — updated cross-tenant agent mutation expectations and asserted tenant creation is forbidden.
- `CHANGELOG_PHASES.md` — recorded this Phase 3A report.

### Database

- Migration: `0011_agent_links_and_client_tool_credentials.py`, following `0010`.
- `agents.phone_number` was already nullable in the existing schema, so no duplicate column was added. `(provider, provider_agent_id)` was already protected by the database-wide `uq_agents_provider_ref` constraint.
- Added partial unique index `uq_agents_phone_number` on non-null phone numbers.
- Added `client_tool_credentials`: `id`, non-null `client_id` FK, `token_hash`, `created_at`, `rotated_at`, `last_used_at`, and `revoked_at`; added the `client_id` index, unique token-hash constraint, and partial unique active-client index.
- Upgrade normalizes existing phone formatting and resolves duplicate phone assignments deterministically: the lowest agent ID retains the number and later duplicates are set to null before the unique index is created. Original values changed by this migration are stored temporarily in `agent_phone_number_migration_backup`; downgrade removes the new table/indexes and restores those original values where the phone field has not subsequently been changed. This prevents existing duplicate rows from blocking upgrade and preserves rollback data.
- The migration is reversible. No existing duplicate provider-agent IDs can block upgrade because the prior database constraint already enforced uniqueness.

### API and behavior

- `POST /api/v1/admin/clients/{client_id}/agents` — super admin only; accepts `name`, `provider`, `provider_agent_id`, `phone_number`, `description`, and `configuration`; returns the created `AgentOut` in the standard response envelope. Duplicate provider-agent IDs and phone numbers return 409 with `AGENT_ID_IN_USE` or `PHONE_IN_USE`.
- `PATCH /api/v1/admin/agents/{agent_id}` — super admin only; accepts `name`, `provider`, `provider_agent_id`, `phone_number`, and `status`; returns updated `AgentOut`.
- `POST /api/v1/admin/agents/{agent_id}/unlink` — super admin only; marks the agent inactive without deleting it.
- `POST /api/v1/admin/clients/{client_id}/tool-token` — super admin only; creates or rotates a credential, immediately revokes the prior one, and returns the raw token and four ready-to-use tool URLs once.
- `GET /api/v1/admin/clients/{client_id}/integration` — super admin only; returns the signed event webhook URL, four tool URL patterns using `{TOKEN}`, URL absoluteness, credential timestamps/existence, and linked agent IDs and phone numbers; it never returns a credential.
- `GET /api/v1/agents` and existing `GET /api/v1/admin/agents` — retain existing fields and now include `phone_number`; tenant responses remain tenant-scoped.
- Tenant `POST /api/v1/agents` and `DELETE /api/v1/agents/{agent_id}` are now forbidden. Tenant `PATCH /api/v1/agents/{agent_id}` accepts only `status`; attempts to modify name, provider, provider-agent ID, or phone return 403. The existing status/power toggle remains available.
- The four `POST /api/v1/webhooks/sarvam/{token}/{client_id}/appointments/{check-slot|book|reschedule|cancel}` routes now validate the token against that client’s active credential. Invalid or cross-client credentials retain the existing 404 response and create no audit rows. While the legacy flag is enabled, the shared token remains accepted with bounded warning/audit records; valid tool calls and failures continue through the existing capped audit logging. The signed event webhook and outbound webhook route were not changed.
- New agent and credential operations audit the acting super admin, client ID, and changed field names. Tokens are hashed at rest, compared with constant-time comparison, and excluded from logs/audit details; integration responses use only `{TOKEN}`.

### Configuration, tests, and remaining work

- `PUBLIC_API_BASE_URL` is optional. When unset, integration URLs are relative and `urls_are_absolute` is false. Set it to the public API origin if absolute tool/webhook URLs are required.
- `SARVAM_LEGACY_SHARED_TOKEN_ENABLED` defaults to `true` for compatibility. Keep it enabled during migration, then set it to `false` after every client uses an individual token. No real secrets were added or changed.
- New tests: `test_admin_agent_and_integration_routes_require_super_admin` (401/403/success authorization); `test_agent_phone_provider_uniqueness_and_validation` (normalization, invalid phone, and duplicate conflicts); `test_clients_only_read_agent_links_and_can_keep_status_toggle` (client/staff restrictions, power toggles, and tenant scoping); `test_client_tool_tokens_are_scoped_rotated_and_never_logged` (hashing, rotation, cross-client rejection, and no token leakage); `test_legacy_shared_token_flag_logs_without_token_and_can_be_disabled` (gated compatibility and audit/warning behavior).
- Verification: `python -m compileall app tests` is a syntax-only check. Pytest and database commands were not run as requested; CI must run the full suite and migration checks.
- No frontend files were changed. Existing dashboard calls `GET /api/v1/agents`, `GET /api/v1/admin/agents`, tenant `PATCH /api/v1/agents/{agent_id}` with only `status`, and super-admin `PATCH /api/v1/admin/agents/{agent_id}/power` remain compatible. Calls to tenant `POST /api/v1/agents`, `DELETE /api/v1/agents/{agent_id}`, or tenant PATCH with fields other than `status` now receive 403. No frontend agent-creation call was found during the prior review.
- Potential operational issue: existing duplicate phone assignments are deterministically cleared except for the lowest-ID agent during upgrade; the originals are preserved for downgrade. Review these reassigned agents after deployment if their phone links need manual correction.

## Phase 3B AGENTLINK-UI

### CHANGE REPORT

1. Branch: `phase-2`; base commit: `47ba8af08813af40c2cc5402bd1272c7ef193c5e`; new commit hash: reported in the delivery message. The commit hash cannot be embedded here because this report is part of that commit.
2. Files changed:
   - `ai-calling-frontend/src/features/dashboard/types.ts` — added client integration, one-time token, billing response, and extended agent types.
   - `ai-calling-frontend/src/features/dashboard/api.ts` — added role-checked agent-link/integration/token/billing adapters, mock behavior, error mapping, and admin API guards.
   - `ai-calling-frontend/src/features/dashboard/mock.ts` — added Sarvam agent metadata and mock client integration data.
   - `ai-calling-frontend/src/features/dashboard/ui.tsx` — added reusable clipboard feedback and configurable billing progress bar.
   - `ai-calling-frontend/src/features/dashboard/views-platform.tsx` — extended the existing platform Agents view with client integration, link/edit/unlink, and one-time token workflows.
   - `ai-calling-frontend/src/features/dashboard/views-tenant.tsx` — shows assigned phone numbers and billing credit; removes tenant agent create/configure controls.
   - `ai-calling-frontend/src/features/dashboard/shell.tsx` — blocks tenant access to platform routes and hides role switching outside mock mode.
   - `CHANGELOG_PHASES.md` — recorded this Phase 3B report.
   - No files were created or deleted.
3. Database changes: none.
4. API calls:
   - `GET /api/v1/admin/agents` — loads the platform agent list; client integration data is fetched to fill in provider agent ID, status, and token-exists fields absent from the existing list response.
   - `GET /api/v1/admin/clients/{client_id}/integration` — enriches agent rows and opens a client’s integration view.
   - `POST /api/v1/admin/clients/{client_id}/agents` — links a Sarvam agent and E.164 phone number.
   - `PATCH /api/v1/admin/agents/{agent_id}` — edits the linked agent name, provider agent ID, and phone.
   - `POST /api/v1/admin/agents/{agent_id}/unlink` — deactivates an agent without deleting it.
   - `POST /api/v1/admin/clients/{client_id}/tool-token` — generates or rotates the client token; its response is shown once and is not persisted.
   - `GET /api/v1/billing/me` — loads the signed-in client’s plan, minutes, alert, and renewal date.
   - Existing `GET /api/v1/agents` remains the tenant list call. Tenant power changes continue through `PATCH /api/v1/agents/{agent_id}` with only `{ "status": "active" | "inactive" }`; super-admin power changes continue through `PATCH /api/v1/admin/agents/{agent_id}/power`.
   - Tenant agent creation/deletion and non-status edits are not called. No backend file changed.
5. Environment/configuration changes: none.
6. Behavior by role:
   - Super admin: can link/edit/unlink Sarvam agents, copy phone numbers and integration URLs, and generate/rotate a client tool token. Rotation warns that the prior token stops working. Raw tokens and ready URLs exist only in the one-time view’s component state.
   - Client admin: sees their assigned number/status and billing credit; can toggle agent power and cannot create, delete, or edit agent configuration. The prior minute-pack button was removed because it invoked a super-admin-only API.
   - Client staff: sees the assigned number/status and billing credit; agent management controls for create/delete/edit are absent. Existing admin-session requirements for power changes remain.
7. Build: not run; `ai-calling-frontend/node_modules` is absent. Dependencies were not installed, as requested.
8. Assumptions and remaining items:
   - The backend schemas provide every billing field used by the UI. The existing admin agent list omits provider agent ID and status, so the UI obtains these from the per-client integration response.
   - The seeded mock billing sample is 62% used (normal state); warning and limit styling follows the response `alert` and `usage_percent` values.
   - Exact mock-mode manual checks:
     1. In PowerShell, run `Set-Location C:\dev\talkaor-u2\ai-calling-frontend`, `$env:NEXT_PUBLIC_API_MODE='mock'`, then `npm run dev` when dependencies are available. Sign in, then use the mock role switcher to choose Super Admin.
     2. Open **AI agents (all)**. Link an agent to a client with a unique provider ID and phone such as `+919876543210`. Try provider ID `sarvam-sunrise-aria` and phone `+912040001101` to verify the duplicate messages; enter an invalid phone to verify inline E.164 validation.
     3. Edit the new agent and confirm the name, provider ID, and phone update. Choose **Unlink**, verify the confirmation says it deactivates rather than deletes, then confirm the row remains with inactive status.
     4. Open a client’s **Integration** view. Verify the relative-URL hint, signed event URL, four `{TOKEN}` patterns, credential status/timestamps, linked agent IDs/phones, copy buttons, and the legacy shared-token note.
     5. Generate a token and confirm the warning. Copy the token and all four ready URLs, close the modal, reopen Integration, and verify the raw token is not shown again. Rotate it and verify the new one-time modal and warning.
     6. Switch to Client Admin, open **AI Voice Agents**, verify the assigned number and copy button, the customer-call explanation, and the active status. Verify there are no Add, Configure, Edit, or Unlink controls; test the power toggle.
     7. On the client dashboard, verify the Growth plan, `114 of 300 minutes left`, renewal date, normal progress color, and rounded-up-minute note. Switch to Staff and verify the same read-only phone and billing details.
     8. In non-mock/live mode, verify the role switcher is absent for clients and directly opening a `/dashboard/platform/...` route shows the access-denied state and redirects.
