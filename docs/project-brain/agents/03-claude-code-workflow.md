# HXY Claude Code Workflow

## Purpose

Claude Code 不是一个“会聊天的模型”，而是 HXY 的执行环境。
它的价值不在于多说，而在于把一次任务稳定做完、做对、做可交接。

## What The External Materials Contribute

- `Loop Engineering` gives HXY a closed-loop method: target, context, tools, evaluation, stop condition.
- `awesome-claude-md` shows how a project contract removes repeated instructions.
- `gstack` shows how one model can be staged as a small virtual team.
- The skills catalog shows which repeatable workflows can be reused instead of rebuilt.

## Harness Vs Loop

**Harness** is the stage.
It includes the repo structure, docs, tests, commands, and guardrails.

**Loop** is the script.
It defines the target, the bounded context, the tool call, the evaluation step, and the stop condition.

Example:

- Harness: `CLAUDE.md`, `tests/`, `docs/project-brain/`, HXY scripts, and local verification commands.
- Loop: "generate a positioning card, score it, stop when the acceptance rule is met."

Do not confuse the stage with the script.
A strong harness without a loop produces repetition.
A loop without a harness produces drift.

## Role Stack

HXY can simulate a compact internal team inside Claude Code:

- Product: defines the target and acceptance rule.
- Design: shapes the result format and interaction boundaries.
- Engineer: makes the smallest code or document change.
- QA: runs tests, screenshots, or checks.
- Release: updates docs, index, and handoff notes.
- Reviewer: checks drift, missing evidence, and regressions.

This is not six separate projects.
It is one task moving through six lenses.

## Operating Rules

1. One goal per loop.
2. One stop condition per loop.
3. One evaluation rule per loop.
4. Keep the active context short.
5. Turn finished work into a handoff.

## Handoff

Every finished loop should leave behind:

- current target
- what changed
- what was verified
- what remains risky
- what the next loop should do

That handoff is the memory bridge between sessions.

## How This Helps HXY

- The project contract moves into `CLAUDE.md`.
- Repeated prompt behavior becomes a documented loop.
- Role switching becomes explicit instead of accidental.
- Results become testable instead of rhetorical.

