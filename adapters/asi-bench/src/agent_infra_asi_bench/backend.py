"""Durable process backend; cleanup is confined to the owned process group."""

from agent_infra.environments.managed_process import ManagedProcessBackend

from .request import BACKEND, FEATURES


class AsiBenchBackend(ManagedProcessBackend):
    backend_id = BACKEND
    features = FEATURES
    cleanup_scope = "owned_process_group"
