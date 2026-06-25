# HXY Brain v1.1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add targeted OCR, an executive brain report, and local search to the HXY knowledge base.

**Architecture:** Keep all artifacts local and file-based. Add small Python scripts that consume the existing inbox manifest/search index and write additive outputs under `knowledge/structured`, `knowledge/reports`, and `data/exports`.

**Tech Stack:** Python 3.12, Pillow, RapidOCR when available, jq for verification, existing Markdown/JSON knowledge artifacts.

---

### Task 1: Add Targeted OCR Script

**Files:**
- Create: `scripts/ocr-hxy-key-images.py`
- Read: `knowledge/structured/hxy-inbox-manifest-inbox-2026-06-11.json`
- Write: `knowledge/structured/ocr/hxy-key-image-ocr-inbox-2026-06-11.json`
- Write: `knowledge/structured/ocr/normalized/*.md`

**Steps:**

1. Select image assets from the manifest.
2. Include paths containing `参考品牌` or `荷小悦相关`.
3. Exclude paths containing `hxyip` unless dimensions indicate a long screenshot.
4. Resize images to a safe OCR width.
5. Slice long images vertically.
6. Run RapidOCR if installed.
7. Write JSON and Markdown sidecars.
8. Add summary counts: selected, processed, text_found, skipped, failed.

**Verification:**

Run:

```bash
python3 -m py_compile scripts/ocr-hxy-key-images.py
python3 scripts/ocr-hxy-key-images.py --root /root/hxy --run-name inbox-2026-06-11 --limit 12
jq empty knowledge/structured/ocr/hxy-key-image-ocr-inbox-2026-06-11.json
```

Expected: script exits 0, JSON is valid, OCR report has at least one asset with `line_count > 0`.

### Task 2: Add Brain Report Builder

**Files:**
- Create: `scripts/build-hxy-brain-report.py`
- Read: `knowledge/structured/hxy-inbox-manifest-inbox-2026-06-11.json`
- Read: `knowledge/structured/hxy-inbox-search-index-inbox-2026-06-11.json`
- Optionally read: `knowledge/structured/ocr/hxy-key-image-ocr-inbox-2026-06-11.json`
- Write: `knowledge/reports/HXY-BRAIN.md`
- Write: `knowledge/structured/hxy-brain-summary.json`

**Steps:**

1. Load manifest, search index, and OCR JSON if present.
2. Group assets by domain and stage.
3. Extract evidence snippets by keyword sets:
   - positioning: `定位`, `核爆点`, `战场`, `购买理由`
   - product: `泡脚`, `按摩`, `菜单`, `SPU`, `SKU`
   - store model: `小店模型`, `单店`, `回本`, `坪效`
   - competitor: `奈晚`, `谷小推`, `长风拨筋`, `帮大爷`
   - finance: `投资`, `成本`, `毛利`, `回本`, `融资`
   - technology: `O2O`, `小程序`, `AI`, `数据`, `支付`
   - franchise: `连锁`, `加盟`, `万店`
4. Render concise Markdown with source references.
5. Include open review backlog for images and low-confidence extraction.

**Verification:**

Run:

```bash
python3 -m py_compile scripts/build-hxy-brain-report.py
python3 scripts/build-hxy-brain-report.py --root /root/hxy --run-name inbox-2026-06-11
test -s knowledge/reports/HXY-BRAIN.md
jq empty knowledge/structured/hxy-brain-summary.json
rg -n "小店模型|奈晚|万店|泡脚|回本" knowledge/reports/HXY-BRAIN.md
```

Expected: report and JSON exist; known terms appear.

### Task 3: Add Local Search Tool

**Files:**
- Create: `scripts/search-hxy-knowledge.py`
- Read: `knowledge/structured/hxy-inbox-search-index-inbox-2026-06-11.json`
- Read: `knowledge/structured/ocr/hxy-key-image-ocr-inbox-2026-06-11.json` when present

**Steps:**

1. Accept query terms.
2. Support `--domain`, `--stage`, `--limit`.
3. Score exact and partial keyword matches.
4. Print title, source path, domain, stage, and snippet.
5. Include OCR text as a secondary source when available.

**Verification:**

Run:

```bash
python3 -m py_compile scripts/search-hxy-knowledge.py
python3 scripts/search-hxy-knowledge.py 泡脚 --limit 5
python3 scripts/search-hxy-knowledge.py 小店模型 --domain store_model --limit 5
python3 scripts/search-hxy-knowledge.py 奈晚 --domain competitor --limit 5
```

Expected: relevant source paths and snippets are printed.

### Task 4: Final Validation

**Steps:**

1. Run syntax checks for all three scripts.
2. Run targeted OCR with a bounded limit.
3. Build the brain report.
4. Run search smoke tests.
5. Verify no output references `/root/htops` except boundary warnings.

**Verification:**

Run:

```bash
python3 -m py_compile scripts/ingest-hxy-inbox-knowledge.py scripts/ocr-hxy-key-images.py scripts/build-hxy-brain-report.py scripts/search-hxy-knowledge.py
jq empty knowledge/structured/hxy-inbox-manifest-inbox-2026-06-11.json
jq empty knowledge/structured/hxy-inbox-search-index-inbox-2026-06-11.json
find knowledge/raw/classified/inbox-2026-06-11 -type l | wc -l
find -L knowledge/raw/classified/inbox-2026-06-11 -type l | wc -l
rg -n "/root/htops" knowledge/structured/hxy-inbox-manifest-inbox-2026-06-11.json knowledge/structured/hxy-inbox-search-index-inbox-2026-06-11.json knowledge/reports/HXY-BRAIN.md || true
```

Expected: syntax ok, JSON ok, classified links count is 140, broken links count is 0, and no business-data references to htops.
