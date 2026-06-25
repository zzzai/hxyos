# HXY Execution Loop

## Purpose

This document turns Loop Engineering into a repeatable HXY operating rule.
It is the difference between "a model that answers" and "a system that finishes work reliably".

## When To Use

Use this loop for:

- prompt-heavy coding tasks
- AI workflows with retries or branching
- answer generation with evaluation gates
- knowledge extraction and correction
- any task that can drift, repeat, or consume context

## Loop Contract

Each loop must define:

1. `goal`
2. `context_budget`
3. `tool_or_agent`
4. `evaluation`
5. `stop_condition`

## Components

### Goal

The goal must be measurable.

Bad:

- "improve the assistant"
- "make it smarter"
- "optimize the prompt"

Good:

- "raise task pass rate from 72% to 85%"
- "reduce false positives in answer cards by 30%"
- "generate a valid positioning card for every stage-0 intake"

### Context Management

The loop must keep only the context needed for the current decision.

Rules:

- trim stale instructions
- compress repeated evidence
- summarize long history
- keep the current constraint set visible
- move everything else into memory or evidence storage

### Tool Call

The loop must do something real.

Examples:

- run a test
- call a model
- inspect a page
- score an output
- create a task
- update a card

### Evaluation

The loop must judge output against a testable standard.

Possible evaluators:

- unit test
- integration test
- golden question set
- rubric scoring
- human review
- metrics delta

### Stop Condition

Every loop must stop when one of these is true:

- the measurable target is met
- the hard iteration limit is reached
- the evidence is insufficient
- the goal has drifted
- the context budget is exhausted

## Failure Modes

### Infinite Loop

Symptom:

- repeated prompt retries
- no visible improvement
- no stop point

Fix:

- add an iteration cap
- define a success threshold
- force a fallback branch

### Goal Drift

Symptom:

- the loop starts about one problem and ends on another

Fix:

- persist the original target
- compare each iteration against the target
- reject off-target improvements

### Context Overflow

Symptom:

- the loop loses important constraints
- output starts contradicting previous decisions

Fix:

- summarize old context
- keep only active constraints
- push stable facts into memory

## HXY Application

HXY is the loop owner. Models and agents execute inside the loop, but HXY owns the goal, the stop condition, and the acceptance rule.

For HXY, the loop should map to:

- project brief intake
- evidence gathering
- answer card generation
- quality scoring
- correction package generation
- version update

The loop is successful when the system produces a better decision, a cleaner answer, or a better follow-up task.
