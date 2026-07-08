from __future__ import annotations


def test_validate_harness_spec_accepts_safe_verification_only_spec(tmp_path):
    from hxy_knowledge.harness_runner import validate_harness_spec

    spec = {
        "version": "hxy-harness-spec.v1",
        "run_name": "source-quality-gate-v1",
        "target": "source classification accuracy >= 0.85",
        "scope": ["apps/api/hxy_knowledge/ingest_loop.py"],
        "max_rounds": 3,
        "verification_commands": ["npm test"],
        "forbidden_paths": ["/root/htops"],
        "forbidden_actions": ["auto_approve_knowledge", "write_formal_knowledge_store"],
        "success_thresholds": {"npm_test": "pass"},
    }

    result = validate_harness_spec(spec, root_dir=tmp_path)

    assert result["version"] == "hxy-harness-spec-validation.v1"
    assert result["valid"] is True
    assert result["error_count"] == 0
    assert result["write_to_database"] is False
    assert result["official_use_allowed"] is False


def test_validate_harness_spec_rejects_htops_scope_and_unsafe_commands(tmp_path):
    from hxy_knowledge.harness_runner import validate_harness_spec

    spec = {
        "version": "hxy-harness-spec.v1",
        "run_name": "unsafe",
        "target": "do unsafe thing",
        "scope": ["/root/htops/api/main.py"],
        "max_rounds": 5,
        "verification_commands": ["rm -rf /root/hxy/knowledge/wiki"],
        "forbidden_paths": ["/root/htops"],
        "forbidden_actions": ["auto_approve_knowledge"],
        "success_thresholds": {},
    }

    result = validate_harness_spec(spec, root_dir=tmp_path)

    assert result["valid"] is False
    assert {error["code"] for error in result["errors"]} >= {
        "forbidden_scope_path",
        "command_not_allowlisted",
    }
    assert result["write_to_database"] is False
