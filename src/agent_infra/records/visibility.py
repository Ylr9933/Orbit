"""Shared read boundaries for user-facing events, trajectories and artifacts."""

from agent_infra.records.api import DataClass, Visibility

_PRIVATE = frozenset({DataClass.PRIVATE_EVALUATION, DataClass.CREDENTIAL, DataClass.SECRET})


def event_visible(data_class: DataClass, visibility: Visibility) -> bool:
    """Controller lifecycle events are public summaries; evaluator/admin events are not."""
    return data_class not in _PRIVATE and visibility not in {Visibility.EVALUATOR, Visibility.ADMIN}


def artifact_visible(data_class: DataClass, visibility: Visibility) -> bool:
    """Artifact contents require explicit Agent/User visibility, not just controller access."""
    return data_class not in _PRIVATE and visibility in {Visibility.USER, Visibility.AGENT}
