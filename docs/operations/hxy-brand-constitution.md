# HXY Brand Constitution Operations

## Purpose

The Brand Constitution is the small, owner-approved root of formal brand identity answers. It is not a chat memory, a raw document collection, or an automatically promoted claim set.

Only an active constitution that passes the adapter validation can produce a `formal` answer. When it is missing, invalid, expired, or superseded, the normal governed retrieval path may still produce a `working` answer, but it cannot claim to be the official brand position.

## Local Layout

Real content stays outside Git under the HXY-owned private data root:

```text
/root/hxy/data/private/brand-constitution/
  active.json              # active version plus approved content SHA-256
  events.jsonl             # publish and rollback write-ahead audit events
  versions/
    1.0.0.json
    1.1.0.json
```

`tests/fixtures/brand-constitution-v1.example.json` contains invented wording only. It is a schema example, not HXY business knowledge.

## Approval Contract

A valid version requires:

- schema `hxy-brand-constitution.v1`;
- a unique immutable version and named owner;
- `status=approved` and `owner_approved=true`;
- approver, approval time, effective time, and an optional valid expiry;
- one brand identity sentence and concrete service facts;
- structured forbidden interpretations with a human-readable `statement` and explicit `blocked_terms`;
- role variants for founder, headquarters, store manager, and store staff;
- source references whose authority is `official_internal` or `approved_answer_card`.

External articles, books, process memory, model output, or ordinary chat cannot grant formal authority. They may support a change proposal, but a new version must be reviewed and activated through an operational change.

## Publish A New Version

1. Copy the prior local version to a new version filename.
2. Edit the new file; never overwrite the prior version.
3. Validate the proposed file with the adapter in a controlled operation.
4. Record owner approval outside the chat flow.
5. Append a `publish` event containing an event ID, the version, and approved file SHA-256.
6. Change `active.json` atomically to the approved version, the same SHA-256, and the publication event ID.
7. Run the ten-question benchmark before release.

Do not expose a conversation command that writes a version or changes `active.json`.

## Rollback

Rollback is an explicit operator action, not an Agent tool:

```python
from pathlib import Path
from hxy_knowledge.brand_constitution import BrandConstitutionAdapter

adapter = BrandConstitutionAdapter(Path("/root/hxy"))
adapter.rollback(
    target_version="1.0.0",
    actor="named-operator",
    reason="documented operational reason",
)
```

The target must be an earlier semantic version, remain valid and approved, and match its recorded publication digest. Rollback is serialized with a local operation lock. It writes one durable rollback authorization event before changing `active.json`, then binds the active pointer to that event ID. There is no second audit write after the authority switch.

The API verifies the active file against the digest in `active.json` and verifies that the pointer matches an existing publication or rollback event on every load. Editing content or changing only the pointer therefore removes formal authority instead of silently changing the organization standard.
