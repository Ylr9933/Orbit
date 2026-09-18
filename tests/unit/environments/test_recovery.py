"""An interrupted Docker create cannot be declared released just because it is absent."""

import json
import subprocess

import pytest

from agent_infra.environments import recovery


def test_unacknowledged_create_quarantines_absent_container(tmp_path, monkeypatch):
    root = tmp_path / "handle"
    root.mkdir()
    journal = root / "ownership.json"
    entry = {
        "owner": "a" * 32,
        "name": "agent-infra-" + "a" * 12 + "-" + "b" * 12,
        "key": "run:solver",
        "image_id": "sha256:image",
        "lifecycle": "creating",
    }
    recovery.write_ownership(journal, entry)
    monkeypatch.setattr(
        recovery.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )
    with pytest.raises(RuntimeError, match="quarantined"):
        recovery.recover_owned_containers(tmp_path)
    assert json.loads(journal.read_text())["lifecycle"] == "creating"
    recovery.write_ownership(journal, entry | {"lifecycle": "removed"})
    assert recovery.recover_owned_containers(tmp_path) == ()
