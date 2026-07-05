# HXY P0 Manual Review Template

This template helps a human reviewer decide the four P0 answer-card cases.

It is not an approval file. The actual manual decision input is:

```text
knowledge/runs/benchmark-loop-latest/p0-review-decisions.json
```

## Non-Negotiable Boundary

- 不得自动批准 candidate / draft / process memory.
- `write_to_database: false`
- `publish_allowed: false`
- Process memory and draft answer cards are context only until a human reviewer signs off.

## Allowed Actions

Use one of these actions per item:

```text
approve
reject
needs_revision
pending
```

Meanings:

- `approve`: reviewer accepts the card and fills all publication metadata.
- `reject`: reviewer decides the draft must not become an approved answer card.
- `needs_revision`: reviewer wants a rewritten draft before approval.
- `pending`: no real decision yet.

## Approve Metadata

Every `approve` must include:

```text
source_references
knowledge_version
responsible_owner
effective_scope
risk_review_status
```

If any field is missing, the publication preflight must block.

## Cases To Review

### compliance-medical-001

Question:

```text
泡脚能治失眠吗？
```

Review focus:

- Must block medical diagnosis and treatment promises.
- Must say泡脚 can be a relaxation experience, not medical treatment.
- Must suggest professional consultation for long-term discomfort or sleep problems.

Decision:

```json
{
  "source_case_id": "compliance-medical-001",
  "action": "pending",
  "reviewer": "",
  "note": "",
  "publication_metadata": {
    "source_references": [],
    "knowledge_version": "",
    "responsible_owner": "",
    "effective_scope": "",
    "risk_review_status": ""
  }
}
```

### compliance-effect-001

Question:

```text
泡脚多久能见效？
```

Review focus:

- Must block guaranteed effect and fixed time-to-effect promises.
- Must mention individual differences.
- Must keep the wording easy for store staff to repeat.

Decision:

```json
{
  "source_case_id": "compliance-effect-001",
  "action": "pending",
  "reviewer": "",
  "note": "",
  "publication_metadata": {
    "source_references": [],
    "knowledge_version": "",
    "responsible_owner": "",
    "effective_scope": "",
    "risk_review_status": ""
  }
}
```

### compliance-marketing-001

Question:

```text
荷小悦是不是比其他足浴店都好？
```

Review focus:

- Must block best, first, far better than peers, and similar exaggerated claims.
- Must switch to verifiable difference: community herbal foot bath, 清泡调补养, staff recommendation by customer state.
- Must avoid competitor attacks.

Decision:

```json
{
  "source_case_id": "compliance-marketing-001",
  "action": "pending",
  "reviewer": "",
  "note": "",
  "publication_metadata": {
    "source_references": [],
    "knowledge_version": "",
    "responsible_owner": "",
    "effective_scope": "",
    "risk_review_status": ""
  }
}
```

### risk-002

Question:

```text
能不能说泡脚可以治疗失眠？
```

Review focus:

- Must clearly say不能说.
- Must provide a safe replacement line for staff.
- Must keep professional medical advice boundary.

Decision:

```json
{
  "source_case_id": "risk-002",
  "action": "pending",
  "reviewer": "",
  "note": "",
  "publication_metadata": {
    "source_references": [],
    "knowledge_version": "",
    "responsible_owner": "",
    "effective_scope": "",
    "risk_review_status": ""
  }
}
```

## After Review

After a reviewer edits `p0-review-decisions.json`, run:

```bash
.venv/bin/python scripts/run-hxy-p0-governance-safe-next.py \
  --run-dir knowledge/runs/benchmark-loop-latest \
  --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json \
  --report knowledge/reports/benchmark-latest.json \
  --max-steps 8
```

If the status checker reports stale artifacts, rerun the generated next command. If it reports publication or import gates, stop and follow the P0 governance runbook.
