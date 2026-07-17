from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import pytest

from hxy_knowledge.answer_service import AnswerServiceHooks, generate_answer
from hxy_knowledge.brand_constitution import (
    BrandConstitutionAdapter,
    BrandConstitutionError,
)


FIXTURE = Path(__file__).parent / "fixtures" / "brand-constitution-v1.example.json"


def _payload(version: str = "1.0.0-example") -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["version"] = version
    return payload


def _write_version(root: Path, payload: dict[str, Any], *, active: bool = True) -> Path:
    constitution_root = root / "data" / "private" / "brand-constitution"
    versions = constitution_root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    version_path = versions / f"{payload['version']}.json"
    version_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(version_path.read_bytes()).hexdigest()
    events_path = constitution_root / "events.jsonl"
    event_id = f"publish-{payload['version']}"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event_id": event_id,
                    "event_type": "publish",
                    "version": payload["version"],
                    "content_sha256": digest,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    if active:
        (constitution_root / "active.json").write_text(
            json.dumps(
                {
                    "version": payload["version"],
                    "content_sha256": digest,
                    "activation_event_id": event_id,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return version_path


def test_valid_owner_approved_constitution_produces_formal_role_answer(tmp_path: Path) -> None:
    _write_version(tmp_path, _payload())

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="store_staff")

    assert result["answer_mode"] == "formal"
    assert result["authority_source"] == "official_internal"
    assert result["usage_boundary"] == "team_standard"
    assert result["answer_status"] == "已批准"
    assert result["confidence"] == "high"
    assert result["needs_review"] is False
    assert result["from_brand_constitution"] is True
    assert result["answer"] == "示例品牌是一家服务社区顾客的日常生活服务门店。"
    assert result["evidence"] == [
        {
            "type": "brand_constitution",
            "source_type": "official_internal",
            "title": "品牌宪法 1.0.0-example",
            "version": "1.0.0-example",
            "authority_source": "official_internal",
            "strength": "high",
            "excerpt": "当前生效的已核定品牌宪法版本。",
        }
    ]
    assert "private" not in json.dumps(result, ensure_ascii=False).lower()


@pytest.mark.parametrize("condition", ["missing", "superseded", "not_owner_approved"])
def test_unavailable_or_inactive_constitution_returns_working_boundary(
    tmp_path: Path,
    condition: str,
) -> None:
    if condition != "missing":
        payload = _payload()
        if condition == "superseded":
            payload["status"] = "superseded"
        else:
            payload["owner_approved"] = False
        _write_version(tmp_path, payload)

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="founder")

    assert result["answer_mode"] == "working"
    assert result["authority_source"] == "none"
    assert result["usage_boundary"] == "review_required"
    assert result["needs_review"] is True
    assert result["from_brand_constitution"] is False
    assert result["evidence"] == []


def test_external_reference_cannot_grant_constitution_authority(tmp_path: Path) -> None:
    payload = _payload()
    payload["source_references"] = [
        {"source_id": "example-article", "authority": "external_reference"}
    ]
    _write_version(tmp_path, payload)

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="founder")

    assert result["answer_mode"] == "working"
    assert result["needs_review"] is True


def test_unsafe_role_variant_invalidates_the_constitution(tmp_path: Path) -> None:
    payload = _payload()
    payload["role_variants"]["store_staff"] = "示例品牌是医疗机构，并保证有效。"
    _write_version(tmp_path, payload)

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="founder")

    assert result["answer_mode"] == "working"
    assert result["needs_review"] is True


def test_project_specific_forbidden_term_invalidates_formal_rendering(tmp_path: Path) -> None:
    payload = _payload()
    payload["forbidden_interpretations"].append(
        {
            "statement": "不得把示例品牌描述为奢华会所",
            "blocked_terms": ["奢华会所"],
        }
    )
    payload["role_variants"]["founder"] = "示例品牌要建设成为奢华会所。"
    _write_version(tmp_path, payload)

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="founder")

    assert result["answer_mode"] == "working"
    assert result["needs_review"] is True


class _NoKnowledgeAccessRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def save_answer_run(self, answer: dict[str, Any]) -> str:
        self.saved.append(answer)
        return "answer-brand-1"

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"formal constitution answer must not access repository.{name}")


class _NoModelRouter:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"formal constitution answer must not access model_router.{name}")


class _AuthorityRouter:
    def route(self, task_type: str) -> dict[str, Any]:
        return {"task_type": task_type, "should_call_model": False}


class _ApprovedCardFallbackRepository(_NoKnowledgeAccessRepository):
    def find_answer_card(self, _question: str, _intent: str) -> dict[str, Any]:
        return {
            "card_id": "legacy-brand-card",
            "status": "approved",
            "answer": "旧答案卡不应绕过品牌宪法边界。",
        }


def _formal_answer_hooks() -> AnswerServiceHooks:
    def classify_frontdoor(**_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "brand_positioning",
            "audience": "brand",
            "mode": "rule",
        }

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("formal constitution answer must bypass retrieval and synthesis")

    return AnswerServiceHooks(
        classify_frontdoor=classify_frontdoor,
        repository_search=forbidden,
        items_need_better_retrieval=forbidden,
        fallback_queries=forbidden,
        answer_from_authority_card=forbidden,
        attach_model_route=forbidden,
        attach_answer_pipeline=forbidden,
        apply_frontdoor_to_answer=forbidden,
        maybe_apply_model_answer=forbidden,
    )


def _approved_card_hooks() -> AnswerServiceHooks:
    def classify_frontdoor(**_kwargs: Any) -> dict[str, Any]:
        return {"intent": "brand_positioning", "audience": "brand", "mode": "rule"}

    def answer_from_card(**kwargs: Any) -> dict[str, Any]:
        return {
            "answer": kwargs["card"]["answer"],
            "intent": "brand_positioning",
            "audience": "brand",
            "answer_status": "已批准",
            "confidence": "high",
            "needs_review": False,
            "from_answer_card": True,
            "evidence": [],
            "sources": [],
        }

    def attach_pipeline(answer: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        answer["answer_pipeline"] = {
            "answer_mode": "formal",
            "authority_source": "approved_answer_card",
            "usage_boundary": "team_standard",
            "policy_decision": {"action": "answer"},
        }
        return answer

    return AnswerServiceHooks(
        classify_frontdoor=classify_frontdoor,
        repository_search=lambda *_args, **_kwargs: [],
        items_need_better_retrieval=lambda _items, _intent: False,
        fallback_queries=lambda _question: [],
        answer_from_authority_card=answer_from_card,
        attach_model_route=lambda answer, _route: answer,
        attach_answer_pipeline=attach_pipeline,
        apply_frontdoor_to_answer=lambda answer, _frontdoor: answer,
        maybe_apply_model_answer=lambda **_kwargs: None,
    )


def test_formal_constitution_answer_bypasses_chat_memory_external_material_and_model(
    tmp_path: Path,
) -> None:
    version_path = _write_version(tmp_path, _payload())
    before = version_path.read_bytes()
    repository = _NoKnowledgeAccessRepository()

    result = generate_answer(
        question="荷小悦是什么？",
        scenario="门店员工工作问答",
        domain=None,
        stage=None,
        limit=5,
        repository=repository,
        model_router=_NoModelRouter(),
        hooks=_formal_answer_hooks(),
        role="store_staff",
        pipeline_role="store_staff",
        brand_constitution=BrandConstitutionAdapter(tmp_path),
    )

    assert result["answer_mode"] == "formal"
    assert result["answer_id"] == "answer-brand-1"
    assert result["from_brand_constitution"] is True
    assert len(repository.saved) == 1
    assert version_path.read_bytes() == before


def test_missing_constitution_returns_boundary_before_retrieval_or_model(
    tmp_path: Path,
) -> None:
    repository = _NoKnowledgeAccessRepository()

    result = generate_answer(
        question="荷小悦是什么？",
        scenario="创始人内部决策",
        domain=None,
        stage=None,
        limit=5,
        repository=repository,
        model_router=_NoModelRouter(),
        hooks=_formal_answer_hooks(),
        role="founder",
        pipeline_role="team",
        brand_constitution=BrandConstitutionAdapter(tmp_path),
    )

    assert result["answer_mode"] == "working"
    assert result["authority_source"] == "none"
    assert result["usage_boundary"] == "review_required"
    assert result["needs_review"] is True
    assert result["answer_id"] == "answer-brand-1"
    assert result["from_answer_card"] is False
    assert result["reasoning"]
    assert result["conflicts"]
    assert result["corrections"] == []
    assert result["actions"] == []
    assert result["result_card"]["stability_level"] == "review_required"
    assert result["result_card"]["usable_answer"] == result["answer"]
    assert len(repository.saved) == 1


@pytest.mark.parametrize(
    "question",
    [
        "荷小悦的品牌定位是什么？",
        "荷小悦的定位是什么？",
        "荷小悦品牌定位怎么说？",
        "介绍一下荷小悦",
        "介绍下荷小悦",
        "荷小悦是干嘛的？",
        "给我说说荷小悦",
        "荷小悦属于什么类型的品牌？",
        "荷小悦的核爆点定位是什么？",
    ],
)
def test_core_brand_positioning_questions_use_the_constitution(
    tmp_path: Path,
    question: str,
) -> None:
    _write_version(tmp_path, _payload())

    result = generate_answer(
        question=question,
        scenario="创始人内部决策",
        domain=None,
        stage=None,
        limit=5,
        repository=_NoKnowledgeAccessRepository(),
        model_router=_NoModelRouter(),
        hooks=_formal_answer_hooks(),
        role="founder",
        pipeline_role="team",
        brand_constitution=BrandConstitutionAdapter(tmp_path),
    )

    assert result["answer_mode"] == "formal"
    assert result["from_brand_constitution"] is True


@pytest.mark.parametrize(
    "question",
    [
        "荷小悦有哪些服务项目？",
        "说说荷小悦有哪些服务项目",
        "荷小悦门店怎么选址？",
        "荷小悦门店定位在哪里？",
        "荷小悦什么时候开业？",
        "荷小悦做什么活动获客？",
        "荷小悦品牌是什么时候注册的？",
    ],
)
def test_specific_business_questions_are_not_mistaken_for_brand_identity(question: str) -> None:
    assert BrandConstitutionAdapter.covers_question(question) is False


def test_invalid_constitution_cannot_fall_through_to_formal_approved_card(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["status"] = "superseded"
    _write_version(tmp_path, payload)

    result = generate_answer(
        question="荷小悦是什么？",
        scenario="创始人内部决策",
        domain=None,
        stage=None,
        limit=5,
        repository=_ApprovedCardFallbackRepository(),
        model_router=_AuthorityRouter(),
        hooks=_approved_card_hooks(),
        role="founder",
        pipeline_role="team",
        brand_constitution=BrandConstitutionAdapter(tmp_path),
    )

    assert result["answer_mode"] == "working"
    assert result["needs_review"] is True
    assert result["from_brand_constitution"] is False
    assert "旧答案卡" not in result["answer"]
    assert result["authority_source"] == "none"
    assert result["usage_boundary"] == "review_required"


def test_operational_rollback_restores_prior_approved_version_and_appends_audit(
    tmp_path: Path,
) -> None:
    first_path = _write_version(tmp_path, _payload("1.0.0-example"), active=False)
    second_path = _write_version(tmp_path, _payload("1.1.0-example"), active=True)
    before_first = first_path.read_bytes()
    before_second = second_path.read_bytes()
    adapter = BrandConstitutionAdapter(tmp_path)

    result = adapter.rollback(
        target_version="1.0.0-example",
        actor="example-operator",
        reason="example operational rollback",
    )

    assert result["from_version"] == "1.1.0-example"
    assert result["to_version"] == "1.0.0-example"
    assert adapter.active_version() == "1.0.0-example"
    assert first_path.read_bytes() == before_first
    assert second_path.read_bytes() == before_second
    events = [
        json.loads(line)
        for line in (
            tmp_path / "data" / "private" / "brand-constitution" / "events.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["event_type"] == "rollback"
    assert events[-1]["actor"] == "example-operator"


def test_rollback_rejects_unapproved_target(tmp_path: Path) -> None:
    _write_version(tmp_path, _payload("1.1.0-example"), active=True)
    target = _payload("1.0.0-example")
    target["owner_approved"] = False
    _write_version(tmp_path, target, active=False)

    with pytest.raises(BrandConstitutionError, match="approved"):
        BrandConstitutionAdapter(tmp_path).rollback(
            target_version="1.0.0-example",
            actor="example-operator",
            reason="must fail",
        )


def test_rollback_rejects_a_later_version(tmp_path: Path) -> None:
    _write_version(tmp_path, _payload("1.0.0-example"), active=True)
    _write_version(tmp_path, _payload("9.0.0-example"), active=False)

    with pytest.raises(BrandConstitutionError, match="prior"):
        BrandConstitutionAdapter(tmp_path).rollback(
            target_version="9.0.0-example",
            actor="example-operator",
            reason="not a rollback",
        )


def test_audit_prepare_failure_keeps_the_active_pointer_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_version(tmp_path, _payload("1.0.0-example"), active=False)
    _write_version(tmp_path, _payload("1.1.0-example"), active=True)
    adapter = BrandConstitutionAdapter(tmp_path)

    def fail_audit(_event: dict[str, Any]) -> None:
        raise OSError("audit unavailable")

    monkeypatch.setattr(adapter, "_append_event", fail_audit)

    with pytest.raises(OSError, match="audit unavailable"):
        adapter.rollback(
            target_version="1.0.0-example",
            actor="example-operator",
            reason="must remain unchanged",
        )

    assert adapter.active_version() == "1.1.0-example"


def test_rollback_has_no_second_audit_write_failure_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_version(tmp_path, _payload("1.0.0-example"), active=False)
    _write_version(tmp_path, _payload("1.1.0-example"), active=True)
    adapter = BrandConstitutionAdapter(tmp_path)
    original = adapter._append_event
    calls = 0

    def fail_second_write(event: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("second audit write unavailable")
        original(event)

    monkeypatch.setattr(adapter, "_append_event", fail_second_write)

    result = adapter.rollback(
        target_version="1.0.0-example",
        actor="example-operator",
        reason="single audited commit",
    )

    assert calls == 1
    assert result["event_type"] == "rollback"
    assert adapter.active_version() == "1.0.0-example"


def test_active_version_tampering_invalidates_formal_authority(tmp_path: Path) -> None:
    path = _write_version(tmp_path, _payload())
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["role_variants"]["founder"] = "同版本下被改写的内容。"
    path.write_text(json.dumps(tampered, ensure_ascii=False, indent=2), encoding="utf-8")

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="founder")

    assert result["answer_mode"] == "working"
    assert result["needs_review"] is True


def test_active_pointer_requires_matching_publication_event(tmp_path: Path) -> None:
    _write_version(tmp_path, _payload())
    events_path = tmp_path / "data" / "private" / "brand-constitution" / "events.jsonl"
    events_path.write_text("", encoding="utf-8")

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="founder")

    assert result["answer_mode"] == "working"
    assert result["needs_review"] is True


def test_formal_answer_exposes_only_the_selected_role_rendering(tmp_path: Path) -> None:
    _write_version(tmp_path, _payload())

    result = BrandConstitutionAdapter(tmp_path).answer_for_brand_identity(role="store_staff")

    assert "role_versions" not in result
    assert "forbidden_interpretations" not in result
    serialized = json.dumps(result, ensure_ascii=False)
    assert "示例品牌以社区日常服务为起点" not in serialized
