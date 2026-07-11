from __future__ import annotations

from apps.api.hxy_engines.adapters.current_model import CurrentModelGateway
from apps.api.hxy_engines.contracts import EngineBudget, EngineContext
from apps.api.hxy_engines.model_gateway import ModelRequest


def _context() -> EngineContext:
    return EngineContext(
        request_id="request-model-001",
        trace_id="trace-model-001",
        account_id="account-001",
        assignment_id="assignment-001",
        organization_id="organization-001",
        store_id=None,
        purpose="answer_synthesis",
        authority_policy="approved_plus_reference",
        budget=EngineBudget(max_latency_ms=60_000, max_tokens=8_000),
    )


class FakeRouter:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result or {}
        self.calls: list[dict] = []

    def generate(self, task_type, *, messages=None, prompt=None, metadata=None):
        self.calls.append(
            {
                "task_type": task_type,
                "messages": messages,
                "prompt": prompt,
                "metadata": metadata,
            }
        )
        return self.result


def test_authority_answer_bypasses_model_router() -> None:
    router = FakeRouter()
    gateway = CurrentModelGateway(router)

    result = gateway.execute(
        _context(),
        ModelRequest(task_type="authority_answer", prompt="approved answer"),
    )

    assert router.calls == []
    assert result.status == "skipped"
    assert result.artifacts == ()
    assert result.policy_decisions[0].reason_code == "authority_answer_bypasses_model"


def test_current_gateway_maps_model_output_to_candidate_and_usage() -> None:
    router = FakeRouter(
        {
            "version": "hxy-model-generation.v1",
            "used_model": True,
            "reason": "ok",
            "provider_response_id": "resp-001",
            "usage": {"input_tokens": 120, "output_tokens": 40},
            "route": {
                "provider": "custom",
                "selected_model": "model-001",
            },
            "output": "基于资料生成的候选回答。",
        }
    )
    gateway = CurrentModelGateway(router)

    result = gateway.execute(
        _context(),
        ModelRequest(
            task_type="answer_synthesis",
            messages=(
                {"role": "system", "content": "只基于证据回答"},
                {"role": "user", "content": "荷小悦是什么？"},
            ),
            metadata_keys=("answer_contract",),
        ),
    )

    assert len(router.calls) == 1
    assert result.status == "succeeded"
    assert result.artifacts[0].authority == "candidate"
    assert result.artifacts[0].artifact_id == "resp-001"
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 40
    assert result.private_output == "基于资料生成的候选回答。"
    assert "候选回答" not in str(result.as_trace_record())


def test_gateway_normalizes_chat_completion_usage_without_exposing_secrets() -> None:
    router = FakeRouter(
        {
            "version": "hxy-model-generation.v1",
            "used_model": True,
            "reason": "ok",
            "provider_response_id": "chat-001",
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            "route": {
                "provider": "dashscope",
                "selected_model": "qwen",
            },
            "output": "草稿",
        }
    )
    result = CurrentModelGateway(router).execute(
        _context(),
        ModelRequest(task_type="answer_synthesis", prompt="问题"),
    )

    assert result.usage.total_tokens == 70
    trace = str(result.as_trace_record()).lower()
    assert "api_key" not in trace
    assert "authorization" not in trace
    assert "bearer" not in trace


def test_disabled_current_router_returns_skipped_without_artifact() -> None:
    router = FakeRouter(
        {
            "version": "hxy-model-generation.v1",
            "used_model": False,
            "reason": "disabled",
            "route": {"provider": "custom", "selected_model": "model-001"},
            "output": None,
        }
    )

    result = CurrentModelGateway(router).execute(
        _context(),
        ModelRequest(task_type="answer_synthesis", prompt="问题"),
    )

    assert result.status == "skipped"
    assert result.artifacts == ()
    assert result.policy_decisions[0].reason_code == "model_disabled"
