# HXY Knowledge Activation Release Design

## Goal

Safely prepare Knowledge Activation Loop V1 for production without automatically migrating the production database, restarting services, publishing knowledge, or changing HXY business data.

The release package must make this sequence repeatable and auditable:

```text
read-only preflight
-> verified local backup
-> explicit bounded migration 009-014
-> post-migration schema verification
-> API canary
-> worker canary
-> assignment-isolation acceptance
```

## Product Boundary

Production activation does not change the knowledge authority model:

- uploaded materials remain `working_context/reference`;
- every uploaded artifact and chunk remains `official_use_allowed=false`;
- assignment-private retrieval cannot return `已批准`;
- only approved answer cards can act as formal authority;
- chat, process memory and answer Trace cannot modify core knowledge;
- no HXY data may be written to `/root/htops` or an htops database.

## Alternatives Considered

### Direct in-place migration and restart

Apply every migration with the existing script and restart both services. This is fast but gives weak evidence, has no mandatory backup gate and can accidentally rerun an unbounded migration set. Reject for production activation.

### Full blue-green database and service deployment

Clone the database, run a second API and worker stack, switch traffic and retain the old stack. This gives the strongest rollback isolation but doubles operational complexity before HXYOS has production traffic that warrants it. Defer until store scale or availability requirements justify it.

### Guarded additive in-place release

Use read-only preflight, a verified custom-format PostgreSQL backup, an exact migration allowlist, explicit operator confirmation and postflight checks. Activate API before worker and stop on the first failed gate. This is the selected approach because migrations `009-014` are additive or compatibility-preserving and the current deployment is single-host and low traffic.

## Release Components

### Release CLI

Add one HXY-owned Python CLI with four commands:

```text
preflight  read-only environment, PostgreSQL and migration inspection
backup     pg_dump plus pg_restore verification and a redacted manifest
apply      exact 009-014 migration allowlist with explicit confirmation
postflight read-only schema and governance constraint verification
```

The CLI reads `HXY_DATABASE_URL` or an explicit env file. It never prints a password, API token, model key or complete DSN. Mutating `apply` requires both a valid backup manifest and an exact confirmation phrase.

### Backup Artifact

The default backup location is HXY-owned and excluded from public release:

```text
/root/hxy/data/backups/knowledge-activation/<UTC timestamp>/
```

Each backup contains:

```text
hxy-before-activation.dump
manifest.json
```

The manifest records database identity without credentials, UTC time, Git commit, dump size, SHA-256, `pg_restore --list` verification and the planned migration range. Directory mode is `0700`; files are `0600`.

### Migration Boundary

Only these files may run through this release command:

```text
009_hxy_product_identity.sql
010_hxy_product_conversations.sql
011_hxy_product_materials.sql
012_hxy_assignment_sessions.sql
013_hxy_material_intake_jobs.sql
014_hxy_knowledge_activation.sql
```

The migration runs with `ON_ERROR_STOP=1` and one PostgreSQL transaction. The command verifies migration checksums against the local files after the backup and refuses a manifest for a different database or changed migration set.

The existing `scripts/apply-db-migrations.sh` remains a development/bootstrap utility. It is not the production activation path.

## Release Gates

### Gate 1: Code

- feature branch is pushed;
- worktree is clean;
- full tests pass;
- production Web build passes;
- secret and public-release scans pass.

### Gate 2: Read-only preflight

- PostgreSQL major version is 16;
- database identity is HXY-owned;
- baseline tables needed by migration 009 exist;
- required migration files exist and have stable checksums;
- API and worker environment files are present but secrets are not emitted;
- product material storage exists and is writable by the service account;
- no htops path or database is selected.

Preflight may report migrations as pending. It must not create tables, update rows or start services.

### Gate 3: Backup

- custom-format dump exits successfully;
- `pg_restore --list` can read the dump;
- dump SHA-256 and byte size match the manifest;
- manifest database identity matches the target;
- backup is newer than the configured release window.

### Gate 4: Migration

- operator supplies the exact confirmation phrase;
- backup manifest passes Gate 3 again immediately before migration;
- only migrations `009-014` are executed;
- any SQL error rolls back the transaction and stops the release.

### Gate 5: Postflight

- product identity, conversation, material, parser job, artifact, private chunk and Trace tables exist;
- `official_use_allowed=false` checks exist for materials, artifacts and chunks;
- assignment ownership foreign keys exist;
- answer Trace has one-row-per-assistant uniqueness;
- trigram retrieval index exists;
- no business rows are created by migration or postflight.

### Gate 6: Canary

Start the API first. Require `/health` success and authenticated identity/session access. Start one worker only after the API canary passes. Then perform a controlled assignment-scoped acceptance:

```text
upload one harmless test document
-> wait for ready
-> ask one keyword question
-> verify AI 草稿 and source link
-> ask from a foreign assignment
-> verify no retrieval
-> archive the test material
```

The canary must not approve an answer card or alter core knowledge.

## Failure And Rollback

Stop immediately if any gate fails. Do not continue to the next gate with a warning.

Code rollback is preferred because migrations `009-014` are additive and old code can ignore new tables. Stop the worker before rolling API code back.

Database restore is a separate emergency operation. It is never automatic because restore discards writes made after the backup. A restore requires an explicit maintenance window, service shutdown, a second confirmation and verification of the backup manifest. This release package documents restore prerequisites but does not execute restore.

## Observability

Every command returns a bounded JSON summary suitable for attaching to a release record. Output may contain check names, pass/fail status, migration filenames, table names, counts and durations. It must not contain:

- credentials or full DSNs;
- uploaded source text;
- answer text or prompts;
- local material paths or storage keys;
- HXY business data.

## Test Strategy

1. Unit-test DSN redaction, migration allowlisting, backup-manifest validation and schema check interpretation.
2. Use fake subprocess runners for backup and migration failure paths.
3. Apply `001-014` to an isolated PostgreSQL 16 database and run postflight.
4. Exercise the existing material/retrieval/Trace PostgreSQL integration test.
5. Run the complete repository test suite, Web build and release scans.

## Acceptance

The release package is ready when:

- preflight is demonstrably read-only;
- a verified backup can be produced without exposing credentials;
- apply cannot run without a matching recent backup and exact confirmation;
- apply cannot execute files outside `009-014`;
- postflight proves the governance and assignment-isolation schema;
- an isolated PostgreSQL 16 rehearsal passes end to end;
- production remains unchanged until a separate deployment decision.
