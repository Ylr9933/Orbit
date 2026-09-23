"""PAST-Bench local native runner using the generic durable process supervisor."""

from agent_infra.environments.managed_process import ManagedProcessBackend

from .request import BACKEND, FEATURES


class PastBenchBackend(ManagedProcessBackend):
    backend_id = BACKEND
    features = FEATURES
    cleanup_scope = "owned_process_group"
