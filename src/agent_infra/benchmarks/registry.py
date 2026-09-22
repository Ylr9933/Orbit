"""Load only operator-enabled, exactly pinned distribution entry points.

Metadata enumeration never imports adapters. Enabled code runs with the user's
permissions: the allowlist is a trust boundary, not an execution sandbox.
"""

import json
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import Distribution, EntryPoint, distributions
from pathlib import Path
from typing import Self, cast

from pydantic import model_validator

from agent_infra.benchmarks.api import (
    ENTRY_POINT_GROUP,
    SDK_VERSION,
    AdapterDescriptor,
    AdapterIdentity,
    BenchmarkAdapter,
    Contract,
    Name,
)


class AdapterError(ValueError):
    """Actionable configuration, compatibility or adapter-boundary failure."""


class EnabledAdapter(Contract):
    alias: Name
    distribution: Name
    version: Name
    entry_point: Name
    sdk_version: Name


class AdapterConfig(Contract):
    schema_version: int
    adapters: tuple[EnabledAdapter, ...] = ()

    @model_validator(mode="after")
    def unique_aliases(self) -> Self:
        if self.schema_version != 1:
            raise ValueError("unsupported adapter configuration schema_version")
        aliases = [item.alias for item in self.adapters]
        if len(set(aliases)) != len(aliases):
            raise ValueError("adapter aliases must be unique")
        return self


def load_config(path: Path | None) -> AdapterConfig:
    if path is None:
        return AdapterConfig(schema_version=1)
    return AdapterConfig.model_validate_json(json.dumps(tomllib.loads(path.read_text())))


def _package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class LoadedAdapter:
    implementation: BenchmarkAdapter
    identity: AdapterIdentity


class AdapterRegistry:
    def __init__(
        self, config: AdapterConfig, *, installed: Iterable[Distribution] | None = None
    ) -> None:
        self._enabled = {item.alias: item for item in config.adapters}
        self._installed = tuple(distributions() if installed is None else installed)

    def inventory(self) -> list[dict[str, object]]:
        """Only metadata, including disabled packages. No EntryPoint.load calls."""
        items: list[dict[str, object]] = []
        for distribution in self._installed:
            for entry in distribution.entry_points:
                if not entry.group.startswith("agent_infra.benchmarks."):
                    continue
                aliases = [
                    spec.alias
                    for spec in self._enabled.values()
                    if _package_name(spec.distribution)
                    == _package_name(distribution.metadata["Name"])
                    and spec.version == distribution.version
                    and spec.entry_point == entry.name
                    and spec.sdk_version == SDK_VERSION
                    and entry.group == ENTRY_POINT_GROUP
                ]
                items.append(
                    {
                        "distribution": distribution.metadata["Name"],
                        "version": distribution.version,
                        "entry_point": entry.name,
                        "group": entry.group,
                        "enabled_as": sorted(aliases),
                    }
                )
        return sorted(items, key=lambda item: (str(item["distribution"]), str(item["entry_point"])))

    def _resolve(self, spec: EnabledAdapter) -> EntryPoint:
        if spec.sdk_version != SDK_VERSION:
            raise AdapterError(
                f"SDK mismatch: configured {spec.sdk_version}, available {SDK_VERSION}"
            )
        matches = [
            distribution
            for distribution in self._installed
            if _package_name(distribution.metadata["Name"]) == _package_name(spec.distribution)
        ]
        if len(matches) != 1:
            raise AdapterError(
                f"expected one installed distribution {spec.distribution}; found {len(matches)}"
            )
        distribution = matches[0]
        if distribution.version != spec.version:
            raise AdapterError(
                f"version mismatch for {spec.distribution}: "
                f"enabled {spec.version}, installed {distribution.version}"
            )
        entries = [
            entry
            for entry in distribution.entry_points
            if entry.name == spec.entry_point and entry.group == ENTRY_POINT_GROUP
        ]
        if len(entries) != 1:
            raise AdapterError(
                f"expected one {ENTRY_POINT_GROUP}:{spec.entry_point} entry point "
                f"in {spec.distribution}; found {len(entries)}"
            )
        return entries[0]

    def load(self, alias: str) -> LoadedAdapter:
        spec = self._enabled.get(alias)
        if spec is None:
            raise AdapterError(f"adapter {alias!r} is not explicitly enabled in --config")
        entry = self._resolve(spec)
        try:
            implementation = entry.load()()
            descriptor = implementation.descriptor
            if not isinstance(descriptor, AdapterDescriptor):
                raise AdapterError("adapter descriptor must use the public SDK AdapterDescriptor")
            if descriptor.sdk_version != spec.sdk_version:
                raise AdapterError("adapter descriptor SDK does not match enabled SDK")
            for method in ("discover", "plan", "validate"):
                if not callable(getattr(implementation, method, None)):
                    raise AdapterError(f"adapter is missing required planning method: {method}")
        except AdapterError:
            raise
        except Exception as error:
            raise AdapterError(f"could not load {spec.alias}: {type(error).__name__}") from error
        return LoadedAdapter(
            cast(BenchmarkAdapter, implementation),
            AdapterIdentity(
                distribution=_package_name(spec.distribution),
                version=spec.version,
                entry_point=spec.entry_point,
                adapter_id=descriptor.adapter_id,
                sdk_version=descriptor.sdk_version,
            ),
        )

    def load_identity(self, identity: AdapterIdentity) -> LoadedAdapter:
        for spec in self._enabled.values():
            if (
                _package_name(spec.distribution) == _package_name(identity.distribution)
                and spec.version == identity.version
                and spec.entry_point == identity.entry_point
                and spec.sdk_version == identity.sdk_version
            ):
                loaded = self.load(spec.alias)
                if loaded.identity.adapter_id != identity.adapter_id:
                    raise AdapterError("adapter identity changed since the plan was frozen")
                return loaded
        raise AdapterError(
            "the plan's exact adapter distribution/version must be explicitly enabled"
        )
