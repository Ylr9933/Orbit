import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adapter


class AdapterTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="orbit-ptb-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        task = self.repo / "src/eval/tasks/fixture"
        task.mkdir(parents=True)
        (task / "evaluate.py").write_text("# Fixture evaluator; never executed.\n")
        (self.repo / ".env").write_text("FIXTURE_KEY=not-a-secret\n")
        self.req = {
            "benchmark": {
                "path": str(self.repo),
                "config": {"hfHome": str(self.root / "cache"), "cudaCompat": ""},
            },
            "trial": {
                "task": "fixture", "staging": str(self.root / "staging"),
                "method": {"name": "native", "agent": "empty"},
            },
            "solve": {"output": str(self.root / "solve-output")},
            "verify": {"output": str(self.root / "verify-output")},
        }
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        prompt = patch.object(adapter, "get_prompt", return_value="Fixture instruction")
        prompt.start()
        self.addCleanup(prompt.stop)

    def test_verify_and_score_use_the_model_collected_by_each_method(self):
        for name, agent, workspace in (
            ("native", "empty", "/home/ben/task"),
            ("codex", "codex", "/task"),
            ("claude", "claude-code", "/task"),
            ("native", "codex", "/task"),
        ):
            with self.subTest(name=name, agent=agent):
                self.req["trial"]["method"] = {"name": name, "agent": agent}
                solve = adapter.solve(self.req)["spec"]
                self.assertEqual(solve["collect"], [f"{workspace}/final_model"])
                model = Path(self.req["solve"]["output"]) / "collected" / workspace.lstrip("/") / "final_model"
                model.mkdir(parents=True, exist_ok=True)
                verify = adapter.verify(self.req)["spec"]
                self.assertIn(f'--model-path "/solve-out/collected{workspace}/final_model"',
                              verify["command"][-1])
                self.assertIn({"source": self.req["solve"]["output"],
                               "target": "/solve-out", "mode": "ro"}, verify["mounts"])
                self.assertTrue(adapter.score(self.req)["invalid"])
                metrics = Path(self.req["verify"]["output"]) / "metrics.json"
                metrics.parent.mkdir(parents=True, exist_ok=True)
                metrics.write_text(json.dumps({"accuracy": 0.625}))
                self.assertEqual(adapter.score(self.req)["score"], 62.5)
                self.assertFalse(adapter.score(self.req)["invalid"])
                metrics.unlink()
                model.rmdir()

    def test_missing_model_stays_a_valid_zero_for_native_and_empty(self):
        for name in ("native", "empty"):
            with self.subTest(name=name):
                self.req["trial"]["method"] = {"name": name, "agent": "empty"}
                result = adapter.score(self.req)
                self.assertEqual(result["score"], 0)
                self.assertFalse(result["invalid"])
                self.assertEqual(result["issues"], ["no final_model produced"])

    def test_only_native_can_access_dotenv(self):
        custom = self.root / "agent.env"
        custom.write_text("FIXTURE_KEY=custom-fixture\n")
        for dotenv in (self.repo / ".env", custom):
            with patch.dict(os.environ, {"AGENT_ENV": str(dotenv)} if dotenv == custom else {}):
                for name, agent in (("native", "empty"), ("empty", "empty"),
                                    ("codex", "codex"), ("claude", "claude-code"),
                                    ("native", "codex")):
                    with self.subTest(name=name, agent=agent, dotenv=dotenv.name):
                        self.req["trial"]["method"] = {"name": name, "agent": agent}
                        spec = adapter.solve(self.req)["spec"]
                        if name == "native" and agent == "empty":
                            self.assertEqual(spec["env"]["AGENT_ENV"], "/env/.env")
                            self.assertIn({"source": str(dotenv), "target": "/env/.env",
                                           "mode": "ro"}, spec["mounts"])
                        else:
                            self.assertNotIn("AGENT_ENV", spec["env"])
                            for mount in spec["mounts"]:
                                source = Path(mount["source"])
                                for secret in (dotenv, self.repo / ".env"):
                                    self.assertNotEqual(source, secret)
                                    self.assertNotIn(source, secret.parents)

    def test_native_without_dotenv_has_no_agent_env(self):
        (self.repo / ".env").unlink()
        spec = adapter.solve(self.req)["spec"]
        self.assertNotIn("AGENT_ENV", spec["env"])
        self.assertFalse(any(m["target"] == "/env/.env" for m in spec["mounts"]))

    def test_solve_timeout_keeps_the_separate_verify_budget(self):
        for timeout, expected in ((None, 660), (12.5, 12.5)):
            with self.subTest(timeout=timeout):
                self.req["trial"]["timeoutMin"] = timeout
                self.assertEqual(adapter.solve(self.req)["spec"]["timeoutMin"], expected)
                self.assertEqual(adapter.verify(self.req)["spec"]["timeoutMin"], 60)


if __name__ == "__main__":
    unittest.main()
