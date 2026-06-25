import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HxyBrainToolsTest(unittest.TestCase):
    def test_ocr_candidate_selection_prioritizes_competitor_and_long_hxy_images(self):
        ocr = load_script("ocr_hxy_key_images", "scripts/ocr-hxy-key-images.py")
        assets = [
            {
                "relative_path": "knowledge/raw/inbox/荷小悦资料/hxyip (1).png",
                "extension": ".png",
                "metadata": {"width": 1900, "height": 2206},
            },
            {
                "relative_path": "knowledge/raw/inbox/荷小悦资料/参考品牌/长风拨筋/菜单.jpg",
                "extension": ".jpg",
                "metadata": {"width": 1080, "height": 19749},
            },
            {
                "relative_path": "knowledge/raw/inbox/荷小悦相关/战略长图.png",
                "extension": ".png",
                "metadata": {"width": 2560, "height": 21600},
            },
        ]

        selected = ocr.select_ocr_candidates(assets, include_long=True)

        paths = [item["relative_path"] for item in selected]
        self.assertIn("knowledge/raw/inbox/荷小悦资料/参考品牌/长风拨筋/菜单.jpg", paths)
        self.assertIn("knowledge/raw/inbox/荷小悦相关/战略长图.png", paths)
        self.assertNotIn("knowledge/raw/inbox/荷小悦资料/hxyip (1).png", paths)

    def test_ocr_candidate_selection_skips_extreme_long_images_by_default(self):
        ocr = load_script("ocr_hxy_key_images_default", "scripts/ocr-hxy-key-images.py")
        assets = [
            {
                "relative_path": "knowledge/raw/inbox/荷小悦资料/参考品牌/长风拨筋/超长滚动截图.jpg",
                "extension": ".jpg",
                "metadata": {"width": 1080, "height": 19749},
            },
            {
                "relative_path": "knowledge/raw/inbox/荷小悦资料/参考品牌/长风拨筋/清晰证书.jpg",
                "extension": ".jpg",
                "metadata": {"width": 2275, "height": 1279},
            },
        ]

        selected = ocr.select_ocr_candidates(assets)

        paths = [item["relative_path"] for item in selected]
        self.assertIn("knowledge/raw/inbox/荷小悦资料/参考品牌/长风拨筋/清晰证书.jpg", paths)
        self.assertNotIn("knowledge/raw/inbox/荷小悦资料/参考品牌/长风拨筋/超长滚动截图.jpg", paths)

    def test_search_scores_domain_filtered_keyword_matches(self):
        search = load_script("search_hxy_knowledge", "scripts/search-hxy-knowledge.py")
        chunks = [
            {
                "title": "荷小悦小店模型",
                "relative_path": "knowledge/normalized/store_model/pilot/model.md",
                "knowledge_domain": "store_model",
                "project_stage": "pilot",
                "text": "小店模型需要关注面积、技师配置和回本周期。",
            },
            {
                "title": "竞品报告",
                "relative_path": "knowledge/normalized/competitor/preparation/naiwan.md",
                "knowledge_domain": "competitor",
                "project_stage": "preparation",
                "text": "奈晚推拿的价格体系和门店模型值得参考。",
            },
        ]

        results = search.search_chunks(chunks, "小店模型", domain="store_model", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "荷小悦小店模型")
        self.assertGreater(results[0]["score"], 0)

    def test_brain_report_extracts_keyword_evidence_with_source_paths(self):
        brain = load_script("build_hxy_brain_report", "scripts/build-hxy-brain-report.py")
        chunks = [
            {
                "title": "荷小悦项目介绍",
                "relative_path": "knowledge/normalized/product/preparation/project.md",
                "knowledge_domain": "product",
                "project_stage": "preparation",
                "text": "荷小悦主打泡脚和按摩，强调草本泡脚养生。",
            },
            {
                "title": "小店模型",
                "relative_path": "knowledge/normalized/store_model/pilot/model.md",
                "knowledge_domain": "store_model",
                "project_stage": "pilot",
                "text": "单店模型关注投资、回本周期、面积和技师配置。",
            },
        ]

        evidence = brain.collect_evidence(chunks, {"product": ["泡脚"], "store_model": ["回本"]}, limit_per_topic=3)

        self.assertEqual(evidence["product"][0]["relative_path"], "knowledge/normalized/product/preparation/project.md")
        self.assertEqual(evidence["store_model"][0]["relative_path"], "knowledge/normalized/store_model/pilot/model.md")


if __name__ == "__main__":
    unittest.main()
