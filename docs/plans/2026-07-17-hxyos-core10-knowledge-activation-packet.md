# HXYOS Core-10 Knowledge Activation Packet Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a deterministic, read-only four-group activation packet that reduces the remaining Core-10 authority gaps to one founder review without applying any knowledge change.

**Architecture:** A pure packet builder consumes a captured Core-10 report plus typed, database-backed authority snapshots and private local drafts. A repository snapshot adapter resolves only explicitly selected asset ids, an artifact writer stores JSON/Markdown under `data/private`, and two read-only API endpoints expose a sanitized packet and validate decisions without mutation. No activation executor is included.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL repository adapter, Pydantic, pytest, canonical JSON SHA-256 fingerprints.

---

### Task 1: Pure Four-Group Packet Builder

**Files:**
- Create: `apps/api/hxy_knowledge/core10_activation.py`
- Create: `tests/test_hxy_core10_activation_packet.py`

**Step 1: Write the failing four-group contract test**

Add fixtures with placeholder content only. The report must contain the five
currently failing case ids, two selected source snapshots, one constitution
draft and one reception card draft.

```python
def test_build_packet_groups_five_failures_into_four_business_decisions() -> None:
    packet = build_core10_activation_packet(
        report=_core10_report(),
        constitution_state=_missing_constitution_state(),
        constitution_draft=_safe_constitution_draft(),
        product_sources=[_internal_candidate("asset-product")],
        operations_sources=[_internal_candidate("asset-operations")],
        reception_draft=_safe_reception_draft(),
        existing_answer_cards=[],
        generated_at="2026-07-17T00:00:00Z",
    )

    assert [item["item_key"] for item in packet["items"]] == [
        "brand_constitution",
        "product_system_sources",
        "first_store_operations_sources",
        "reception_standard_answer_card",
    ]
    assert packet["item_count"] == 4
    assert packet["write_to_database"] is False
    assert packet["publish_allowed"] is False
    assert not _contains_key(packet, "claim_id")
    assert not _contains_key(packet, "chunk_id")
```

Assert the case mapping exactly:

```python
assert _affected(packet, "brand_constitution") == ["core-brand-identity"]
assert _affected(packet, "product_system_sources") == ["core-product-system"]
assert _affected(packet, "first_store_operations_sources") == [
    "core-next-action",
    "core-operating-decision",
]
assert _affected(packet, "reception_standard_answer_card") == ["core-citation"]
```

**Step 2: Run the test to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_packet.py::test_build_packet_groups_five_failures_into_four_business_decisions -q
```

Expected: FAIL because `hxy_knowledge.core10_activation` does not exist.

**Step 3: Implement the minimal packet contract**

Create constants and a pure builder:

```python
PACKET_VERSION = "hxyos-core10-activation-packet.v1"
DECISION_OPTIONS = ("approve", "reject", "request_correction")
GROUP_CASES = {
    "brand_constitution": ("core-brand-identity",),
    "product_system_sources": ("core-product-system",),
    "first_store_operations_sources": (
        "core-operating-decision",
        "core-next-action",
    ),
    "reception_standard_answer_card": ("core-citation",),
}

def build_core10_activation_packet(
    *,
    report: dict[str, Any],
    constitution_state: dict[str, Any],
    constitution_draft: dict[str, Any] | None,
    product_sources: list[dict[str, Any]],
    operations_sources: list[dict[str, Any]],
    reception_draft: dict[str, Any] | None,
    existing_answer_cards: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    ...
```

Every group must include `current_state`, `proposed_authority`,
`source_evidence`, `why_needed`, `affected_core10_cases`,
`risk_if_approved`, `risk_if_rejected`, `exact_write_intents`, `blockers`,
`decision_options`, `official_use_allowed=False`, and `write_allowed=False`.

Do not import FastAPI or call a repository from this module.

**Step 4: Run the focused test to verify GREEN**

Run the command from Step 2.

Expected: PASS.

**Step 5: Add blocker and write-intent tests**

```python
@pytest.mark.parametrize(
    ("mutation", "group_key", "blocker_code"),
    [
        ("missing_constitution", "brand_constitution", "missing_constitution_draft"),
        ("external_product", "product_system_sources", "external_source_not_eligible"),
        ("missing_operations", "first_store_operations_sources", "missing_source_selection"),
        ("unsafe_reception", "reception_standard_answer_card", "unsafe_answer_wording"),
    ],
)
def test_packet_fails_closed_per_group(mutation, group_key, blocker_code):
    ...
```

Assert source write intents contain only:

```text
operation=classify_source_authority
asset_id
expected_previous_version
source_origin=internal
source_authority=internal_material
reason
payload_sha256
```

Assert no intent contains SQL, commands, credentials, absolute paths or
`write_allowed=true`.

**Step 6: Run all packet-builder tests**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_packet.py -q
```

Expected: PASS.

**Step 7: Commit**

```bash
git add apps/api/hxy_knowledge/core10_activation.py tests/test_hxy_core10_activation_packet.py
git commit -m "feat: build core10 activation packet"
```

### Task 2: Canonical Fingerprints And Preview-Only Decisions

**Files:**
- Modify: `apps/api/hxy_knowledge/core10_activation.py`
- Modify: `tests/test_hxy_core10_activation_packet.py`

**Step 1: Write failing fingerprint tests**

```python
def test_packet_identity_is_stable_when_only_generated_at_changes() -> None:
    first = _build(generated_at="2026-07-17T00:00:00Z")
    second = _build(generated_at="2026-07-17T01:00:00Z")
    assert first["packet_id"] == second["packet_id"]
    assert first["packet_fingerprint"] == second["packet_fingerprint"]

def test_source_authority_version_changes_packet_and_item_fingerprints() -> None:
    first = _build()
    second = _build(product_authority_version=2)
    assert first["packet_fingerprint"] != second["packet_fingerprint"]
    assert _item(first, "product_system_sources")["item_fingerprint"] != (
        _item(second, "product_system_sources")["item_fingerprint"]
    )
```

**Step 2: Run fingerprint tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_packet.py -q -k fingerprint
```

Expected: FAIL because canonical fingerprints are incomplete.

**Step 3: Implement canonical fingerprints**

Use sorted, compact UTF-8 JSON. Exclude only volatile fields such as
`generated_at` from packet identity. Include all current authority versions,
draft digests, existing-card snapshots and exact write intents.

```python
def json_fingerprint(payload: Any) -> dict[str, str]:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {"algorithm": "sha256", "digest": hashlib.sha256(canonical).hexdigest()}
```

**Step 4: Write failing decision-validation tests**

```python
def test_validate_decisions_accepts_independent_group_actions_without_writes() -> None:
    packet = _build()
    result = validate_core10_activation_decisions(
        packet,
        _decisions_for(packet, actions={
            "brand_constitution": "approve",
            "product_system_sources": "approve",
            "first_store_operations_sources": "request_correction",
            "reception_standard_answer_card": "reject",
        }),
    )
    assert result["valid"] is True
    assert result["write_to_database"] is False
    assert result["publish_allowed"] is False

def test_validate_decisions_rejects_stale_or_blocked_approval() -> None:
    ...
```

Require actor role `founder`, actor id, reason, packet id, packet fingerprint,
item key and item fingerprint. Unknown, duplicate or missing item decisions fail.
An approval on an item with blockers fails. Reject and request-correction remain
valid for blocked items.

**Step 5: Run decision tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_packet.py -q -k decision
```

Expected: FAIL because validation is not implemented.

**Step 6: Implement preview-only decision validation**

Add:

```python
def validate_core10_activation_decisions(
    packet: dict[str, Any],
    decisions: dict[str, Any] | None,
) -> dict[str, Any]:
    ...
```

The return value must always include:

```json
{
  "preview_only": true,
  "write_to_database": false,
  "publish_allowed": false,
  "official_use_allowed": false
}
```

Do not accept callbacks or repository objects in this function.

**Step 7: Run packet tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_packet.py -q
```

Expected: PASS.

```bash
git add apps/api/hxy_knowledge/core10_activation.py tests/test_hxy_core10_activation_packet.py
git commit -m "feat: validate core10 activation decisions"
```

### Task 3: Database-Backed Read Snapshot

**Files:**
- Modify: `apps/api/hxy_knowledge/repository.py`
- Create: `tests/test_hxy_core10_activation_repository.py`

**Step 1: Write failing repository tests**

Use the existing PostgreSQL repository test pattern. Prove that selected asset
ids return their database-backed source origin, source authority and authority
version plus bounded source evidence.

```python
def test_activation_snapshot_resolves_only_explicit_asset_ids(postgres_repo) -> None:
    snapshot = postgres_repo.core10_activation_snapshot(
        product_asset_ids=["asset-product"],
        operations_asset_ids=["asset-operations"],
    )
    assert [item["asset_id"] for item in snapshot["product_sources"]] == ["asset-product"]
    assert snapshot["product_sources"][0]["source_authority"] == "external_reference"
    assert snapshot["product_sources"][0]["authority_version"] == 1
    assert "unselected-asset" not in json.dumps(snapshot)
```

Also assert that a chunk metadata field claiming `official_internal` cannot
override the parent asset authority.

**Step 2: Run repository tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_repository.py -q
```

Expected: FAIL because `core10_activation_snapshot` does not exist.

**Step 3: Implement the bounded read method**

Add:

```python
def core10_activation_snapshot(
    self,
    *,
    product_asset_ids: list[str],
    operations_asset_ids: list[str],
    evidence_limit_per_asset: int = 3,
    excerpt_chars: int = 360,
) -> dict[str, Any]:
    ...
```

Rules:

- reject duplicate ids and more than 20 total ids;
- use parameterized SQL;
- preserve caller order;
- raise `LookupError` listing unknown ids;
- read authority only from `hxy_knowledge_assets`;
- bound evidence count and excerpt length;
- return repository answer cards with `status='approved'` for conflict checks;
- perform no INSERT, UPDATE or DELETE.

**Step 4: Run repository tests and authority regression**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_repository.py tests/test_hxy_global_source_authority.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/repository.py tests/test_hxy_core10_activation_repository.py
git commit -m "feat: read core10 activation authority snapshot"
```

### Task 4: Private Artifact Writer And CLI

**Files:**
- Modify: `apps/api/hxy_knowledge/core10_activation.py`
- Create: `scripts/build-hxy-core10-activation-packet.py`
- Create: `tests/test_hxy_core10_activation_cli.py`
- Modify: `.gitignore`

**Step 1: Write failing artifact tests**

```python
def test_write_artifacts_keeps_private_content_under_ignored_data_path(tmp_path: Path) -> None:
    paths = write_core10_activation_artifacts(tmp_path, _build())
    assert paths["packet_json"].name == "packet.json"
    assert paths["packet_markdown"].name == "packet.md"
    assert paths["decision_sample"].name == "decisions.sample.json"
    assert paths["packet_json"].parent.name.startswith("core10-activation-")
```

Assert Markdown is business-facing and contains no claim/chunk ids, absolute
paths, credentials or executable write commands. Simulate an `os.replace`
failure and assert no partial target directory replaces a prior complete packet.

**Step 2: Run artifact tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_cli.py -q
```

Expected: FAIL because writer and CLI do not exist.

**Step 3: Implement renderer and atomic writer**

Add:

```python
def render_core10_activation_packet_markdown(packet: dict[str, Any]) -> str:
    ...

def build_core10_activation_decision_sample(packet: dict[str, Any]) -> dict[str, Any]:
    ...

def write_core10_activation_artifacts(
    private_root: Path,
    packet: dict[str, Any],
) -> dict[str, Path]:
    ...
```

Write a complete temporary directory, fsync files, and atomically rename it to
`data/private/core10-activation/core10-activation-<digest-prefix>/`.

Ensure `.gitignore` covers `data/private/` without weakening existing public
release checks.

**Step 4: Implement the CLI around explicit private inputs**

The CLI accepts:

```text
--report <captured Core-10 report>
--selection <private JSON containing selected asset ids and draft paths>
--output-root <default data/private/core10-activation>
--database-url-env <default HXY_DATABASE_URL>
```

The selection file contains only:

```json
{
  "constitution_draft_path": "data/private/...json",
  "product_asset_ids": [],
  "operations_asset_ids": [],
  "reception_draft_path": "data/private/...json"
}
```

Reject paths outside the project `data/private` directory. Never print source
content or a database URL. Print only packet id, item statuses and relative
artifact paths.

**Step 5: Run CLI tests and public-release guardrails**

Run:

```bash
.venv/bin/pytest tests/test_hxy_core10_activation_cli.py tests/test_hxy_public_release_guardrails.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add .gitignore apps/api/hxy_knowledge/core10_activation.py scripts/build-hxy-core10-activation-packet.py tests/test_hxy_core10_activation_cli.py
git commit -m "feat: write private core10 activation artifacts"
```

### Task 5: Read-Only API And Decision Preview

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing API tests**

Add tests for:

```text
GET  /api/operating-brain/core10-activation-packet
POST /api/operating-brain/core10-activation-decision-preview
```

```python
def test_core10_activation_packet_endpoint_returns_sanitized_latest_packet(client, tmp_path):
    response = client.get("/api/operating-brain/core10-activation-packet")
    assert response.status_code == 200
    body = response.json()
    assert body["write_to_database"] is False
    assert body["item_count"] == 4
    assert "/root/" not in json.dumps(body)

def test_decision_preview_never_calls_repository_write(client, repository):
    response = client.post(
        "/api/operating-brain/core10-activation-decision-preview",
        json=_valid_decisions(),
        headers=_founder_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["preview_only"] is True
    assert repository.write_calls == []
```

Missing packet returns a safe missing response, not a synthetic packet.
Decision preview requires existing API authentication and a founder role.

**Step 2: Run API tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_knowledge_api.py -q -k core10_activation
```

Expected: FAIL with 404 because routes do not exist.

**Step 3: Implement Pydantic request and safe packet loading**

Add a strict decision-preview request model with `extra="forbid"`. Load only
directories matching `core10-activation-[a-f0-9]{12}` under
`data/private/core10-activation`, parse complete `packet.json` files, and choose
the latest valid `generated_at`. Do not follow user-controlled paths.

Sanitize evidence to:

```text
asset_id
title
source_path (project-relative only)
source_origin
source_authority
authority_version
excerpt (bounded)
```

**Step 4: Implement endpoints**

The GET endpoint is read-only. The POST endpoint calls only
`validate_core10_activation_decisions`. It must not call source classification,
answer-card creation, constitution publication or any repository write method.

**Step 5: Run focused API and security tests**

Run:

```bash
.venv/bin/pytest tests/test_hxy_knowledge_api.py tests/test_hxy_answer_authority.py -q -k 'core10_activation or authority'
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: expose core10 activation preview API"
```

### Task 6: Full Verification And Local Packet Dry Run

**Files:**
- Modify only if verification exposes a defect in the files above.
- Create locally ignored input: `data/private/core10-activation/selection.json`
- Create locally ignored drafts under `data/private/core10-activation/drafts/`

**Step 1: Run formatting and focused tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_hxy_core10_activation_packet.py \
  tests/test_hxy_core10_activation_repository.py \
  tests/test_hxy_core10_activation_cli.py \
  tests/test_hxy_knowledge_api.py -q
```

Expected: PASS.

**Step 2: Run full Python regression**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all tests pass with only existing documented skips/warnings.

**Step 3: Run web regression**

Run:

```bash
npm test
```

Expected: PASS.

**Step 4: Run public-release checks**

Run:

```bash
.venv/bin/python scripts/check-hxy-public-release.py
```

Expected: `code_only_private_knowledge_local` and no private activation artifact
is Git-eligible.

**Step 5: Generate one local packet without applying writes**

Prepare private placeholder-to-real drafts and the explicit source selection
outside Git, then run:

```bash
.venv/bin/python scripts/build-hxy-core10-activation-packet.py \
  --report /root/hxy/data/releases/authority-answer/core-10-report-dev.json \
  --selection data/private/core10-activation/selection.json
```

Expected output:

```text
item_count=4
write_to_database=false
publish_allowed=false
```

Do not classify any source, create an answer card, activate a constitution or
apply migration 019.

**Step 6: Re-run Core-10 and prove no artificial score change**

Run the existing candidate capture and report commands against a disposable
candidate database.

Expected:

```text
authority_leakage_failures=0
high_risk_interception_rate=1.0
pass_rate remains the pre-activation value
```

Packet generation is not allowed to improve the benchmark because no approved
decision has been applied.

**Step 7: Review the implementation**

Use `superpowers:requesting-code-review` and verify:

- no write path is reachable from packet generation or decision preview;
- no claim-level review has reappeared;
- private content remains out of Git;
- source versions and packet fingerprints fail stale;
- `/root/htops` is untouched;
- migration 019 remains unapplied in production.

**Step 8: Commit verification-only corrections if needed**

```bash
git add <only corrected implementation and test files>
git commit -m "fix: harden core10 activation preview"
```
