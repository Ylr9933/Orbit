import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adapter


class ScoreTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="orbit-rcb-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.req = {
            "trial": {"id": "fixture"},
            "solve": {"output": str(self.root / "solve")},
            "verify": {"output": str(self.root)},
        }

    def score(self, attempts):
        (self.root / "result.json").write_text(json.dumps({"attempts": attempts}))
        return adapter.score(self.req)

    def test_preserves_judge_errors_on_every_attempt(self):
        for index in range(3):
            for error in ("fixture judge unavailable", adapter.NO_REPORT, ""):
                if index == 0 and error == adapter.NO_REPORT:
                    continue
                with self.subTest(attempt=index + 1, error=error):
                    attempts = [{"total": 80, "items": 2, "failedItems": []}] * index
                    result = self.score([*attempts, {"error": error}])
                    self.assertTrue(result["invalid"])
                    self.assertIsNone(result["score"])
                    self.assertEqual(result["issues"], [f"judge: {error} (attempt {index + 1})"])

    def test_no_report_stays_a_valid_zero(self):
        result = self.score([{"error": adapter.NO_REPORT}])
        self.assertEqual(result["score"], 0)
        self.assertFalse(result.get("invalid", False))

    def test_successful_attempts_keep_their_mean_and_spread(self):
        result = self.score([{"total": n, "items": 2, "failedItems": []} for n in (40, 60)])
        self.assertEqual(result["score"], 50)
        self.assertFalse(result["invalid"])
        self.assertEqual(result["metrics"]["matched"], 100)
        self.assertAlmostEqual(result["metrics"]["judgeSpread"], 200 ** 0.5)

    def test_failed_checklist_items_still_invalidate_the_score(self):
        result = self.score([{"total": 40, "items": 2, "failedItems": [1]}])
        self.assertEqual(result["score"], 40)
        self.assertTrue(result["invalid"])
        self.assertIn("judge failed on 1/2 checklist items (attempt 1)", result["issues"])

    def test_solve_timeout_keeps_the_separate_verify_budget(self):
        self.req["benchmark"] = {"path": str(self.root), "config": {"venvs": ""}}
        self.req["trial"].update({
            "task": "fixture", "method": {"name": "empty", "agent": "empty"},
            "staging": str(self.root / "staging"),
        })
        with patch.object(adapter, "instruction", return_value="Fixture instruction"):
            for timeout, expected in ((None, 240), (12.5, 12.5)):
                with self.subTest(timeout=timeout):
                    self.req["trial"]["timeoutMin"] = timeout
                    self.assertEqual(adapter.solve(self.req)["spec"]["timeoutMin"], expected)
                    self.assertEqual(adapter.verify(self.req)["spec"]["timeoutMin"], 60)


if __name__ == "__main__":
    unittest.main()
