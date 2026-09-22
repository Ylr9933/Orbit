"""Compose installed adapters and read-only benchmark planning use cases."""

import argparse

from agent_infra.benchmarks.api import CapabilityProfile, PlanRequest
from agent_infra.benchmarks.planning import (
    check_plan,
    discover,
    freeze_plan,
    read_plan,
    write_plan,
)
from agent_infra.benchmarks.registry import AdapterRegistry, load_config
from agent_infra.bootstrap.benchmark_execution import execution_action


def benchmark_action(args: argparse.Namespace) -> dict[str, object]:
    config = load_config(args.config)
    registry = AdapterRegistry(config)
    action = args.benchmark_command
    if action in {
        "prepare",
        "run",
        "status",
        "cancel",
        "reconcile",
        "queue",
        "events",
        "artifacts",
    }:
        return execution_action(args, registry)
    if action == "adapters":
        return {
            "configured": [item.model_dump(mode="json") for item in config.adapters],
            "installed": registry.inventory(),
            "imports_performed": False,
        }
    if action == "check":
        frozen = read_plan(args.plan)
        loaded = registry.load_identity(frozen.adapter)
        profile = (
            CapabilityProfile.model_validate_json(args.capabilities.read_bytes())
            if args.capabilities
            else CapabilityProfile()
        )
        issues = check_plan(frozen, loaded, profile)
        return {
            "compatible": not any(issue.severity == "error" for issue in issues),
            "scope": "offline_declared_capabilities",
            "runtime_ready": False,
            "issues": [issue.model_dump(mode="json") for issue in issues],
            "limitation": "BM00 checks declarations only; no benchmark execution or attestation",
            "digest": frozen.digest,
        }
    loaded = registry.load(args.adapter)
    if action == "inspect":
        catalog, snapshot = discover(loaded, args.source)
        return {
            "adapter": loaded.identity.model_dump(mode="json"),
            "benchmark": catalog.suite.benchmark,
            "profile": catalog.suite.profile,
            "synthetic": catalog.suite.synthetic,
            "source_digest": snapshot.digest,
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "native_id": unit.native_id,
                    "kind": unit.kind,
                    "episodes": len(unit.episodes),
                    "conditions": len(unit.conditions),
                }
                for unit in catalog.units
            ],
        }
    if args.output.resolve().is_relative_to(args.source.resolve()):
        raise ValueError("write the frozen plan outside its immutable source directory")
    request = PlanRequest.model_validate_json(args.request.read_bytes())
    frozen = freeze_plan(loaded, args.source, request)
    write_plan(frozen, args.output)
    return {
        "planning_valid": True,
        "runtime_ready": False,
        "output": str(args.output),
        "digest": frozen.digest,
        "units": [unit.unit_id for unit in frozen.plan.units],
        "synthetic": frozen.plan.suite.synthetic,
        "next": "benchmark check PLAN --config CONFIG; prepare requires execution support",
    }
