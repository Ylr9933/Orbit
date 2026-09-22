"""Model-free protocol exercise using the pinned PAST manifest and state primitives."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from past_bench.cli import _prepare_episode_history, _save_episode_history_anchor
from past_bench.models.self_evolve import SelfEvolveSequenceDefinition
from past_bench.runner.self_evolve import summarize_comparison, summarize_sequence, write_json


def _artifacts(present: bool) -> dict[str, Any]:
    return {
        "memory_file_exists": present,
        "user_file_exists": False,
        "memory_chars": 32 if present else 0,
        "user_chars": 0,
        "skill_count": 0,
        "skill_names": [],
    }


def _episode_result(episode: Any, index: int, *, learned: bool) -> dict[str, Any]:
    evaluation = episode.bucket in {"evaluation", "control"}
    score = 0.8 if evaluation and learned else 0.25 if evaluation else 0.5
    used = evaluation and learned
    return {
        "index": index,
        "label": episode.label,
        "task_id": Path(episode.task).name,
        "task_name": episode.label,
        "family_id": episode.family_id,
        "bucket": episode.bucket,
        "stage": episode.stage,
        "mechanism": episode.mechanism,
        "expected_persistence_signal": episode.expected_persistence_signal or episode.mechanism,
        "task_score": score,
        "passed": score >= 0.7,
        "tool_dispatch_count": 1,
        "token_usage": {"total_tokens": 0},
        "timing": {"wall_time_s": 0.0},
        "artifacts": _artifacts(learned),
        "internal_tools": {
            "memory_calls": 1 if learned else 0,
            "skill_manage_calls": 0,
            "session_search_calls": 0,
            "memory_write_count": 1 if learned else 0,
            "skill_create_count": 0,
            "skill_update_count": 0,
        },
        "retrieval_signals": {
            "used_expected_signal": used,
            "retrieval_before_first_update": used,
            "memory_read_count": 1 if used else 0,
            "session_search_count": 0,
            "skill_read_count": 0,
        },
        "mechanism_scores": {
            "mechanism_confidence": 0.9 if used else 0.0,
            "artifact_quality_score": 0.9 if learned else 0.0,
            "transfer_quality": 1.0 if used else 0.0,
            "shortcut_resistance": 1.0,
        },
        "requires_fresh_session": episode.requires_fresh_session,
        "persistence_allowed": episode.persistence_allowed,
        "history_mode": episode.history_mode,
        "history_save_anchor": episode.history_save_anchor,
        "history_load_anchor": episode.history_load_anchor,
        "infra_blocked": False,
        "engineering_fixture": True,
    }


def run(manifest: Path, output: Path) -> None:
    sequence = SelfEvolveSequenceDefinition.from_yaml(manifest)
    summaries: dict[str, dict[str, Any]] = {}
    state_evidence: list[dict[str, Any]] = []
    for variant, persistence_enabled in (
        ("with_persistence", True),
        ("without_persistence", False),
    ):
        variant_dir = output / variant
        variant_dir.mkdir(parents=True)
        state_root = variant_dir / "family_state"
        state_root.mkdir()
        anchors_dir = variant_dir / "history_anchors"
        anchors: dict[str, Path] = {}
        results = []
        for index, episode in enumerate(sequence.episodes, start=1):
            _prepare_episode_history(
                hermes_home=state_root,
                episode=episode,
                history_anchors=anchors,
            )
            marker = state_root / "learned.json"
            before = marker.exists()
            if persistence_enabled and episode.persistence_allowed and episode.bucket == "learn":
                marker.write_text(json.dumps({"learned_at": episode.label}))
            learned = persistence_enabled and episode.persistence_allowed and marker.exists()
            result = _episode_result(episode, index, learned=learned)
            results.append(result)
            _save_episode_history_anchor(
                hermes_home=state_root,
                episode=episode,
                anchors_dir=anchors_dir,
                history_anchors=anchors,
            )
            state_evidence.append(
                {
                    "variant": variant,
                    "episode": episode.label,
                    "session_id": f"{variant}:{index}",
                    "history_mode": episode.history_mode,
                    "history_save_anchor": episode.history_save_anchor,
                    "history_load_anchor": episode.history_load_anchor,
                    "state_scope": str(state_root),
                    "state_before": before,
                    "state_visible": learned,
                }
            )
        summary = summarize_sequence(
            sequence_name=sequence.name,
            variant=variant,
            episodes=results,
        )
        write_json(
            variant_dir / "sequence_results.json",
            {"sequence": sequence.name, "variant": variant, "episodes": results},
        )
        write_json(variant_dir / "sequence_summary.json", summary)
        summaries[variant] = summary
    write_json(
        output / "sequence_comparison.json",
        summarize_comparison(
            with_persistence=summaries["with_persistence"],
            without_persistence=summaries["without_persistence"],
        ),
    )
    write_json(output / "state_evidence.json", {"items": state_evidence})
