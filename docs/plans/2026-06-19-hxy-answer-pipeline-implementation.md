# HXY Answer Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn HXY chat into a controlled answer pipeline with policy, evidence planning, guardrails, and evolution actions.

**Architecture:** Add a deterministic `answer_pipeline.py` owner module that wraps existing workbench, reliability, answer-card, and model-router signals into one Inspector-ready contract. Keep the user-facing answer clean; expose policy, evidence, guardrail, and evolution metadata only as structured fields.

**Tech Stack:** Python 3.12, FastAPI, unittest, existing HXY knowledge modules.

---

## Tasks

1. Write failing service tests for `build_answer_pipeline`.
2. Write failing API tests for `/api/knowledge/chat` pipeline metadata.
3. Implement `answer_pipeline.py`.
4. Wire pipeline output into authority-card and RAG answers.
5. Extend `ModelRouter` with pipeline route names.
6. Run full verification and smoke tests.

