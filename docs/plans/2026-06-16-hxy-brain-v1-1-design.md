# HXY Brain v1.1 Design

## Goal

Build the next practical version of the 荷小悦智慧大脑 so uploaded knowledge is not only stored and classified, but also easier to search, inspect, and convert into operating decisions.

## Current State

The inbox ingestion pipeline already indexes 140 uploaded files from `knowledge/raw/inbox`, creates normalized Markdown, generates a manifest, writes search chunks, and produces a human report. Text-first assets are usable. Image assets are classified and represented by metadata/contact sheets, but full image OCR is too slow when run against every screenshot.

## Scope

HXY Brain v1.1 adds three focused capabilities:

1. Targeted OCR for high-value images.
2. A structured brain report that consolidates strategy, product, store model, competitor, finance, technology, and franchise knowledge.
3. A local search tool for fast command-line lookup across normalized files and structured chunks.

## Architecture

Keep this local-first and file-based. Source files stay under `knowledge/raw/inbox`. Derived artifacts stay in HXY-owned directories:

- `knowledge/structured/ocr/` for OCR outputs.
- `knowledge/reports/HXY-BRAIN.md` for the executive knowledge map.
- `scripts/search-hxy-knowledge.py` for local retrieval.

The ingestion script remains the canonical manifest/search-index builder. The new scripts read existing manifest/index files and create additive artifacts, avoiding movement or mutation of original uploads.

## OCR Strategy

Do not OCR every image by default. Select candidates by path, dimensions, and source context:

- Include: `参考品牌`, long screenshots, files likely to contain menu/price/store-material text.
- Include: key HXY strategic screenshot images under `荷小悦相关`.
- Exclude by default: `hxyip` character images and obvious pure photos unless they are long screenshots.

OCR is best-effort. Long images are resized and sliced. Results include line text, confidence, source path, dimensions, warnings, and extracted normalized Markdown sidecars.

## Brain Report Strategy

`HXY-BRAIN.md` should be a working executive map, not a long archive dump. It should include:

- Knowledge coverage snapshot.
- Core strategic positioning evidence.
- Product/service system.
- Store model and financial model.
- Competitor evidence.
- Technology/O2O/AI operating system.
- Franchise/scale strategy.
- Open questions and review backlog.

The report should cite source paths from the manifest so conclusions remain traceable.

## Search Strategy

The search tool should support:

- Keyword query.
- Optional domain filter.
- Optional stage filter.
- Configurable limit.
- Snippets from normalized/search chunks.

It should work with Python standard library only.

## Validation

Validation requires:

- Python syntax checks for scripts.
- JSON validity checks for generated structured artifacts.
- Nonzero OCR output for selected image candidates.
- Search returns relevant results for known terms: `泡脚`, `小店模型`, `奈晚`, `回本`, `万店`.
- `HXY-BRAIN.md` exists and references real source paths.

## Boundary

All outputs stay under `/root/hxy`. No HXY knowledge artifacts are written to `/root/htops`.
