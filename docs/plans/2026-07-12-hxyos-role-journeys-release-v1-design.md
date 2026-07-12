# HXYOS Role Journeys Release V1 Design

## Status

Approved for implementation on 2026-07-12.

This is an internal release design. It does not add a public repository description,
marketing README, public roadmap or detailed GitHub project narrative.

## Goal

Release the complete Product Shell stack through `015-016` without running production
from a dirty worktree, mutating core knowledge, or applying database changes without a
verified backup and exact confirmation.

## Current State

- Release candidate commit: `4a9810b5355ad30e134ea60bf19c6ee45f25b5e3`.
- The release branch is a linear descendant of `main` and includes Product Shell,
  governed conversations, material intake, private retrieval, task loop and role journeys.
- Production PostgreSQL has the `009-014` activation structures.
- Production PostgreSQL does not have `hxy_product_tasks`,
  `hxy_product_training_sessions` or `parent_task_id`.
- The active API process runs from `/root/hxy`, whose worktree contains unrelated
  uncommitted changes. That directory is not a valid release source.
- Git push works, but the local GitHub CLI token is invalid. GitHub metadata is not a
  deployment dependency.

## Release Principles

1. Code is released from an immutable, clean release worktree at an exact commit.
2. Database migration and application activation are separate stop gates.
3. `015` and `016` run in one PostgreSQL transaction under an advisory lock.
4. A fresh, verified full database backup is mandatory before mutation.
5. Migration files are checksum-bound to the backup manifest.
6. Any failed check stops the release; no warning is converted into success manually.
7. Core knowledge, approval state and private source material are outside this release.
8. Rollback prefers application rollback while retaining additive database structures.

## Architecture

### Release Profile

The existing guarded activation release code becomes profile-driven while preserving its
current `009-014` defaults. A release profile defines:

```text
release id
backup manifest version
migration filenames
confirmation phrase
advisory lock name
required prerequisite structures
postflight inspection rules
backup output directory
```

The role-journeys profile uses:

```text
release: hxy-role-journeys-015-016
confirmation: APPLY-HXY-015-016
migrations:
  - 015_hxy_product_tasks.sql
  - 016_hxy_product_training.sql
```

### Commands

```text
preflight
backup
apply --backup-manifest ... --confirm APPLY-HXY-015-016
postflight
```

All command output is bounded JSON. Database credentials, full DSNs, private material and
session credentials are redacted.

### Preflight

Preflight is read-only and verifies:

- PostgreSQL major version 16;
- HXY-owned repository and database boundary;
- activation prerequisites from `009-014` exist;
- `staff_sessions.assignment_id` and its assignment constraint exist;
- exact checksums can be calculated for `015-016`;
- the target Git worktree is clean and at a real commit.

Existing task/training structures may be reported as already present. Their absence is the
normal first-release state and is not a preflight failure.

### Backup

Backup creates a private `0700` directory containing:

```text
hxy-before-role-journeys.dump
manifest.json
```

The dump is custom-format, `0600`, validated by `pg_restore --list` and recorded with size,
SHA-256, database identity, Git commit and migration checksums. A manifest is valid for at
most 24 hours.

### Apply

Apply requires the exact confirmation phrase. It revalidates the manifest and dump, then
runs both migrations with:

```text
ON_ERROR_STOP=1
--single-transaction
pg_advisory_xact_lock(...)
```

Failure in either migration rolls back both.

### Postflight

Postflight is read-only and verifies:

- task and task-event tables exist;
- product training table exists;
- `parent_task_id` exists;
- the parent-task foreign key includes organization and store;
- task events reject update/delete and truncate;
- training sessions reject update/delete and truncate;
- required organization/store/assignment foreign keys exist;
- relevant active-task and training indexes exist.

### Application Activation

The API and web build must come from the same clean release commit. The existing
`/root/hxy` worktree is not overwritten or cleaned. Activation must use a release worktree
or versioned release directory and update service configuration atomically.

Canary order:

```text
API health
founder session and question -> evidence -> task
manager visible task -> linked issue -> follow-up
employee answer -> practice -> correction -> issue
mobile viewport smoke
```

No production service is activated until database postflight passes.

## Error Handling

- Wrong confirmation: fail before any command runs.
- Missing or stale manifest: fail before migration.
- Checksum or database identity mismatch: fail before migration.
- Dirty release worktree: fail preflight.
- Migration SQL error: transaction rollback and stop.
- Postflight failure: stop before application activation.
- API or UI canary failure: restore previous service release path; retain additive schema.

Database restore is not an ordinary rollback. It requires a separate maintenance decision
because it may discard writes after the backup.

## Verification

Implementation must include:

- unit tests for release profile isolation and confirmation;
- backup manifest validation tests;
- command redaction tests;
- disposable PostgreSQL upgrade from current production shape through `015-016`;
- same-store parent acceptance and cross-store parent rejection;
- fresh migration `001-016` verification;
- full Python, web, build and Playwright suites;
- independent Critical/Important review before release.

## Non-Goals

- No public GitHub project description.
- No production deployment from a feature or dirty worktree.
- No automatic merge to `main` while GitHub authentication is invalid.
- No automatic approval or publication of knowledge.
- No changes to `/root/htops`.
- No automatic database restore.
