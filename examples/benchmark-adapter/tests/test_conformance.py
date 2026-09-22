"""Run after installing the package: python -m unittest discover -s tests."""

import unittest
from pathlib import Path

from agent_infra_benchmark_example import Adapter

from agent_infra.benchmarks.api import PlanRequest
from agent_infra.benchmarks.testing import assert_planning_conformance


class AdapterTests(unittest.TestCase):
    def test_all_protocol_shapes(self):
        fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        for source in sorted(fixtures.iterdir()):
            with self.subTest(shape=source.name):
                request = PlanRequest.model_validate_json((source / "request.json").read_bytes())
                plan = assert_planning_conformance(Adapter(), source, request)
                self.assertTrue(plan.suite.synthetic)
                self.assertEqual(plan.request, request)


if __name__ == "__main__":
    unittest.main()
