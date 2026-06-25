# HXY Enterprise Answer Engine Plan

## Product Goal

Upgrade the HXY knowledge base from document search to an enterprise answer engine.

The system should turn HXY's scattered documents into verifiable operating judgment:

- Give a direct conclusion first.
- Explain why the conclusion is reasonable.
- Cite evidence from source documents.
- Identify conflicts, weak evidence, and missing facts.
- Suggest next actions.
- Capture user feedback so answers can improve.

## Value By Role

| Role | Value | Primary Output |
| --- | --- | --- |
| Founder / CEO | strategic judgment and alignment | positioning, trade-offs, risks |
| Product manager | product structure and priority | product architecture, SKU/SPU logic, roadmap |
| Brand / marketing | consistent narrative and content | positioning language, claims, source-backed talking points |
| Operations / store team | reusable SOP and training answers | standard actions, scripts, escalation guidance |
| Franchise / financing | credible business story | model logic, numbers, evidence, objections |
| AI / tech team | governed knowledge substrate | claims, evidence, conflicts, feedback data |

## Answer Contract

`POST /api/knowledge/chat` should return:

```json
{
  "question": "string",
  "query": "string",
  "intent": "brand_positioning | product_system | operations | finance | franchise | store_model | knowledge_lookup | unknown",
  "audience": "founder | product | brand | operations | franchise | general",
  "answer": "direct conclusion",
  "reasoning": ["why"],
  "evidence": [
    {
      "title": "source title",
      "source_path": "knowledge/raw/inbox/...",
      "excerpt": "short evidence",
      "strength": "high | medium | low"
    }
  ],
  "conflicts": ["conflicting or weak points"],
  "corrections": ["how the user question should be reframed"],
  "confidence": "high | medium | low",
  "next_actions": ["what to do next"],
  "needs_review": true
}
```

## V1 Implementation

V1 remains local-first and deterministic. It does not pretend to be a hosted LLM.

1. Intent routing from question text and retrieved domains.
2. Evidence retrieval from PostgreSQL.
3. Answer synthesis from weighted evidence snippets.
4. Confidence scoring from number and diversity of sources.
5. Conflict detection using simple contradiction signals and duplicate strategy phrases.
6. Correction prompts when questions are vague, too broad, or asking for unavailable facts.
7. Feedback persistence for answer quality and future tuning.

## Database Additions

- `hxy_knowledge_answer_runs`: question, intent, answer JSON, confidence, evidence count.
- `hxy_knowledge_feedback`: user feedback on answer quality, correction notes.

## Frontend Changes

`apps/admin-web/brain.html` becomes the user-facing answer surface:

- Direct conclusion area.
- Reasoning bullets.
- Evidence cards.
- Conflict / correction panel.
- Next action panel.
- Feedback buttons.

`apps/admin-web/knowledge.html` remains the admin surface:

- upload
- import
- search
- asset status

## Verification

- Unit tests for intent classification and structured answer shape.
- API tests for `/api/knowledge/chat` and `/api/knowledge/feedback`.
- Migration applies with `ON_ERROR_STOP=1`.
- Runtime HTTP test returns structured answer for:
  - `荷小悦的品牌定位是什么`
  - `泡脚方是什么`
  - `清泡调补养产品体系怎么讲`
- Frontend page renders structured answer fields.
