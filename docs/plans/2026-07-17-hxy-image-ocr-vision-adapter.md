# HXY Image OCR/Vision Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace image parser `PENDING_ADAPTER` results with a governed OCR + vision extraction path for inbox images and uploaded material jobs.

**Architecture:** A reusable image adapter validates and downsizes an image, runs optional local RapidOCR for literal text, then calls the existing HXY model router for visual/business understanding when the vision route is enabled. The adapter emits a non-authoritative Markdown reference and a parser-quality result; it never approves, publishes, or writes to the HXY formal knowledge layer. Both the source-registry parser runner and the product material worker use this adapter, while existing API upload understanding remains compatible.

**Tech Stack:** Python 3.12, Pillow, optional `rapidocr-onnxruntime`, existing `ModelRouter`/DashScope OpenAI-compatible chat completions, pytest, domestic PyPI mirror for deployment dependencies.

---

### Task 1: Add failing image-adapter contract tests

**Files:**
- Create: `tests/test_hxy_image_adapter.py`
- Modify: `tests/test_hxy_parser_adapter.py`
- Modify: `tests/test_hxy_material_parser.py`

**Step 1: Write the failing tests**

Cover these behaviors:

- a fake router receives a data URL and produces a structured non-authoritative image reference;
- local OCR text is retained and included in the reference;
- a vision model failure falls back to OCR with review quality;
- an inbox image job is `EXTRACTED`, not `PENDING_ADAPTER`, when the adapter succeeds;
- an uploaded image selects the image adapter instead of MarkItDown;
- source hash and source isolation rules remain enforced.

**Step 2: Run the focused tests to verify they fail**

Run: `pytest -q tests/test_hxy_image_adapter.py tests/test_hxy_parser_adapter.py tests/test_hxy_material_parser.py`

Expected: FAIL because the adapter module and image parser route do not exist yet.

### Task 2: Implement the reusable image adapter

**Files:**
- Create: `apps/api/hxy_knowledge/image_adapter.py`
- Modify: `apps/api/hxy_knowledge/parser_adapter.py`

**Step 1: Implement safe image preparation**

- Reject missing, non-file, oversized, and invalid images.
- Use Pillow to inspect dimensions and resize only the in-memory model payload.
- Never overwrite or move the original source.

**Step 2: Implement optional OCR**

- Detect `rapidocr_onnxruntime` without making the whole service unusable when the optional dependency is absent.
- Return OCR text and confidence metadata without treating OCR as truth.

**Step 3: Implement model understanding**

- Use the existing `ModelRouter` `vision_understanding` route.
- Send OCR as supporting evidence and request strict JSON fields: image type, visual summary, business summary, OCR, entities, prices, related domains, confidence, and review flag.
- Parse fenced or bare JSON defensively and discard malformed model output.

**Step 4: Implement quality and reference rendering**

- Prefer model understanding plus OCR when available.
- Fall back to OCR-only as review-quality extraction.
- Return `official_use_allowed=false` for every result.
- Render a bounded Markdown reference containing provenance, OCR, visual summary, business summary, and quality signals.

**Step 5: Route parser jobs through the adapter**

- Add `_run_vision_job` with the same source SHA-256 verification and isolated attempt boundary as other parsers.
- Remove the unconditional `PENDING_ADAPTER` branch.
- Include `ocr_or_vision` in default allowed strategies.
- Preserve exception statuses for missing dependencies, invalid images, model failures, and failed quality gates.

### Task 3: Connect uploaded material parsing

**Files:**
- Modify: `apps/api/hxy_product/material_parser.py`
- Modify: `apps/api/hxy_product/material_worker.py`
- Modify: `tests/test_hxy_material_worker.py`

**Step 1: Add image-aware parser selection**

- Detect common image extensions.
- Use the reusable adapter for images and MarkItDown for other material types.
- Keep `MaterialParseResult` and artifact governance unchanged.

**Step 2: Run focused tests and fix only production behavior**

Run: `pytest -q tests/test_hxy_image_adapter.py tests/test_hxy_material_parser.py tests/test_hxy_material_worker.py`

Expected: PASS with image parser metadata and non-authoritative artifacts.

### Task 4: Declare and install the optional OCR dependency

**Files:**
- Create: `apps/api/requirements-parser-vision.txt`
- Modify: `docs/operations/hxy-knowledge-service-runbook.md`

**Step 1: Pin the optional parser dependency**

Declare Pillow and RapidOCR with bounded versions. Keep them separate from the base API requirements so deployments that do not process images do not pay the dependency cost.

**Step 2: Install using a domestic mirror**

Run: `python -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r apps/api/requirements-parser-vision.txt`

Verify imports without printing environment values.

### Task 5: Run regression and real synthetic-image verification

**Files:**
- No source changes expected.

**Step 1: Run focused and full tests**

Run:

```bash
pytest -q tests/test_hxy_image_adapter.py tests/test_hxy_parser_adapter.py tests/test_hxy_material_parser.py tests/test_hxy_material_worker.py
pytest -q
```

Expected: all relevant tests pass and no authority or source-isolation tests regress.

**Step 2: Run a synthetic image through the real HXY route**

- Generate the image in memory only.
- Call `ModelRouter` with the HXY production environment.
- Report model, success, latency, and sanitized quality output only.
- Do not run the adapter across all inbox materials in this change.

**Step 3: Commit the implementation**

```bash
git add apps/api/hxy_knowledge/image_adapter.py apps/api/hxy_knowledge/parser_adapter.py apps/api/hxy_product/material_parser.py apps/api/hxy_product/material_worker.py apps/api/requirements-parser-vision.txt docs/operations/hxy-knowledge-service-runbook.md tests/test_hxy_image_adapter.py tests/test_hxy_parser_adapter.py tests/test_hxy_material_parser.py tests/test_hxy_material_worker.py
git commit -m "feat(knowledge): connect governed image OCR vision adapter"
```
