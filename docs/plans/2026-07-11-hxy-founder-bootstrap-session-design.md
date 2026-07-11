# HXY Founder Bootstrap And Session Link Design

## Goal

Create the first governed HXY founder identity and let that founder open HXYOS on desktop or mobile without a password form, while preserving assignment-scoped authorization and avoiding credentials in server access logs.

## Current Constraint

The production schema is ready through migration `014`, but these tables have no business rows:

```text
staff_accounts
hxy_organizations
hxy_role_assignments
```

The product frontend immediately calls `/api/v1/me` and has no login surface. The existing trusted gateway endpoint requires a server-side HMAC assertion, but no Feishu or SSO gateway currently issues that assertion. Starting the worker before an authenticated assignment can be verified would violate the release Gate.

## Alternatives

### Username and password login

Add a login page and password reset flow. This creates password storage, recovery, brute-force protection and a visible interaction the product does not need. Reject for the first founder path.

### Put a bearer token in the URL query

Generate `?token=...` and exchange it for a cookie. This is simple but query strings are commonly recorded by reverse proxies, browser history and analytics. Reject.

### One-time short-lived session link in the URL fragment

Create a high-entropy, ten-minute bootstrap session and place it after `#`. URL fragments are not sent in HTTP requests. The frontend removes the fragment immediately, posts the token in the request body to a same-origin exchange endpoint, and receives a rotated HttpOnly cookie. This is the selected approach.

## Founder Bootstrap

Add an HXY-owned CLI:

```text
scripts/bootstrap-hxy-founder.py
```

Inputs:

```text
username
display name
organization slug
organization name
application URL
exact confirmation phrase
```

The command requires:

```text
BOOTSTRAP-HXY-FOUNDER
```

It opens one PostgreSQL transaction and refuses to run unless all three identity tables are empty. It creates:

1. one active `staff_accounts` row with legacy role `hq_admin`;
2. one active HXY organization;
3. one active organization-scoped `founder` assignment;
4. one ten-minute bootstrap row in `staff_sessions` tied to that assignment.

No password login is enabled. `password_hash` receives an unusable randomized gateway-only marker so no default password exists.

The raw session token is generated with at least 256 bits of entropy, stored only as SHA-256 and returned once in a URL fragment:

```text
https://<hxy-app>/#hxy_session_grant=<opaque token>
```

The CLI must not write the raw token to a file, database, release record or log.

## Session Exchange

Add:

```text
POST /api/v1/auth/session-grant
```

Request:

```json
{"grant":"<opaque token>"}
```

The repository hashes the grant, locks the matching session row, verifies expiry and active account/organization/assignment, deletes the grant row, creates a fresh normal session and returns the new raw token only to the route. The route sets the existing `hxy_session` HttpOnly cookie and never returns either token in JSON.

Properties:

- one-time: the grant row is deleted in the exchange transaction;
- rotating: the cookie token differs from the fragment token;
- assignment-bound: both rows carry the same `assignment_id`;
- short-lived grant: ten minutes maximum;
- normal session: existing configured session TTL;
- no query-string credential;
- no core-knowledge or material write.

## Frontend Flow

Before the initial `/api/v1/me` request, `SessionProvider` checks `window.location.hash` for exactly one `hxy_session_grant` value.

If present:

1. copy the value to memory;
2. immediately remove the fragment with `history.replaceState`;
3. `POST /api/v1/auth/session-grant` with same-origin credentials;
4. call `/api/v1/me`;
5. render the existing minimal conversation UI.

No login page, token input, instructional card or dashboard is added. Invalid or expired links fall into the existing unauthorized state without showing token details.

## Security Boundary

- Require HTTPS when `HXY_AUTH_SECURE_COOKIE=true`.
- Never accept the grant through query parameters or headers written by the frontend.
- Require an exact JSON body shape and bound token length.
- Return the same `401` response for missing, expired, consumed or unknown grants.
- Do not log request bodies.
- Delete the old grant before inserting the normal session in the same transaction.
- Refuse bootstrap when any identity row already exists; later staff onboarding uses a separate governed workflow.
- Keep the existing HMAC gateway endpoint for future Feishu/SSO integration.

## Operational Flow

```text
verify production backup
-> run bootstrap CLI with explicit founder metadata
-> start API canary
-> open one-time link
-> verify /api/v1/me returns founder assignment
-> verify conversation and upload
-> start worker
-> archive canary material
```

The CLI does not start services. The API and worker remain separate release Gates.

## Testing

1. Unit tests for validation, entropy, fragment URL construction and secret-free output.
2. Repository tests for atomic creation, empty-database refusal, one-time exchange, expiry and assignment preservation.
3. Route tests for HttpOnly cookie, constant unauthorized responses and no token in JSON.
4. Frontend tests proving the fragment is removed before network exchange and `/api/v1/me` runs afterward.
5. Playwright mobile test proving the link reaches the existing conversation UI without a login form.
6. Isolated PostgreSQL 16 integration test for bootstrap and one-time rotation.

## Acceptance

- founder bootstrap is impossible without exact confirmation;
- no default password is created;
- grant token never appears in a database row, URL query, response JSON or committed file;
- grant can be exchanged exactly once;
- `/api/v1/me` returns the founder assignment after exchange;
- mobile and desktop reach the same minimal conversation shell;
- existing assignment isolation and formal-knowledge boundaries remain unchanged;
- production identity creation remains a separate explicit operation after code review and deployment.
