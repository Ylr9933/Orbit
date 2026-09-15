"""Provider registry used by composition roots and Run orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from agent_infra.agents.api import InstallableCommandAgentAdapter


class AgentRegistry:
    def __init__(
        self,
        adapters: Iterable[InstallableCommandAgentAdapter],
        *,
        aliases: Mapping[str, str] | None = None,
    ) -> None:
        self._adapters: dict[str, InstallableCommandAgentAdapter] = {}
        for adapter in adapters:
            provider = adapter.descriptor.provider
            if provider in self._adapters:
                raise ValueError(f"Duplicate Agent provider: {provider}")
            self._adapters[provider] = adapter
        self._aliases = dict(aliases or {})
        unknown = set(self._aliases.values()) - set(self._adapters)
        if unknown:
            raise ValueError(
                f"Agent aliases target unknown providers: {', '.join(sorted(unknown))}"
            )

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def get(self, provider: str) -> InstallableCommandAgentAdapter:
        canonical = self._aliases.get(provider, provider)
        try:
            return self._adapters[canonical]
        except KeyError as error:
            supported = ", ".join(self.providers)
            raise ValueError(
                f"Unsupported Agent provider {provider!r}; choose one of: {supported}"
            ) from error
