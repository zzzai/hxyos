# HXY Decision Log Baseline

## Goal

Turn the HXY project knowledge base from raw claim extraction into an auditable project brain baseline:

`raw project material -> claims/evidence -> governance candidates -> compact decision log -> validation queue`

The decision log is not a second ontology runtime. It sits after the existing HXY knowledge factory and governance report, and it records the current best project decisions with source evidence and validation plans.

## Scope

- Add `hxy-decision-log.v1` as a generated artifact under `knowledge/hxy/structured`.
- Keep governance candidate selection conservative:
  - prefer current, concise, auditable project decisions
  - reject long future-strategy fragments as current positioning
  - separate product menu, store model, customer segment, franchise model, and data/AI model candidates
- Render compact decision statements while preserving original evidence snippets.

## Current Decision Keys

- `current_positioning`
- `brand_asset`
- `product_menu`
- `store_model`
- `customer_segment`
- `franchise_model`
- `data_ai_model`

## Verification

Target checks:

```bash
npx vitest run src/hxy-decision-log.test.ts src/hxy-knowledge-governance.test.ts src/hxy-knowledge-extractor.test.ts src/hxy-knowledge-factory.test.ts src/personal-knowledge.test.ts src/hxy-knowledge-taxonomy.test.ts
npx tsc --noEmit
node --import tsx scripts/build-hxy-knowledge-governance.ts
node --import tsx scripts/build-hxy-decision-log.ts
```

## Next

- Add human approval status for each decision.
- Add superseded/active/retired lifecycle for conflicting strategic directions.
- Feed the decision log into the HXY personal knowledge assistant as high-priority project context.
