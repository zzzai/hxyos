# HXY GitHub Public Release Checklist

**Rule:** 项目代码可以上传 GitHub；品牌知识留在本地。

This checklist is the gate before publishing HXY code or the sanitized HXYOS public scaffold.

## Never Publish

Keep these local-only:

```text
knowledge/raw/
knowledge/normalized/
knowledge/structured/
knowledge/wiki/
knowledge/runs/
knowledge/reports/
knowledge/okf/core/
data/seeds/
data/product-materials/
data/backups/
data/exports/
quarantine/
ops/env/*.env
ops/env/*.toml
```

Also never publish:

- real API keys, database passwords, tokens, cookies, private keys;
- sensitive SQL dumps or backups;
- internal brand strategy source files;
- customer, order, member, technician, store, finance, or operating data;
- unreviewed raw WeChat articles, PDFs, books, meeting notes, images, or competitor screenshots.

## Publishable Material

Allowed:

- reusable source code under HXY-owned directories;
- generic tests and fixtures;
- secret-free `.env.example` and `.toml.example` files;
- sanitized docs that describe architecture, operations, and governance;
- generated public scaffold from `scripts/export-hxyos-public.py`.

## Required Local Checks

Run before any GitHub push or public export:

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
npm test
```

For sanitized public scaffold export:

```bash
python3 scripts/export-hxyos-public.py --target /tmp/hxyos-public
```

Only push the generated `/tmp/hxyos-public` repository after its own verification passes.

## GitHub CI Gate

The repository CI must run:

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
npm test
```

CI is a release gate, not a replacement for local review. If a file contains real brand knowledge or internal operating data, do not rely on redaction after the fact; keep it out of Git.

## Model And Database Secrets

- `ops/env/hxy-postgres.env` is local-only.
- `HXY_MODEL_API_KEY` must be issued and revoked in the provider console.
- New model keys must never be pasted into docs, commits, issues, or chat.
- Database passwords must remain in ignored env files or managed secret storage.

## Final Human Review

Before pushing:

1. Confirm `git status --short` contains no private knowledge paths.
2. Confirm CI files exist under `.github/workflows/`.
3. Confirm `python3 scripts/check-hxy-secrets.py` passes.
4. Confirm `python3 scripts/check-hxy-public-release.py` passes.
5. Confirm `npm test` passes.
6. Confirm the target repo does not include raw business materials.
