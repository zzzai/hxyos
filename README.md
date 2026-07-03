# HXYOS Public Scaffold

HXYOS is an organization memory and knowledge-governance scaffold for building an enterprise AI operating system.

This public repository contains reusable engineering pieces only:

- knowledge compilation into extracts, candidate claims, review queues, and draft answer cards
- memory-context budgeting with process-memory governance
- loop runners with hard stop conditions and human-review gates
- model routing metadata that never exposes credentials by default
- workspace event logging with sensitive-content redaction

It intentionally does not contain private brand knowledge, source documents, raw materials, compiled local wiki pages, seeds, run reports, environment files, or production backups.

## Public vs Private

Public code:

```text
apps/api/hxy_knowledge/     # reusable Python modules
scripts/                    # local CLI runners
tests/                      # generic fixtures only
knowledge/examples/         # safe sample material
```

Private local material, excluded from Git:

```text
knowledge/raw/
knowledge/normalized/
knowledge/structured/
knowledge/wiki/
knowledge/runs/
knowledge/reports/
knowledge/okf/core/
data/seeds/
data/backups/
ops/env/*.env
```

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r apps/api/requirements.txt
pytest
```

Run the sample ingest loop:

```bash
python scripts/run-hxy-ingest-loop.py \
  --root-dir . \
  --raw-dir knowledge/examples/raw \
  --wiki-dir /tmp/hxyos-public-sample/wiki \
  --report /tmp/hxyos-public-sample/report.json \
  --runs-dir /tmp/hxyos-public-sample/runs \
  --run-id sample-ingest
```

The loop stops at `review_required`. It does not publish approved knowledge automatically.

## Governance Rules

1. Raw and reference material is not authority.
2. Process memory is only a context hint.
3. AI-generated extracts, claims, and answer-card drafts require human review.
4. Approved knowledge must have source, owner, version, scope, and review status.
5. Secrets and private business material stay outside the public repo.

