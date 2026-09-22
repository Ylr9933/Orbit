"""Metadata-only discovery, fail-closed opt-in and actionable CLI results."""

import json
from importlib.metadata import Distribution, EntryPoint
from pathlib import Path

import pytest

from agent_infra.benchmarks.api import AdapterIdentity
from agent_infra.benchmarks.registry import (
    AdapterConfig,
    AdapterError,
    AdapterRegistry,
    EnabledAdapter,
    load_config,
)
from agent_infra.bootstrap.benchmarks import benchmark_action
from agent_infra.gateways.cli.main import run

EXAMPLE = Path(__file__).resolve().parents[3] / "examples/benchmark-adapter"


def distribution(path: Path, entry: str = "contract-demo", group: str = "v1") -> Distribution:
    path.mkdir()
    (path / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: agent-infra-benchmark-example\nVersion: 0.1.0\n"
    )
    (path / "entry_points.txt").write_text(
        f"[agent_infra.benchmarks.{group}]\n{entry} = agent_infra_benchmark_example:Adapter\n"
    )
    return Distribution.at(path)


def enabled(**updates: str) -> AdapterConfig:
    values = dict(
        alias="demo",
        distribution="agent-infra-benchmark-example",
        version="0.1.0",
        entry_point="contract-demo",
        sdk_version="1.0",
    )
    values.update(updates)
    return AdapterConfig(schema_version=1, adapters=(EnabledAdapter(**values),))


def test_inventory_does_not_import_even_enabled_package(tmp_path, monkeypatch):
    package = tmp_path / "agent_infra_benchmark_example.py"
    marker = tmp_path / "imported"
    package.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(EntryPoint, "load", lambda self: pytest.fail("unexpected adapter import"))
    installed = [distribution(tmp_path / "demo.dist-info")]
    registry = AdapterRegistry(enabled(), installed=installed)
    assert registry.inventory()[0]["enabled_as"] == ["demo"]
    assert not marker.exists()
    disabled = AdapterRegistry(load_config(None), installed=installed)
    with pytest.raises(AdapterError, match="not explicitly enabled"):
        disabled.load("demo")
    assert not marker.exists()


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"version": "0.2.0"}, "version mismatch"),
        ({"sdk_version": "2.0"}, "SDK mismatch"),
        ({"entry_point": "other"}, "entry point"),
        ({"distribution": "uninstalled"}, "installed distribution"),
    ],
)
def test_bad_configuration_rejected_before_loading(tmp_path, updates, expected, monkeypatch):
    monkeypatch.setattr(EntryPoint, "load", lambda self: pytest.fail("unexpected adapter import"))
    registry = AdapterRegistry(
        enabled(**updates), installed=[distribution(tmp_path / "demo.dist-info")]
    )
    with pytest.raises(AdapterError, match=expected):
        registry.load("demo")


@pytest.mark.parametrize(
    "kind", ["bad_descriptor", "wrong_sdk", "missing_methods", "broken_factory"]
)
def test_factory_contract_failures_have_actionable_errors(tmp_path, monkeypatch, kind):
    from types import SimpleNamespace

    from agent_infra.benchmarks.api import AdapterDescriptor

    def factory():
        if kind == "broken_factory":
            raise ImportError("fixture dependency unavailable")
        if kind == "bad_descriptor":
            return SimpleNamespace(descriptor={"adapter_id": "not-an-sdk-object"})
        sdk = "2.0" if kind == "wrong_sdk" else "1.0"
        return SimpleNamespace(
            descriptor=AdapterDescriptor(adapter_id="test", sdk_version=sdk, description="Fixture")
        )

    monkeypatch.setattr(EntryPoint, "load", lambda self: factory)
    registry = AdapterRegistry(enabled(), installed=[distribution(tmp_path / "demo.dist-info")])
    with pytest.raises(AdapterError):
        registry.load("demo")


def test_ambiguous_distribution_and_incompatible_entry_group_fail(tmp_path):
    first = distribution(tmp_path / "one.dist-info")
    second = distribution(tmp_path / "two.dist-info")
    with pytest.raises(AdapterError, match="found 2"):
        AdapterRegistry(enabled(), installed=[first, second]).load("demo")
    wrong_sdk = distribution(tmp_path / "v2.dist-info", group="v2")
    with pytest.raises(AdapterError, match="found 0"):
        AdapterRegistry(enabled(), installed=[wrong_sdk]).load("demo")


def test_loading_exact_identity_and_duplicate_config(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    registry = AdapterRegistry(enabled(), installed=[distribution(tmp_path / "demo.dist-info")])
    loaded = registry.load("demo")
    assert registry.load_identity(loaded.identity).identity == loaded.identity
    stale = AdapterIdentity(**{**loaded.identity.model_dump(), "adapter_id": "replaced"})
    with pytest.raises(AdapterError, match="identity changed"):
        registry.load_identity(stale)
    stale = AdapterIdentity(**{**loaded.identity.model_dump(), "version": "0.2.0"})
    with pytest.raises(AdapterError, match="explicitly enabled"):
        registry.load_identity(stale)
    path = tmp_path / "adapters.toml"
    path.write_text((EXAMPLE / "adapters.toml").read_text() + "\nunknown = true\n")
    with pytest.raises(ValueError, match="Extra inputs"):
        load_config(path)
    with pytest.raises(ValueError, match="aliases must be unique"):
        AdapterConfig(schema_version=1, adapters=enabled().adapters * 2)


def test_cli_plan_check_inspect_and_disabled_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    installed = [distribution(tmp_path / "demo.dist-info")]
    monkeypatch.setattr("agent_infra.benchmarks.registry.distributions", lambda: installed)

    def cli(*arguments):
        return run(
            lambda path: {},
            lambda provider: {},
            lambda provider: {},
            lambda: {},
            lambda path: {},
            ["benchmark", *arguments],
            benchmark_action=benchmark_action,
        )

    config = ["--config", str(EXAMPLE / "adapters.toml")]
    source = EXAMPLE / "fixtures/terminal-like"
    with pytest.raises(SystemExit) as rejected:
        cli("inspect", "demo", "--source", str(source))
    assert rejected.value.code == 2
    assert "not explicitly enabled" in capsys.readouterr().err
    assert cli("inspect", "demo", "--source", str(source), *config) == 0
    output = capsys.readouterr().out
    assert "private-tests" not in output and "native_config" not in output
    assert json.loads(output)["synthetic"] is True
    plan = tmp_path / "plan.json"
    assert (
        cli(
            "plan",
            "demo",
            "--source",
            str(source),
            "--request",
            str(source / "request.json"),
            "--output",
            str(plan),
            *config,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["runtime_ready"] is False
    assert cli("check", str(plan), *config) == 1
    assert json.loads(capsys.readouterr().out)["compatible"] is False
    assert (
        cli("check", str(plan), "--capabilities", str(EXAMPLE / "capabilities.json"), *config) == 0
    )
    assert json.loads(capsys.readouterr().out)["runtime_ready"] is False
