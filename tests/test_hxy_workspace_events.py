from hxy_knowledge.workspace_events import (
    classify_workspace_visibility,
    create_workspace_event,
    get_workspace_event,
    list_workspace_events,
    redact_workspace_event,
)


def test_create_workspace_event_applies_public_episodic_defaults(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"

    event = create_workspace_event(
        {
            "topic": "公开 AI 工作记录",
            "input": "整理公开工作台记录",
            "ai_output": {"summary": "生成公开摘要"},
        },
        store_path=store_path,
        now=lambda: "2026-07-01T12:00:00Z",
    )

    assert event["version"] == "hxy-workspace-event.v1"
    assert event["event_id"].startswith("workspace-event-")
    assert event["visibility"] == "public_org"
    assert event["memory_layer"] == "episodic"
    assert event["official_use_allowed"] is False
    assert (
        event["authority_rule"]
        == "workspace_events_are_episodic_memory_not_approved_knowledge"
    )
    assert event["memory_action"] == {
        "type": "process_memory_context_only",
        "allowed_as_authority": False,
    }
    assert event["review_action"] == {"type": "none", "required": False}
    assert event["created_at"] == "2026-07-01T12:00:00Z"


def test_sensitive_payload_is_restricted_and_redacted_without_secret_leak(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"

    event = create_workspace_event(
        {
            "topic": "接口排查",
            "actor": "ops",
            "role": "admin",
            "input": "配置里出现 HXY_API_TOKEN=secret-value，需要处理",
            "ai_output": {"summary": "不要公开 HXY_API_TOKEN=secret-value"},
            "evidence": ["HXY_API_TOKEN=secret-value"],
            "risk_flags": ["credential_exposure"],
            "corrections": ["删除 HXY_API_TOKEN=secret-value"],
            "generated_tasks": ["轮换 HXY_API_TOKEN=secret-value"],
        },
        store_path=store_path,
        now=lambda: "2026-07-01T12:00:00Z",
    )

    assert event["visibility"] == "restricted_role"

    redacted = redact_workspace_event(event)
    rendered = str(redacted)
    assert redacted["visibility"] == "redacted_public"
    assert redacted["event_id"] == event["event_id"]
    assert redacted["topic"] == "接口排查"
    assert redacted["actor"] == "ops"
    assert redacted["role"] == "admin"
    assert redacted["risk_flags"] == ["credential_exposure"]
    assert redacted["review_action"] == event["review_action"]
    assert redacted["memory_action"] == event["memory_action"]
    assert redacted["created_at"] == event["created_at"]
    assert redacted["authority_rule"] == event["authority_rule"]
    assert redacted["input"] == "[redacted]"
    assert redacted["ai_output"] == "[redacted]"
    assert redacted["evidence"] == "[redacted]"
    assert redacted["corrections"] == "[redacted]"
    assert redacted["generated_tasks"] == "[redacted]"
    assert "secret-value" not in rendered
    assert "HXY_API_TOKEN" not in rendered


def test_list_redacts_sensitive_metadata_values_for_public_mirror(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"

    event = create_workspace_event(
        {
            "topic": "接口 HXY_API_TOKEN=secret-value 排查",
            "actor": "客户 13800138000",
            "role": "融资股权 reviewer",
            "input": "普通正文",
            "ai_output": {"summary": "普通输出"},
            "risk_flags": [
                "HXY_API_TOKEN=secret-value",
                {"phone": "13800138000", "clean": "kept"},
            ],
            "memory_action": {
                "type": "process_memory_context_only",
                "note": "HXY_DATABASE_URL=postgres://secret-value",
                "HXY_API_TOKEN=secret-value": "clean",
                "nested": ["safe", "融资计划"],
            },
            "review_action": {
                "type": "manual_review",
                "reason": "股权条款和 password=secret-value",
                "13800138000": "clean",
                "clean": "kept",
            },
        },
        store_path=store_path,
        now=lambda: "2026-07-01T12:00:00Z",
    )

    listed = list_workspace_events(store_path)
    item = listed["items"][0]
    rendered = str(item)

    assert item["event_id"] == event["event_id"]
    assert item["visibility"] == "redacted_public"
    assert item["official_use_allowed"] is False
    assert item["authority_rule"] == event["authority_rule"]
    assert item["input"] == "[redacted]"
    assert item["ai_output"] == "[redacted]"
    assert item["evidence"] == "[redacted]"
    assert item["corrections"] == "[redacted]"
    assert item["generated_tasks"] == "[redacted]"
    assert "secret-value" not in rendered
    assert "HXY_API_TOKEN" not in rendered
    assert "13800138000" not in rendered
    assert "融资" not in rendered
    assert "股权" not in rendered


def test_list_workspace_events_returns_newest_first_and_filters_query(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"
    create_workspace_event(
        {
            "topic": "早期记录",
            "input": "普通整理",
            "ai_output": {"summary": "无关内容"},
        },
        store_path=store_path,
        now=lambda: "2026-07-01T10:00:00Z",
    )
    later = create_workspace_event(
        {
            "topic": "菜单工作台",
            "input": "沉淀菜单协作记录",
            "ai_output": {"summary": "菜单公开摘要"},
        },
        store_path=store_path,
        now=lambda: "2026-07-01T11:00:00Z",
    )
    latest = create_workspace_event(
        {
            "topic": "复盘记录",
            "input": "HXY_API_TOKEN=secret-value",
            "ai_output": {"summary": "敏感复盘"},
        },
        store_path=store_path,
        now=lambda: "2026-07-01T12:00:00Z",
    )

    all_events = list_workspace_events(store_path)
    assert set(all_events) == {"items", "count"}
    assert [item["event_id"] for item in all_events["items"]] == [
        latest["event_id"],
        later["event_id"],
        all_events["items"][2]["event_id"],
    ]
    assert all_events["items"][0]["visibility"] == "redacted_public"
    assert "secret-value" not in str(all_events["items"][0])

    filtered = list_workspace_events(store_path, query="菜单")
    assert [item["event_id"] for item in filtered["items"]] == [later["event_id"]]


def test_get_workspace_event_returns_raw_event_by_id(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"
    event = create_workspace_event(
        {
            "topic": "敏感原始记录",
            "input": "HXY_API_TOKEN=secret-value",
            "ai_output": {"summary": "HXY_API_TOKEN=secret-value"},
        },
        store_path=store_path,
        now=lambda: "2026-07-01T12:00:00Z",
    )

    found = get_workspace_event(store_path, event["event_id"])

    assert found == event
    assert found["visibility"] == "restricted_role"
    assert "secret-value" in str(found)
    assert get_workspace_event(store_path, "workspace-event-missing") is None


def test_classify_workspace_visibility_honors_explicit_and_sensitive_patterns():
    assert (
        classify_workspace_visibility(
            {
                "visibility": "private_draft",
                "input": "HXY_DATABASE_URL=postgres://secret-value",
            }
        )
        == "private_draft"
    )
    assert (
        classify_workspace_visibility({"input": "HXY_DATABASE_URL=postgres://secret"})
        == "restricted_role"
    )
    assert (
        classify_workspace_visibility({"input": "客户手机号 13800138000"})
        == "restricted_role"
    )
    assert (
        classify_workspace_visibility({"input": "融资和股权结构讨论"})
        == "restricted_role"
    )
    assert (
        classify_workspace_visibility({"visibility": "restricted_role", "input": "普通"})
        == "restricted_role"
    )
    assert (
        classify_workspace_visibility({"visibility": "public_org", "input": "普通"})
        == "public_org"
    )


def test_list_workspace_events_skips_malformed_jsonl_and_filters_raw_visibility(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"
    public_event = create_workspace_event(
        {"topic": "公开记录", "input": "普通"},
        store_path=store_path,
        now=lambda: "2026-07-01T10:00:00Z",
    )
    restricted_event = create_workspace_event(
        {"topic": "敏感记录", "input": "HXY_API_TOKEN=secret-value"},
        store_path=store_path,
        now=lambda: "2026-07-01T11:00:00Z",
    )
    with store_path.open("a", encoding="utf-8") as stream:
        stream.write("{bad jsonl line\n")

    listed = list_workspace_events(store_path)
    assert [item["event_id"] for item in listed["items"]] == [
        restricted_event["event_id"],
        public_event["event_id"],
    ]

    restricted = list_workspace_events(store_path, visibility="restricted_role")
    assert restricted["count"] == 1
    assert restricted["items"][0]["event_id"] == restricted_event["event_id"]
    assert restricted["items"][0]["visibility"] == "redacted_public"
    assert "secret-value" not in str(restricted["items"][0])


def test_private_draft_is_hidden_from_list_but_raw_event_is_gettable(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"
    public_event = create_workspace_event(
        {"topic": "公开记录", "input": "普通"},
        store_path=store_path,
        now=lambda: "2026-07-01T10:00:00Z",
    )
    private_event = create_workspace_event(
        {
            "visibility": "private_draft",
            "topic": "内部草稿",
            "input": "HXY_API_TOKEN=private-secret",
            "ai_output": {"summary": "内部草稿内容"},
        },
        store_path=store_path,
        now=lambda: "2026-07-01T11:00:00Z",
    )

    listed = list_workspace_events(store_path)
    assert [item["event_id"] for item in listed["items"]] == [public_event["event_id"]]

    private_list = list_workspace_events(store_path, visibility="private_draft")
    assert private_list == {"items": [], "count": 0}

    raw_private = get_workspace_event(store_path, private_event["event_id"])
    assert raw_private == private_event
    assert raw_private["visibility"] == "private_draft"
    assert "private-secret" in str(raw_private)


def test_explicit_redacted_public_event_redacts_payload_fields_in_list(tmp_path):
    store_path = tmp_path / "workspace-events.jsonl"
    event = create_workspace_event(
        {
            "visibility": "redacted_public",
            "topic": "可公开脱敏镜像",
            "actor": "ops",
            "role": "team",
            "input": "原始内容包含 13800138000 和 HXY_API_TOKEN=secret-value",
            "ai_output": {"summary": "融资细节和 secret-value"},
            "evidence": ["HXY_DATABASE_URL=postgres://secret-value"],
            "risk_flags": ["contains_sensitive_context"],
            "corrections": ["隐藏 13800138000"],
            "generated_tasks": ["处理融资细节"],
        },
        store_path=store_path,
        now=lambda: "2026-07-01T12:00:00Z",
    )

    assert event["visibility"] == "redacted_public"

    listed = list_workspace_events(store_path)
    item = listed["items"][0]
    rendered = str(item)

    assert item["event_id"] == event["event_id"]
    assert item["visibility"] == "redacted_public"
    assert item["topic"] == "可公开脱敏镜像"
    assert item["actor"] == "ops"
    assert item["role"] == "team"
    assert item["risk_flags"] == ["contains_sensitive_context"]
    assert item["input"] == "[redacted]"
    assert item["ai_output"] == "[redacted]"
    assert item["evidence"] == "[redacted]"
    assert item["corrections"] == "[redacted]"
    assert item["generated_tasks"] == "[redacted]"
    assert "secret-value" not in rendered
    assert "13800138000" not in rendered
    assert "融资细节" not in rendered
