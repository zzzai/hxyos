import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HxyMemoryContextTest(unittest.TestCase):
    def test_build_memory_context_prioritizes_formal_knowledge_over_process_memory(self):
        memory_context = load_module("hxy_memory_context", "apps/api/hxy_knowledge/memory_context.py")

        result = memory_context.build_memory_context(
            working_memory={
                "goal": "回答员工怎么推荐泡脚方",
                "role": "store_staff",
                "scenario": "员工训练",
                "remaining_steps": ["判断禁用表达", "输出门店话术"],
            },
            short_term_messages=[
                {"role": "user", "content": "顾客说睡不好，能不能说治疗失眠？"},
                {"role": "assistant", "content": "不能说治疗，只能表达放松和体验建议。"},
            ],
            retrieved_memories=[
                {
                    "memory_id": "approved-card-1",
                    "content": "员工不能承诺治疗、治愈、保证有效。",
                    "layer": "formal_knowledge",
                    "status": "approved",
                    "source_type": "approved_answer_card",
                    "importance": 0.95,
                    "recency": 0.4,
                    "semantic_relevance": 0.9,
                    "risk_level": "high",
                },
                {
                    "memory_id": "process-1",
                    "content": "创始人偏好口语化表达，不要讲太复杂。",
                    "layer": "long_term_memory",
                    "status": "process",
                    "source_type": "process_memory",
                    "importance": 0.7,
                    "recency": 0.9,
                    "semantic_relevance": 0.8,
                },
            ],
            budget={"formal_knowledge": 3, "process_memory": 1, "short_term_messages": 2},
        )

        self.assertEqual(result["version"], "hxy-memory-context.v1")
        self.assertEqual(result["working_memory"]["goal"], "回答员工怎么推荐泡脚方")
        self.assertEqual([item["memory_id"] for item in result["formal_knowledge"]], ["approved-card-1"])
        self.assertEqual([item["memory_id"] for item in result["process_memory_hints"]], ["process-1"])
        self.assertTrue(result["process_memory_hints"][0]["context_hint_only"])
        self.assertFalse(result["process_memory_hints"][0]["official_use_allowed"])
        self.assertEqual(result["authority_rule"], "process_memory_cannot_be_authority")

    def test_memory_context_applies_decay_and_blocks_conflicted_items(self):
        memory_context = load_module("hxy_memory_context_decay", "apps/api/hxy_knowledge/memory_context.py")

        result = memory_context.build_memory_context(
            working_memory={"goal": "核对品牌口径", "role": "founder", "scenario": "品牌复核"},
            short_term_messages=[],
            retrieved_memories=[
                {
                    "memory_id": "old-reference",
                    "content": "旧稿说可以强调治疗。",
                    "layer": "long_term_memory",
                    "status": "reference",
                    "source_type": "reference_material",
                    "importance": 0.5,
                    "recency": 0.1,
                    "semantic_relevance": 0.8,
                    "correction_count": 2,
                    "conflict": True,
                },
                {
                    "memory_id": "approved-safe",
                    "content": "对外表达必须避开医疗化承诺。",
                    "layer": "formal_knowledge",
                    "status": "approved",
                    "source_type": "approved_answer_card",
                    "importance": 0.9,
                    "recency": 0.5,
                    "semantic_relevance": 0.8,
                },
            ],
            budget={"formal_knowledge": 2, "process_memory": 2, "short_term_messages": 2},
        )

        self.assertEqual([item["memory_id"] for item in result["formal_knowledge"]], ["approved-safe"])
        self.assertEqual(result["blocked_memories"][0]["memory_id"], "old-reference")
        self.assertEqual(result["blocked_memories"][0]["blocked_reason"], "conflicted")
        self.assertGreater(result["blocked_memories"][0]["decay_score"], 0)

    def test_memory_context_limits_process_hints_and_marks_context_overflow(self):
        memory_context = load_module("hxy_memory_context_budget", "apps/api/hxy_knowledge/memory_context.py")

        retrieved = [
            {
                "memory_id": f"process-{idx}",
                "content": f"过程记忆 {idx}",
                "layer": "long_term_memory",
                "status": "process",
                "source_type": "process_memory",
                "importance": 0.5 + idx / 10,
                "recency": 0.5,
                "semantic_relevance": 0.6,
            }
            for idx in range(5)
        ]

        result = memory_context.build_memory_context(
            working_memory={"goal": "整理口径", "role": "team", "scenario": "经营问答"},
            short_term_messages=[{"role": "user", "content": str(idx)} for idx in range(6)],
            retrieved_memories=retrieved,
            budget={"formal_knowledge": 2, "process_memory": 2, "short_term_messages": 3},
        )

        self.assertEqual(len(result["process_memory_hints"]), 2)
        self.assertEqual(len(result["short_term_context"]), 3)
        self.assertTrue(result["context_budget"]["context_overflow"])
        self.assertEqual(result["storage_temperature"]["process-4"], "hot")


if __name__ == "__main__":
    unittest.main()
