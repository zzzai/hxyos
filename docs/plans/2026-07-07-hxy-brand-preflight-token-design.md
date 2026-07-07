# HXY Brand Preflight Token Design

## Problem

`brand-check.html` now calls the real compliance workflow gate, but that endpoint is protected by `HXY_API_TOKEN`. Without a bearer token, the page falls back to local keyword checks. That makes the page look useful while silently skipping the enterprise gate.

## Decision

Add a minimal "系统口令" field to `brand-check.html`.

The page will:

- read `hxyActionApiToken` first
- fall back to `hxyBrainApiToken`
- fall back to `hxyKnowledgeApiToken`
- save any entered token back to `hxyActionApiToken`
- send `Authorization: Bearer <token>` on API requests

If no token is available or the API is unreachable, the page still uses local preflight fallback. It must not claim formal approval.

## UI Rule

This is not an audit or review surface. The token field is only a connection control. It must not expose governance internals or approval actions.

## Testing

Frontend tests verify:

- the page exposes the system token field
- it reuses existing admin tokens
- workflow gate requests include `Authorization`
- local boundary-language fallback still works
