import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "hxy-web" / "src" / "App.tsx"
NAVIGATION = ROOT / "apps" / "hxy-web" / "src" / "features" / "shell" / "Navigation.tsx"
COMPOSER = ROOT / "apps" / "hxy-web" / "src" / "features" / "composer" / "UniversalComposer.tsx"
ROOT_PACKAGE = ROOT / "package.json"
SHELL_STYLES = ROOT / "apps" / "hxy-web" / "src" / "styles" / "shell.css"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
JOURNEYS = (
    ROOT / "tests" / "fixtures" / "product-shell" / "role-journeys.json"
)

EXPECTED_STEPS = {
    "founder": [
        "询问当前开业进度",
        "查看支持结论的来源",
        "创建并指派下一项任务",
    ],
    "store_manager": [
        "打开今日待办",
        "询问门店问题",
        "上传照片或备注",
        "创建后续事项",
    ],
    "store_employee": [
        "询问该怎么说",
        "进行话术练习",
        "接收纠正",
        "上报问题",
    ],
}


class HxyProductShellContractTest(unittest.TestCase):
    def test_shell_exposes_only_the_product_frontstage_contract(self):
        self.assertTrue(APP.exists(), "React product shell App.tsx should exist")
        self.assertTrue(NAVIGATION.exists(), "product navigation should exist")
        self.assertTrue(COMPOSER.exists(), "unified composer should exist")
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (APP, NAVIGATION, COMPOSER)
        )

        for navigation_item in ["今日", "对话", "学习", "我的"]:
            self.assertIn(navigation_item, source)

        self.assertIn("问问题，或记录刚刚发生的事", source)

        for forbidden in ["claim", "chunk_id", "review queue", "/root/hxy"]:
            self.assertNotIn(forbidden, source.lower())

    def test_fixture_locks_the_three_actionable_role_journeys(self):
        payload = json.loads(JOURNEYS.read_text(encoding="utf-8"))
        journeys = payload["journeys"]

        self.assertEqual(len(journeys), 3)
        self.assertEqual({journey["role"] for journey in journeys}, set(EXPECTED_STEPS))

        for journey in journeys:
            self.assertTrue(journey.get("initial_input") or journey.get("steps"))
            self.assertEqual(journey["steps"], EXPECTED_STEPS[journey["role"]])
            self.assertGreaterEqual(len(journey.get("expected_actions", [])), 1)
            self.assertTrue(all(journey["expected_actions"]))
            self.assertGreaterEqual(len(journey.get("forbidden_scopes", [])), 1)
            self.assertTrue(all(journey["forbidden_scopes"]))

    def test_fixture_does_not_expose_internal_governance_or_server_paths(self):
        fixture_text = JOURNEYS.read_text(encoding="utf-8").lower()

        for internal_term in [
            "claim",
            "chunk_id",
            "review queue",
            "审核队列",
            "治理",
            "/root/",
        ]:
            self.assertNotIn(internal_term, fixture_text)

    def test_root_test_command_includes_product_shell_tests(self):
        package = json.loads(ROOT_PACKAGE.read_text(encoding="utf-8"))
        scripts = package["scripts"]

        self.assertIn("test:web", scripts)
        self.assertIn("npm run test:web", scripts["test"])
        self.assertIn("test:e2e", scripts)
        self.assertIn("npm run test:e2e", scripts["test"])

    def test_ci_installs_and_verifies_the_product_shell(self):
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("apps/hxy-web", workflow)
        self.assertIn("npm ci", workflow)
        self.assertIn("playwright install", workflow)
        self.assertIn("npm test", workflow)

    def test_mobile_navigation_reserves_the_device_safe_area(self):
        styles = SHELL_STYLES.read_text(encoding="utf-8")

        self.assertIn("safe-area-inset-bottom", styles)


if __name__ == "__main__":
    unittest.main()
