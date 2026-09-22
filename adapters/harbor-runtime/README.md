# agent-infra-harbor

Optional native Harbor execution package. Fixed upstream commit and installed-file digest;
transitive runtime dependencies are pinned in `requirements.lock`.

Core Agent Infra does not depend on this package. A trusted independent benchmark adapter
provides the factory and validates its supported task profile before launch. This runtime
reuses the durable process backend and additionally requires native container cleanup evidence.

[Boundaries and recovery](../../docs/implementation/benchmark-harbor.md)
