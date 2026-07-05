# HXY Brand Decision Loop V1 Design

## Purpose

Brand Decision Loop V1 is the first-store brand execution gate for HXYOS.

It does not design HXY VI or store SI. A professional design company owns VI, SI, storefront visual design, spatial identity, materials, typography, color, and construction-grade visual specifications.

HXYOS owns the operating acceptance layer:

```text
Does the brand output help the first store open, explain itself, convert first-time customers, avoid compliance risk, and create reusable learning?
```

The loop converts opening-stage brand actions into governed review artifacts. It gives scores, reasons, risk flags, rewrite directions, and decision records. It does not approve official brand standards automatically.

## Current Context

The inbox already contains a large set of HXY reference materials:

- brand strategy files;
- first-store and store-model files;
- marketing books and reading notes;
- STAG / scenario-marketing notes;
- HXY brand expression checklist;
- first-store growth experiment template;
- future VI/SI documents to be uploaded later.

Current HXYOS already has:

- knowledge ingest loop;
- knowledge compiler;
- review queue;
- answer-card drafts;
- benchmark loop;
- public AI workspace;
- process memory;
- governance rule: candidate/reference material is not official knowledge.

Brand Decision Loop V1 must reuse this foundation instead of creating a separate RAGFlow/Dify-style knowledge system.

## Product Boundary

V1 can evaluate:

- storefront text;
- main opening slogan;
- window copy;
- first-order project/menu naming;
- price presentation copy;
- opening posters and local-life listing copy;
- Xiaohongshu / WeChat / community opening copy;
- staff 30-second introduction and first-time recommendation scripts;
- first-store experiment proposals.

V1 must not:

- create VI;
- create SI;
- judge visual beauty as the main task;
- generate final storefront artwork;
- replace the design company;
- approve official brand standards;
- use candidate/reference material as authoritative source;
- process customer data that does not exist yet;
- create franchise/investor messaging as the main line.

## First-Store Focus

V1 follows the first-store funnel:

```text
exposure -> consultation -> arrival -> first_order -> satisfied_departure -> repurchase -> referral
```

The first version focuses on five brand decision domains.

### 1. Storefront And Outside Expression

Goal: make passersby understand what HXY is within three seconds.

Inputs:

- main storefront text;
- secondary storefront text;
- window copy;
- door poster headline;
- category word.

Core criteria:

- category clarity;
- one primary message;
- first-store credibility;
- community-store fit;
- visible purchase reason;
- compliance risk;
- copyability across future stores.

### 2. First-Order Project And Menu Expression

Goal: reduce choice friction for first-time customers.

Inputs:

- first-time recommended project;
- menu item name;
- package copy;
- price presentation;
- first-order explanation.

Core criteria:

- low decision cost;
- clear recommendation path;
- transparent price;
- staff explainability;
- margin and operation fit;
- no medicalized or exaggerated claims.

### 3. Staff Reception And Recommendation Script

Goal: make the brand executable by frontline staff.

Inputs:

- 30-second brand introduction;
- first-time reception script;
- customer objection responses;
- Qingpao/Tiaobuyang explanation;
- no-hard-sell card script;
- risk-boundary language.

Core criteria:

- speakable by staff;
- understandable by customers;
- no hard selling;
- clear next action;
- compliant wording;
- trainable as question cards.

### 4. Opening Content And Local Distribution

Goal: turn first-store brand expression into trackable opening traffic.

Inputs:

- Xiaohongshu opening content;
- WeChat Moments copy;
- community-group announcement;
- Douyin / local-life listing copy;
- map listing description;
- opening poster copy.

Core criteria:

- concrete scenario;
- one primary tag;
- explicit customer action;
- trust evidence;
- channel fit;
- measurable result.

### 5. First-Store Experiment And Review

Goal: make each brand action measurable and reusable.

Inputs:

- storefront wording experiment;
- first-order project experiment;
- price presentation experiment;
- opening content experiment;
- community script experiment;
- referral experiment.

Core criteria:

- hypothesis clarity;
- target funnel stage;
- measurable metric;
- risk metric;
- review date;
- decision: scale, adjust, stop, or retest.

## Scoring Model

Each review outputs a 100-point score:

| Dimension | Weight |
|---|---:|
| Category clarity | 15 |
| Scenario concreteness | 10 |
| Action clarity | 10 |
| Trust evidence | 15 |
| Staff explainability | 10 |
| Customer repeatability | 10 |
| First-store operating fit | 10 |
| Compliance safety | 15 |
| Copyability | 5 |

Decision thresholds:

```text
>= 85: usable draft, still requires human review
70-84: revise before use
< 70: reject for first-store use
any high compliance risk: reject or legal/operator review required
```

No result is official by default:

```json
{
  "official_use_allowed": false,
  "requires_human_review": true,
  "authority_rule": "brand_decision_outputs_are_reviews_not_official_brand_standards"
}
```

## Data Flow

```text
User submits brand artifact
-> classify artifact type
-> load first-store brand rules
-> score against criteria
-> detect risk flags
-> attach source references
-> produce decision result
-> write review record
-> optionally create review task
-> human decides whether to promote to official brand/SI knowledge
```

## VI/SI Integration

When the design company provides VI/SI files, HXYOS should ingest them as design-company outputs.

They should become:

- candidate design standards;
- operational acceptance checklists;
- store setup checklists;
- forbidden usage notes;
- material placement instructions;
- training references.

They should not become official standards until reviewed.

V1 only reserves the governance contract. It does not parse images or make visual-generation decisions.

## Output Contract

A brand decision review should include:

```json
{
  "version": "hxy-brand-decision-review.v1",
  "artifact_type": "storefront",
  "stage": "first_store_opening",
  "status": "revise_before_use",
  "score": 78,
  "criteria": [],
  "risk_flags": [],
  "matched_rules": [],
  "source_refs": [],
  "reject_reasons": [],
  "rewrite_direction": [],
  "recommended_version": "",
  "reviewer_role": "founder_or_operations_owner",
  "official_use_allowed": false,
  "requires_human_review": true
}
```

## UI Placement

V1 should appear in the knowledge workbench or operating brain as:

```text
首店品牌决策 Loop
输入：方案/文案/项目名/员工话术
输出：评分、风险、修改方向、复核记录
```

It should be visually separated from approved brand standards to avoid confusing reviews with official VI/SI rules.

## Success Criteria

V1 is acceptable when:

- storefront copy can be reviewed with clear scoring;
- first-order project/menu copy can be reviewed;
- risky medicalized claims are rejected;
- staff script review produces trainable feedback;
- opening content review maps to funnel metrics;
- review records are persisted;
- every result says it is not official knowledge;
- tests cover pass, revise, reject, and VI/SI boundary cases.

## Non-Goals

V1 does not implement:

- visual design generation;
- image-based SI inspection;
- construction drawing validation;
- full RAG over all PDFs/EPUBs;
- RAGFlow/Dify/LangGraph integration;
- automatic official brand standard publishing;
- customer-data analysis.
