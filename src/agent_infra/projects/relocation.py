"""Explicit rebind after a user moves a workspace; never move or merge their files."""

from pathlib import Path

from agent_infra.projects import _filesystem as fs
from agent_infra.projects.api import InitializationStatus, Project, ProjectConflict, ProjectError
from agent_infra.projects.local import LocalProjectStore
from agent_infra.projects.service import ProjectService


def rebind_project(
    store: LocalProjectStore, project_id: str, destination: Path, *, expected_revision: int
) -> Project:
    destination = fs.absolute(destination)
    service = ProjectService(store)
    if type(expected_revision) is not int or expected_revision < 1:
        raise ProjectError("expected_revision must be a positive integer")
    with store.writer():
        item = store.get(project_id)
        project = item.project
        if destination == Path(project.workspace):
            if project.revision not in {expected_revision, expected_revision + 1}:
                raise ProjectConflict("project revision changed")
            return service._recover(item)
        if (
            project.initialization != InitializationStatus.READY
            or project.revision != expected_revision
        ):
            raise ProjectConflict("project changed; reload or recover before rebinding")
        old = Path(project.workspace)
        if old.exists() or old.is_symlink():
            raise ProjectConflict(
                "old workspace still exists; move it before rebinding, do not clone its identity"
            )
        if destination.is_relative_to(store.root) or store.root.is_relative_to(destination):
            raise ProjectError("workspace and control state must not contain one another")
        with fs.directory(destination) as root:
            # Exact managed manifest and marker prove the moved workspace identity.
            if fs.read_file(root, "project.yaml") != item.snapshot["project.yaml"].encode():
                raise ProjectConflict("moved workspace manifest differs from the stored project")
            with fs.child_directory(root, ".agent-infra") as marker:
                if (
                    fs.read_file(marker, "project.json")
                    != item.snapshot[".agent-infra/project.json"].encode()
                ):
                    raise ProjectConflict("moved workspace identity marker differs")
        store.reserve_rebind(project_id, str(destination), expected_revision)
        return service._recover(store.get(project_id))
