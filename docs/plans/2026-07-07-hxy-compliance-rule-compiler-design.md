# HXY Compliance Rule Compiler Design

## Context

HXY already has a deterministic external-language check endpoint. It blocks obvious medical, guaranteed-effect, and exaggerated claims, and the admin page exposes a minimal "这句话能不能发" workflow.

The next risk is knowledge quality. The local risk/compliance folder now contains four private reference files:

- `荷小悦禁用表达库.md`
- `荷小悦员工功效问题标准话术.md`
- `荷小悦项目红线卡.md`
- `索引_风险与合规.md`

These files should not become public repository knowledge and should not become approved authority automatically. They should compile into local, candidate, reviewable rule artifacts that improve deterministic checking and prepare human review.

## Decision

Build a local compliance rule compiler inside the existing HXY knowledge API package.

The compiler reads private Markdown files from `knowledge/raw/inbox/.../09_风险与合规`, extracts:

- forbidden terms from red-word sections and "不能怎么说" table cells
- caution terms from yellow-word sections and high-risk project names
- safe replacements from "常见错误与替换"
- employee safe-answer snippets from "标准回答" sections
- project red-line rows from the project card

The output remains:

```text
status: candidate_rules
official_use_allowed: false
requires_human_review: true
```

The external-language checker may use these candidate rules to block or revise risky wording. The answer pipeline must not cite them as approved authority.

## Alternatives Considered

### A. Keep current ad hoc Markdown parser

This is simple, but it only reads part of the forbidden expression library and ignores the employee script and project red-line card. It leaves too much useful compliance material outside the executable gate.

### B. Use an LLM to summarize the compliance folder into rules

This is flexible, but it is unstable for P0 compliance. It can introduce invented rules, miss exact forbidden terms, or rewrite source meaning. Good for drafting, not for the gate.

### C. Deterministic local compiler with human-review status

This is the preferred approach. It is boring in the right way: source-controlled code, local private inputs, deterministic outputs, testable behavior, no auto-approval.

## Architecture

```text
private risk/compliance markdown
  -> deterministic parser
  -> candidate rule artifact
  -> language check endpoint
  -> business decision: allow / revise / block
  -> admin workflow: 能不能用 / 为什么 / 怎么改
```

The compiler belongs in `apps/api/hxy_knowledge/compliance_rules.py` because it directly feeds the existing check function. It should stay independent from htops and use only HXY-owned paths.

## Governance

Rules compiled from local documents are not official knowledge. They are guardrails.

Allowed:

- block risky wording
- suggest safer wording
- expose source file names for internal review
- feed admin-only compliance panels

Not allowed:

- publish as approved answer cards
- cite as external authority
- auto-update brand positioning
- push private knowledge files to GitHub

## Test Strategy

Add tests that prove:

- employee script forbidden examples are loaded
- project red-line "不能怎么说" terms are loaded
- safe replacement pairs are extracted
- checker blocks risky project wording such as `艾灸调理体质`
- checker does not flag boundary/reference wording such as `我们不做治疗`
- outputs remain non-official and human-review required
