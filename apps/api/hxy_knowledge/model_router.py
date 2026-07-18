from __future__ import annotations

import os
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_CODEX_CONFIG_PATH = Path("/root/.codex/config.toml")

_DEFAULT_ROUTES: dict[str, dict[str, Any]] = {
    "reasoning": {
        "purpose": "经营判断、冲突分析、纠偏建议、多场景答案改写",
        "model_role": "default_model",
    },
    "classification": {
        "purpose": "资料分类、意图识别、角色识别、质检分级",
        "model_role": "default_model",
    },
    "issue_understanding": {
        "purpose": "把门店经营问题提取为受治理的结构化候选提案",
        "model_role": "default_model",
    },
    "vision": {
        "purpose": "图片理解、菜单图解析、流程图解析、报表截图解析",
        "model_role": "default_model",
    },
    "embedding": {
        "purpose": "文本召回、答案卡召回、组织记忆召回",
        "model_role": "default_model",
    },
    "speech": {
        "purpose": "培训语音转写、门店复盘转写、企微语音入口",
        "model_role": "default_model",
    },
    "training_evaluation": {
        "purpose": "门店员工话术评分、纠偏、复训建议和标准话术生成",
        "model_role": "review_model",
    },
    "frontdoor_classification": {
        "purpose": "识别问答、上传、培训、纠偏、经营判断等入口类型",
        "model_role": "default_model",
    },
    "workbench_intake": {
        "purpose": "判断聊天框输入应进入问经营、练员工、传资料、纠偏或经营任务工作流",
        "model_role": "default_model",
    },
    "answer_synthesis": {
        "purpose": "在证据约束下生成可用答案、角色话术和行动建议",
        "model_role": "default_model",
    },
    "policy_review": {
        "purpose": "质检答案风险、资料不足、夸大表达、收益和疗效边界",
        "model_role": "review_model",
    },
    "vision_understanding": {
        "purpose": "图片、菜单图、流程图、报表截图的多模态理解",
        "model_role": "default_model",
    },
    "offline_eval": {
        "purpose": "离线评测黄金问题、禁用表达、纠偏样本和答案稳定性",
        "model_role": "review_model",
    },
    "authority_answer": {
        "purpose": "已批准答案卡直接返回，不调用外部模型覆盖权威口径",
        "model_role": "none",
    },
    "rag_answer": {
        "purpose": "资料召回后的经营问答草稿；默认只记录推荐路由",
        "model_role": "default_model",
    },
}


def _enabled_from_env() -> bool:
    value = os.getenv("HXY_MODEL_ROUTER_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on", "enabled"}


def _safe_endpoint_host(base_url: str) -> str:
    if not base_url:
        return ""
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path.split("/", 1)[0]


def _extract_response_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts).strip()


def _extract_chat_completion_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for choice in data.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
    return "\n".join(parts).strip()


class ModelRouter:
    """Safe metadata router for HXY model selection.

    The router reads Codex model names and provider endpoints, but it never
    reads or returns credentials. Model execution is guarded by
    HXY_MODEL_ROUTER_ENABLED; the default mode is metadata-only.
    """

    def __init__(self, config_path: Path | str | None = None, http_client: Any | None = None) -> None:
        env_path = os.getenv("HXY_MODEL_CONFIG_PATH")
        self.config_path = Path(config_path or env_path or DEFAULT_CODEX_CONFIG_PATH)
        self._http_client = http_client
        self._config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with self.config_path.open("rb") as file:
            loaded = tomllib.load(file)
        return loaded if isinstance(loaded, dict) else {}

    @property
    def provider(self) -> str:
        return str(self._config.get("model_provider") or "")

    @property
    def default_model(self) -> str:
        return str(self._config.get("model") or "")

    @property
    def review_model(self) -> str:
        return str(self._config.get("review_model") or self.default_model)

    @property
    def vision_model(self) -> str:
        return str(self._config.get("vision_model") or self.default_model)

    @property
    def reasoning_effort(self) -> str:
        return str(self._config.get("model_reasoning_effort") or "")

    def _provider_config(self) -> dict[str, Any]:
        providers = self._config.get("model_providers") or {}
        if not isinstance(providers, dict):
            return {}
        provider_config = providers.get(self.provider) or {}
        return provider_config if isinstance(provider_config, dict) else {}

    def _route_config(self, route_key: str) -> dict[str, Any]:
        for section_name in ["model_routes", "hxy_model_routes", "task_routes"]:
            routes = self._config.get(section_name) or {}
            if not isinstance(routes, dict):
                continue
            route_config = routes.get(route_key) or {}
            if isinstance(route_config, dict):
                return route_config
        return {}

    @property
    def wire_api(self) -> str:
        provider_config = self._provider_config()
        return str(provider_config.get("wire_api") or "")

    @property
    def endpoint_host(self) -> str:
        provider_config = self._provider_config()
        return _safe_endpoint_host(str(provider_config.get("base_url") or ""))

    @property
    def base_url(self) -> str:
        provider_config = self._provider_config()
        return str(provider_config.get("base_url") or "").rstrip("/")

    @property
    def execution_mode(self) -> str:
        return "enabled" if _enabled_from_env() else "metadata_only"

    @property
    def api_key(self) -> str:
        return os.getenv("HXY_MODEL_API_KEY", "").strip()

    def route(self, task_type: str) -> dict[str, Any]:
        route_key = task_type.strip() or "reasoning"
        route_definition = deepcopy(_DEFAULT_ROUTES.get(route_key) or _DEFAULT_ROUTES["reasoning"])
        route_config = self._route_config(route_key)
        model_role = route_definition.get("model_role")
        selected_model = ""
        if model_role == "default_model":
            selected_model = self.vision_model if route_key in {"vision", "vision_understanding"} else self.default_model
        elif model_role == "review_model":
            selected_model = self.review_model
        if route_config.get("model"):
            selected_model = str(route_config["model"])

        wire_api = str(route_config.get("wire_api") or "")
        if not wire_api and route_key in {"vision", "vision_understanding"}:
            wire_api = str(self._config.get("vision_wire_api") or "")
        wire_api = wire_api or self.wire_api

        should_call_model = (
            self.execution_mode == "enabled"
            and route_key not in {"authority_answer"}
            and bool(selected_model)
            and bool(self.provider)
            and bool(wire_api)
        )
        return {
            "version": "hxy-model-router.v1",
            "task_type": route_key,
            "purpose": route_definition["purpose"],
            "provider": self.provider,
            "selected_model": selected_model,
            "wire_api": wire_api,
            "endpoint_host": self.endpoint_host,
            "reasoning_effort": self.reasoning_effort,
            "execution_mode": self.execution_mode,
            "should_call_model": should_call_model,
            "config_loaded": bool(self._config),
            "config_source": str(self.config_path),
        }

    def generate(
        self,
        task_type: str,
        *,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        route = self.route(task_type)
        request_shape = {
            "message_count": len(messages or []),
            "has_prompt": bool(prompt),
            "metadata_keys": sorted((metadata or {}).keys()),
        }
        if not route["should_call_model"]:
            return {
                "version": "hxy-model-generation.v1",
                "used_model": False,
                "reason": "disabled",
                "route": route,
                "request_shape": request_shape,
                "output": None,
            }
        route_wire_api = str(route.get("wire_api") or "")
        if not self.api_key or route_wire_api not in {"responses", "chat_completions"} or not self.base_url:
            return {
                "version": "hxy-model-generation.v1",
                "used_model": False,
                "reason": "client_not_configured",
                "route": route,
                "request_shape": request_shape,
                "output": None,
            }
        client = self._http_client
        if client is None:
            try:
                import httpx
            except ImportError:
                return {
                    "version": "hxy-model-generation.v1",
                    "used_model": False,
                    "reason": "client_not_configured",
                    "route": route,
                    "request_shape": request_shape,
                    "output": None,
                }
            client = httpx.Client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if route_wire_api == "chat_completions":
            payload = {
                "model": route["selected_model"],
                "messages": messages or [{"role": "user", "content": prompt or ""}],
            }
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
        else:
            payload = {
                "model": route["selected_model"],
                "input": messages or [{"role": "user", "content": prompt or ""}],
                "store": False,
            }
            if self.reasoning_effort:
                payload["reasoning"] = {"effort": self.reasoning_effort}
            response = client.post(
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
                timeout=60,
            )
        response.raise_for_status()
        data = response.json()
        output = _extract_chat_completion_text(data) if route_wire_api == "chat_completions" else _extract_response_text(data)
        return {
            "version": "hxy-model-generation.v1",
            "used_model": True,
            "reason": "ok",
            "route": route,
            "request_shape": request_shape,
            "provider_response_id": data.get("id"),
            "usage": data.get("usage") or {},
            "output": output,
        }

    def status(self) -> dict[str, Any]:
        public_routes = [
            self.route(task_type)
            for task_type in [
                "reasoning",
                "classification",
                "issue_understanding",
                "vision",
                "embedding",
                "speech",
                "training_evaluation",
                "frontdoor_classification",
                "workbench_intake",
                "answer_synthesis",
                "policy_review",
                "vision_understanding",
                "offline_eval",
            ]
        ]
        return {
            "version": "hxy-model-router.v1",
            "config_source": str(self.config_path),
            "config_loaded": bool(self._config),
            "provider": self.provider,
            "default_model": self.default_model,
            "review_model": self.review_model,
            "vision_model": self.vision_model,
            "wire_api": self.wire_api,
            "endpoint_host": self.endpoint_host,
            "reasoning_effort": self.reasoning_effort,
            "execution_mode": self.execution_mode,
            "routes": public_routes,
            "safety": {
                "private_values_exposed": False,
                "auth_files_read": False,
                "default_behavior": "answer cards and deterministic retrieval stay in control; model calls are opt-in.",
            },
        }
