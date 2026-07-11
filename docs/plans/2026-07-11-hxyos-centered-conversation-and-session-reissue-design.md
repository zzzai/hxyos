# HXYOS Centered Conversation And Session Reissue Design

## Product Intent

HXYOS frontstage remains a minimal organization AI workbench. The empty
conversation should behave like DataAgent or Codex: one central task surface,
not a dashboard. Once work starts, the interface should become a stable chat
workspace without moving navigation or adding cards.

## Adaptive Conversation Layout

The conversation stage owns one content axis. The empty heading, suggestions,
composer, message list, and material receipts all use the same bounded width.

```text
empty conversation:
header
-> centered heading + suggestions + composer

active conversation:
header
-> centered scrollable message stream
-> centered bottom composer
```

The stage receives an explicit `is-conversation-empty` state. CSS places the
empty content and composer in the same central grid area. When a message is
created, the class disappears and the existing three-row chat layout resumes.
Mobile keeps 12-16px side clearance and places the centered group above the
bottom navigation.

No new cards, dashboards, promotional copy, or workflow menus are introduced.

## Session Link Reissue

Founder bootstrap is one-time and must remain one-time. A separate host-only
CLI reissues a short-lived session grant for an existing active founder:

```text
exact operator confirmation
-> lock identity operation
-> resolve active founder assignment
-> persist only SHA-256 of a new random grant
-> return one HTTPS fragment link once
```

The command does not create or modify identities, does not expose the database
DSN, and does not invalidate active browser sessions. Expired grants may remain
until normal cleanup; every newly issued grant expires within ten minutes and
is consumed atomically by the existing exchange endpoint.

## Acceptance

- Empty desktop and mobile conversations show one centered task surface.
- After the first message, the composer moves to the bottom chat position.
- The composer and messages share the same horizontal center.
- Existing accessibility, upload, citation, and role permission behavior stays
  unchanged.
- Reissue requires an exact confirmation and an existing active founder.
- The database stores only the grant hash.
- The resulting public fragment link exchanges once into a Secure HttpOnly
  cookie session.
