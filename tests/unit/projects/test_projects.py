"""Exercise persistence, non-clobber publication and recovery across real processes."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from agent_infra.projects import (
    InitializationStatus,
    InitRequest,
    Project,
    ProjectConflict,
    ProjectError,
    ProjectNotFound,
    ProjectStatus,
)
from agent_infra.projects import _filesystem as fs
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.rendering import render
from agent_infra.projects.service import ProjectService


def service(root: Path) -> ProjectService:
    return ProjectService(LocalProjectStore(root / "control"))


def request(root: Path, **kwargs: object) -> InitRequest:
    return InitRequest("  研究\n原始目标\n", directory=root / "experiment", **kwargs)


def test_preview_is_pure_and_rendering_is_deterministic(tmp_path: Path) -> None:
    manager = service(tmp_path)
    before = set(tmp_path.iterdir())
    preview = manager.preview(request(tmp_path, operation_id="chosen"))
    assert manager.store.list_projects() == ()
    with pytest.raises(ProjectNotFound):
        manager.store.get(preview.project.project_id)
    assert set(tmp_path.iterdir()) == before
    assert render(preview.project) == preview.files
    assert yaml.safe_load(preview.files["project.yaml"])["original_goal"] == "  研究\n原始目标\n"
    assert "Not researched yet" in preview.files["docs/background.md"]
    project = manager.initialize(request(tmp_path, operation_id="chosen"))
    assert project.project_id == preview.project.project_id


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("revision", 0),
        ("revision", True),
        ("title", " "),
        ("original_goal", ""),
        ("workspace", "relative"),
        ("created_at", "2026-09-18"),
        ("project_id", "not-a-uuid"),
        ("status", "unknown"),
    ],
)
def test_project_schema_rejects_invalid_values(tmp_path: Path, field: str, value: object) -> None:
    p = service(tmp_path).preview(request(tmp_path)).project
    document = p.to_dict()
    assert Project.from_dict(document) == p
    with pytest.raises(ProjectError):
        Project.from_dict(document | {field: value})
    with pytest.raises(ProjectError):
        Project.from_dict(document | {"surprise": True})


def test_reopen_repeat_and_preserve_user_documents(tmp_path: Path) -> None:
    first = service(tmp_path).initialize(request(tmp_path))
    workspace = Path(first.workspace)
    edited = workspace / "docs/research-goal.md"
    edited.write_text("用户自己的补充\n", encoding="utf-8")
    (workspace / "code/src/train.py").write_text("print('user code')\n")
    second = service(tmp_path).initialize(request(tmp_path))
    assert second == first
    assert service(tmp_path).get(first.workspace) == first
    assert service(tmp_path).store.list_projects() == (first,)
    assert edited.read_text() == "用户自己的补充\n"
    assert second.status == ProjectStatus.DRAFT
    assert second.initialization == InitializationStatus.READY


def test_auto_name_display_name_and_identity_are_separate(tmp_path: Path) -> None:
    manager = service(tmp_path)
    generated = manager.initialize(InitRequest("目标", root=tmp_path, operation_id="auto"))
    assert Path(generated.workspace).name.startswith("project-")
    assert manager.initialize(InitRequest("目标", root=tmp_path, operation_id="auto")) == generated
    named = manager.initialize(InitRequest("目标", root=tmp_path, name="中文 Project"))
    assert Path(named.workspace).name == "中文-Project"
    assert named.title == "中文 Project"
    assert named.project_id != generated.project_id
    explicit = manager.initialize(InitRequest("目标", directory=tmp_path / "folder", name="论文名"))
    assert explicit.title == "论文名"
    assert Path(explicit.workspace).name == "folder"


@pytest.mark.parametrize("change", ["goal", "name", "directory"])
def test_idempotency_key_cannot_be_reused_for_different_request(
    tmp_path: Path, change: str
) -> None:
    manager = service(tmp_path)
    req = request(tmp_path, operation_id="one")
    first = manager.initialize(req)
    modified = replace(
        req, **{change: tmp_path / "elsewhere" if change == "directory" else "other"}
    )
    with pytest.raises(ProjectConflict):
        manager.initialize(modified)
    assert manager.get(first.project_id) == first


@pytest.mark.parametrize("kind", ["empty", "populated", "file", "symlink"])
def test_existing_destination_is_never_taken_over(tmp_path: Path, kind: str) -> None:
    target = tmp_path / "experiment"
    if kind in {"empty", "populated"}:
        target.mkdir()
        if kind == "populated":
            (target / "mine").write_text("keep")
    elif kind == "file":
        target.write_text("keep")
    else:
        target.symlink_to(tmp_path / "missing")
    for action in (service(tmp_path).preview, service(tmp_path).initialize):
        with pytest.raises(ProjectConflict):
            action(request(tmp_path))
    if kind == "populated":
        assert (target / "mine").read_text() == "keep"
    assert service(tmp_path).store.list_projects() == ()


def test_path_traversal_and_linked_parent_are_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    manager = service(tmp_path)
    for target in (linked / "project", tmp_path / "real/../escape"):
        with pytest.raises((OSError, ProjectError)):
            manager.initialize(InitRequest("goal", directory=target))
    with pytest.raises(ProjectError, match="child"):
        manager.initialize(InitRequest("goal", directory=tmp_path / "outside", root=real))
    with pytest.raises(ProjectError, match="contain"):
        manager.initialize(InitRequest("goal", directory=tmp_path / "control/inside"))
    assert not list(real.iterdir())


def test_store_symlink_and_hardlinked_projection_are_rejected(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (tmp_path / "control").symlink_to(external, target_is_directory=True)
    with pytest.raises(OSError):
        service(tmp_path).initialize(request(tmp_path))
    assert not list(external.iterdir())
    (tmp_path / "control").unlink()
    p = service(tmp_path).initialize(request(tmp_path))
    os.link(Path(p.workspace) / "project.yaml", tmp_path / "borrowed")
    with pytest.raises(ProjectConflict):
        service(tmp_path).recover(p.project_id)


def test_empty_database_left_by_crash_is_retryable(tmp_path: Path) -> None:
    control = tmp_path / "control"
    control.mkdir()
    (control / "projects.sqlite3").touch()
    assert (
        service(tmp_path).initialize(request(tmp_path)).initialization == InitializationStatus.READY
    )


_CHILD = """
import os, sys
from pathlib import Path
from agent_infra.projects import InitRequest
from agent_infra.projects.service import ProjectService
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects import _filesystem as fs
root = Path(sys.argv[1])
phase = sys.argv[2]
manager = ProjectService(LocalProjectStore(root / "control"))
if phase == "reserved":
    original = LocalProjectStore.reserve
    def crash(self, item):
        original(self, item)
        os._exit(71)
    LocalProjectStore.reserve = crash
elif phase == "file_linked":
    original = fs.os.unlink
    def crash(name, *args, **kwargs):
        if str(name).endswith(".init-tmp"):
            os._exit(71)
        return original(name, *args, **kwargs)
    fs.os.unlink = crash
elif phase in ("files_written", "published"):
    original = fs.publish
    def crash(*args):
        if phase == "published":
            original(*args)
        os._exit(71)
    fs.publish = crash
manager.initialize(InitRequest("研究目标", directory=root / "experiment", operation_id="crash"))
"""


@pytest.mark.parametrize("phase", ["reserved", "file_linked", "files_written", "published"])
def test_process_death_then_recovery(tmp_path: Path, phase: str) -> None:
    child = subprocess.run(
        [sys.executable, "-c", _CHILD, str(tmp_path), phase],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert child.returncode == 71, child.stderr
    manager = service(tmp_path)
    pending = manager.store.list_projects()[0]
    assert pending.initialization == InitializationStatus.PENDING
    recovered = manager.recover(pending.project_id)
    assert recovered.project_id == pending.project_id
    assert recovered.initialization == InitializationStatus.READY
    assert manager.projection_matches(recovered)
    assert not list(tmp_path.glob(".agent-infra-init-*"))


@pytest.mark.parametrize("phase", ["files_written", "published"])
def test_recovery_keeps_conflicting_edits(tmp_path: Path, phase: str) -> None:
    child = subprocess.run(
        [sys.executable, "-c", _CHILD, str(tmp_path), phase],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert child.returncode == 71, child.stderr
    manager = service(tmp_path)
    pending = manager.store.list_projects()[0]
    folder = (
        tmp_path / f".agent-infra-init-{pending.project_id}"
        if phase == "files_written"
        else Path(pending.workspace)
    )
    modified = folder / "docs/background.md"
    modified.write_text("用户写入的内容")
    with pytest.raises(ProjectConflict):
        manager.recover(pending.project_id)
    assert modified.read_text() == "用户写入的内容"
    assert manager.get(pending.project_id).initialization == InitializationStatus.PENDING


def test_concurrent_initializers_share_one_project(tmp_path: Path) -> None:
    def initialize(_: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", _CHILD, str(tmp_path), "normal"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(initialize, range(4)))
    assert [p.returncode for p in results] == [0] * 4, [p.stderr for p in results]
    assert len(service(tmp_path).store.list_projects()) == 1


def test_publish_cannot_replace_even_an_empty_competing_directory(tmp_path: Path) -> None:
    (tmp_path / "stage").mkdir()
    (tmp_path / "stage/mine").write_text("mine")
    target = tmp_path / "target"
    target.mkdir()
    with fs.directory(tmp_path) as parent, pytest.raises(ProjectConflict):
        fs.publish(parent, "stage", "target")
    assert list(target.iterdir()) == []
    assert (tmp_path / "stage/mine").read_text() == "mine"


def test_metadata_cas_and_projection_recovery(tmp_path: Path) -> None:
    manager = service(tmp_path)
    p = manager.initialize(request(tmp_path))
    update_script = """
import sys
from pathlib import Path
from agent_infra.projects import ProjectConflict
from agent_infra.projects.local import LocalProjectStore
try:
    LocalProjectStore(Path(sys.argv[1])).update(sys.argv[2], expected_revision=1, title=sys.argv[3])
except ProjectConflict:
    sys.exit(4)
"""

    def update(title: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", update_script, str(manager.store.root), p.project_id, title],
            capture_output=True,
            text=True,
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ("one", "two")))
    assert sorted(r.returncode for r in results) == [0, 4], [r.stderr for r in results]
    assert not manager.projection_matches(manager.get(p.project_id))
    recovered = manager.recover(p.project_id)
    assert recovered.revision == 2
    assert recovered.original_goal == p.original_goal
    assert manager.projection_matches(recovered)


def test_metadata_projection_never_overwrites_user_edit(tmp_path: Path) -> None:
    manager = service(tmp_path)
    p = manager.initialize(request(tmp_path))
    manager.store.update(p.project_id, expected_revision=1, title="updated")
    file = Path(p.workspace) / "project.yaml"
    file.write_text(file.read_text() + "# user edit\n")
    with pytest.raises(ProjectConflict, match="edited"):
        manager.recover(p.project_id)
    assert file.read_text().endswith("# user edit\n")


def test_init_cli_from_other_directory_and_environment_defaults(tmp_path: Path) -> None:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_INFRA_")}
    environment["XDG_STATE_HOME"] = str(tmp_path / "user-state")
    environment["AGENT_INFRA_PROJECTS_DIR"] = str(tmp_path)
    args = ["agent-infra", "init", "--goal", "研究目标", "--name", "My Project"]
    preview = subprocess.run(
        [*args, "--dry-run"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert preview.returncode == 0, preview.stderr
    assert not (tmp_path / "user-state").exists()
    assert not (tmp_path / "My-Project").exists()
    made = subprocess.run(
        args, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=20
    )
    assert made.returncode == 0, made.stderr
    p = json.loads(made.stdout)["project"]
    show = subprocess.run(
        ["agent-infra", "project", "show", p["project_id"]],
        cwd="/tmp",
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert show.returncode == 0, show.stderr
    assert json.loads(show.stdout)["manifest_matches"] is True
    assert (Path(p["workspace"]) / "docs/research-plan.md").is_file()
    listing = subprocess.run(
        ["agent-infra", "project", "list"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert json.loads(listing.stdout)["projects"][0]["project_id"] == p["project_id"]


def test_cli_directory_option_alias_and_conflict_errors(tmp_path: Path) -> None:
    base = [
        "agent-infra",
        "project",
        "init",
        "--goal",
        "goal",
        "--state-dir",
        str(tmp_path / "state"),
    ]
    args = [*base, "--directory", str(tmp_path / "folder"), "--name", "display"]
    for _ in range(2):
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
    bad = subprocess.run([*args, "--goal", "different"], capture_output=True, text=True, timeout=20)
    assert bad.returncode == 2
    assert json.loads(bad.stderr)["error"] == "project_conflict"
    assert "Traceback" not in bad.stderr


def test_invalid_manifest_has_cli_error_without_traceback(tmp_path: Path) -> None:
    manager = service(tmp_path)
    p = manager.initialize(request(tmp_path))
    document = Path(p.workspace) / "project.yaml"
    document.write_text("title: [unfinished\n")
    # Path lookup parses the manifest; using an ID still allows querying durable metadata.
    result = subprocess.run(
        ["agent-infra", "project", "show", p.workspace, "--state-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "invalid_project"
    assert "Traceback" not in result.stderr
    with pytest.raises(ProjectError, match="not valid YAML"):
        manager.recover(p.project_id)
    assert document.read_text() == "title: [unfinished\n"


def test_projection_recovery_after_manifest_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = service(tmp_path)
    p = manager.initialize(request(tmp_path))
    manager.store.update(p.project_id, expected_revision=1, status=ProjectStatus.ACTIVE)

    def fail(*args: object) -> Project:
        raise OSError("interrupted after manifest publication")

    monkeypatch.setattr(manager.store, "mark_ready", fail)
    with pytest.raises(OSError, match="interrupted"):
        manager.recover(p.project_id)
    fresh = service(tmp_path)
    assert fresh.get(p.project_id).initialization == InitializationStatus.PROJECTION_PENDING
    result = fresh.recover(p.project_id)
    assert result.revision == 2 and result.status == ProjectStatus.ACTIVE
    assert fresh.projection_matches(result)


def test_independent_stores_compete_for_one_destination(tmp_path: Path) -> None:
    script = """
import sys, time
from pathlib import Path
from agent_infra.projects import InitRequest, ProjectConflict
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.service import ProjectService
root, index = Path(sys.argv[1]), sys.argv[2]
service = ProjectService(LocalProjectStore(root / ('control-' + index)))
original = service.store.reserve
def reserve(item):
    original(item)
    (root / ('barrier-' + index)).touch()
    deadline = time.monotonic() + 10
    while len(list(root.glob('barrier-*'))) < 2:
        if time.monotonic() > deadline:
            raise RuntimeError('barrier timed out')
        time.sleep(0.01)
service.store.reserve = reserve
try:
    service.initialize(InitRequest('goal', directory=root / 'shared'))
except ProjectConflict:
    sys.exit(4)
"""

    def initialize(index: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", script, str(tmp_path), str(index)],
            capture_output=True,
            text=True,
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(initialize, range(2)))
    assert sorted(r.returncode for r in results) == [0, 4], [r.stderr for r in results]
    winner = next(i for i, r in enumerate(results) if r.returncode == 0)
    manager = ProjectService(LocalProjectStore(tmp_path / f"control-{winner}"))
    project = manager.store.list_projects()[0]
    assert manager.projection_matches(project)


def test_default_user_state_can_live_behind_local_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_infra.bootstrap.projects import project_action

    home = tmp_path / "home"
    home.mkdir()
    data = tmp_path / "data-disk"
    data.mkdir()
    (home / ".local").symlink_to(data, target_is_directory=True)
    for key in list(os.environ):
        if key.startswith("AGENT_INFRA_") or key == "XDG_STATE_HOME":
            monkeypatch.delenv(key)
    monkeypatch.setenv("HOME", str(home))
    assert project_action("list", {})["projects"] == []
    assert not (data / "state").exists()
    options = {"goal": "研究目标", "directory": str(tmp_path / "experiment")}
    preview = project_action("preview", options)
    assert not (data / "state").exists()
    result = project_action("init", options)
    assert result["state_dir"] == preview["state_dir"] == str(data / "state/agent-infra")
    assert len(project_action("list", {})["projects"]) == 1
    with pytest.raises(OSError):
        project_action("list", {"state_dir": str(home / ".local/state/agent-infra")})
