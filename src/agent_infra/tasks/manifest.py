"""Strict, bounded YAML loading and filesystem validation; never executes source code."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from agent_infra.tasks.api import (
    FieldState,
    Material,
    Provenance,
    TaskDefinition,
    TaskIssue,
    TaskSection,
    TaskSnapshot,
)

SECTIONS = ("tools", "resource_intent", "environment", "outputs", "evaluation", "execution_policy")


def mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a string-keyed mapping")
    return value


def string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    items = tuple(string(item, field) for item in value)
    if len(items) != len(set(items)):
        raise ValueError(f"{field} contains duplicates")
    return items


def only_keys(data: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown {field} fields: {', '.join(sorted(unknown))}")


def canonical(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError) as error:
        raise ValueError("manifest values must be finite JSON-compatible values") from error


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in value:
        raise ValueError("material path must be a non-empty relative path without traversal")
    return path


def resolve_material(root: Path, source: str) -> Path:
    relative = relative_path(source)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("material symlinks are not supported")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("material path escapes root")
    return current


def content_digest(path: Path) -> str:
    """Hash names and contents, including empty directories; reject links and special files."""
    digest = hashlib.sha256()

    def visit(item: Path, name: str) -> None:
        if item.is_symlink():
            raise ValueError("material symlinks are not supported")
        if item.is_file():
            digest.update(canonical(["file", name]).encode())
            file_digest = hashlib.sha256()
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    file_digest.update(chunk)
            digest.update(file_digest.digest())
        elif item.is_dir():
            digest.update(canonical(["directory", name]).encode())
            for child in sorted(item.iterdir()):
                visit(child, f"{name}/{child.name}")
        else:
            raise ValueError("material is missing or is not a regular file/directory")

    visit(path, ".")
    return "sha256:" + digest.hexdigest()


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("task manifest exceeds 1 MiB")
    try:
        tokens = yaml.scan(raw)
        for token in tokens:
            if isinstance(token, yaml.tokens.AliasToken | yaml.tokens.AnchorToken):
                raise ValueError("YAML anchors and aliases are not supported")
        node = yaml.compose(raw, Loader=yaml.SafeLoader)

        def check(current: yaml.Node, depth: int = 0) -> None:
            if depth > 32:
                raise ValueError("manifest nesting exceeds 32 levels")
            if isinstance(current, yaml.MappingNode):
                keys: set[str] = set()
                for key, value in current.value:
                    if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                        raise ValueError("YAML keys must be strings")
                    if key.value in keys or key.value == "<<":
                        raise ValueError("duplicate keys and YAML merges are not supported")
                    keys.add(key.value)
                    check(value, depth + 1)
            elif isinstance(current, yaml.SequenceNode):
                for value in current.value:
                    check(value, depth + 1)

        if node is not None:
            check(node)
        return mapping(yaml.safe_load(raw), "task")
    except (yaml.YAMLError, UnicodeError, RecursionError) as error:
        raise ValueError("invalid task YAML") from error


def _section(value: object, name: str) -> TaskSection:
    data = mapping(value, name)
    state = FieldState(data.get("state", "unspecified"))
    body = {key: item for key, item in data.items() if key != "state"}
    if state is not FieldState.SPECIFIED and body:
        raise ValueError(f"{name}: unspecified/none/unknown cannot contain assumed values")
    if state is FieldState.SPECIFIED and not body:
        raise ValueError(f"{name}: specified requires content")
    if state is FieldState.SPECIFIED:
        _validate_section_body(name, body)
    return TaskSection(state, canonical(body))


def _validate_section_body(name: str, body: dict[str, Any]) -> None:
    allowed = {
        "tools": {"items"},
        "resource_intent": {"constraints", "provenance"},
        "environment": {"native_ref", "image", "provenance"},
        "outputs": {"items"},
        "evaluation": {"evaluator_ref", "audiences", "feedback"},
        "execution_policy": {"native_ref", "provenance"},
    }
    only_keys(body, allowed[name], name)
    if name in {"tools", "outputs"}:
        items = body.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"{name}.items must be non-empty; use state none for no items")
        for raw in items:
            item = mapping(raw, name)
            if name == "outputs":
                only_keys(item, {"path", "required", "provenance"}, "output")
                relative_path(string(item.get("path"), "output.path"))
            else:
                only_keys(
                    item,
                    {"tool_id", "version", "required", "transport", "scope", "provenance"},
                    "tool",
                )
                string(item.get("tool_id"), "tool_id")
                string(item.get("version"), "tool.version")
                if item.get("transport") not in {"mcp", "cli", "function"}:
                    raise ValueError("unsupported tool transport")
                string(item.get("scope"), "tool.scope")
            if type(item.get("required")) is not bool:
                raise ValueError(f"{name}.required must be boolean")
    elif name == "resource_intent":
        from agent_infra.resources.config import parse_bytes

        bounds = mapping(body.get("constraints"), "constraints")
        only_keys(
            bounds,
            {"cpu_min", "cpu_max", "memory_min", "memory_max", "gpu_min", "gpu_max"},
            "constraints",
        )
        normalized: dict[str, float] = {}
        for key, raw in bounds.items():
            if key.startswith("memory"):
                normalized[key] = float(parse_bytes(raw, key, allow_zero=True))
            else:
                if (
                    isinstance(raw, bool)
                    or not isinstance(raw, int | float)
                    or not math.isfinite(raw)
                    or raw < 0
                ):
                    raise ValueError("resource bounds must be finite nonnegative numbers")
                if key.startswith("gpu") and type(raw) is not int:
                    raise ValueError("GPU bounds must be integers")
                normalized[key] = float(raw)
        for resource in ("cpu", "memory", "gpu"):
            if normalized.get(f"{resource}_min", 0) > normalized.get(f"{resource}_max", math.inf):
                raise ValueError("resource minimum exceeds maximum")
    elif name == "evaluation":
        string(body.get("evaluator_ref"), "evaluator_ref")
        if set(strings(body.get("audiences"), "evaluation.audiences")) != {
            "evaluator",
            "controller",
        }:
            raise ValueError("private evaluation requires evaluator/controller audiences")
        if body.get("feedback") not in {"none", "after_submission", "native"}:
            raise ValueError("invalid evaluation feedback")
    else:
        if not body.get("native_ref") and not (name == "environment" and body.get("image")):
            raise ValueError(f"{name} requires a native reference or environment image")


def parse_task(data: dict[str, Any], *, root: Path) -> TaskDefinition:
    only_keys(
        data,
        {
            "schema_version",
            "task_id",
            "revision",
            "mode",
            "source",
            "instructions",
            "materials",
            "user_context",
            "extensions",
            *SECTIONS,
        },
        "task",
    )
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    mode = string(data.get("mode"), "mode")
    if mode not in {"research", "benchmark"}:
        raise ValueError("mode must be research or benchmark")
    source = mapping(data.get("source"), "source")
    if mode == "benchmark" and not all(source.get(key) for key in ("native_id", "revision")):
        raise ValueError("benchmark source requires native_id and revision")
    raw_materials = data.get("materials", [])
    if not isinstance(raw_materials, list):
        raise ValueError("materials must be a list")
    materials = []
    for raw in raw_materials:
        item = mapping(raw, "material")
        only_keys(
            item,
            {
                "id",
                "role",
                "kind",
                "source",
                "description",
                "audiences",
                "target",
                "access",
                "availability",
                "provenance",
                "media_type",
                "digest",
            },
            "material",
        )
        audience = strings(item.get("audiences"), "audiences")
        if not audience or set(audience) - {"solver", "evaluator", "controller"}:
            raise ValueError("invalid material audiences")
        kind = string(item.get("kind"), "kind")
        if kind not in {"file", "directory"}:
            raise ValueError("only materialized file/directory sources are supported")
        access = item.get("access", "read_only")
        if access not in {"read_only", "writable_copy"}:
            raise ValueError("invalid access")
        availability = item.get("availability", "present")
        if availability not in {"present", "missing", "needs_input"}:
            raise ValueError("generated sources must be materialized by a native adapter first")
        provenance = mapping(item.get("provenance"), "provenance")
        only_keys(provenance, {"origin", "evidence"}, "provenance")
        origin = string(provenance.get("origin"), "origin")
        if origin not in {"user", "native", "adapter", "agent_proposed"}:
            raise ValueError("invalid provenance origin")
        evidence = provenance.get("evidence")
        if evidence is not None:
            evidence = string(evidence, "evidence")
        target = item.get("target")
        if target is not None:
            relative_path(string(target, "target"))
        if "solver" in audience and target is None:
            raise ValueError("solver material requires a target")
        source_path = string(item.get("source"), "material source")
        relative_path(source_path)
        checksum = item.get("digest")
        if checksum is not None and (
            not isinstance(checksum, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", checksum)
        ):
            raise ValueError("invalid material digest")
        media_type = item.get("media_type")
        if media_type is not None:
            media_type = string(media_type, "media_type")
        materials.append(
            Material(
                string(item.get("id"), "material id"),
                string(item.get("role"), "role"),
                kind,
                source_path,
                string(item.get("description"), "description"),
                audience,
                target,
                access,
                availability,
                Provenance(origin, evidence),
                media_type,
                checksum,
            )
        )
    sections = {name: _section(data.get(name, {"state": "unspecified"}), name) for name in SECTIONS}
    return TaskDefinition(
        task_id=string(data.get("task_id"), "task_id"),
        revision=string(data.get("revision"), "revision"),
        mode=mode,
        root=root.resolve(),
        source_json=canonical(source),
        instructions=strings(data.get("instructions", []), "instructions"),
        materials=tuple(materials),
        user_context=strings(data.get("user_context", []), "user_context"),
        extensions_json=canonical(mapping(data.get("extensions", {}), "extensions")),
        **sections,
    )


def load_task(path: Path) -> TaskDefinition:
    return parse_task(_read_yaml(path), root=path.parent)


def task_document(task: TaskDefinition) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "task_id": task.task_id,
        "revision": task.revision,
        "mode": task.mode,
        "source": json.loads(task.source_json),
        "instructions": list(task.instructions),
        "user_context": list(task.user_context),
        "materials": [asdict(item) for item in task.materials],
        "extensions": json.loads(task.extensions_json),
    }
    for item in data["materials"]:
        item["audiences"] = list(item["audiences"])
    for name in SECTIONS:
        section = getattr(task, name)
        data[name] = {"state": section.state.value, **json.loads(section.value_json)}
    return data


def validate_task(task: TaskDefinition) -> tuple[TaskIssue, ...]:
    issues: list[TaskIssue] = []
    for name in SECTIONS:
        section = getattr(task, name)
        try:
            _section({"state": section.state, **json.loads(section.value_json)}, name)
        except (ValueError, TypeError) as error:
            issues.append(TaskIssue("invalid_section", name, str(error)))
    ids = [item.id for item in task.materials]
    if len(ids) != len(set(ids)):
        issues.append(TaskIssue("duplicate_id", "materials", "Material IDs must be unique"))
    visible = {item.id for item in task.materials if "solver" in item.audiences}
    if not task.instructions:
        issues.append(
            TaskIssue("missing_instruction", "instructions", "Provide a task instruction")
        )
    for ref in (*task.instructions, *task.user_context):
        if ref not in visible:
            issues.append(
                TaskIssue("invalid_reference", "instructions", "Reference is not solver-visible")
            )
    targets: list[PurePosixPath] = []
    sources: list[tuple[Material, Path]] = []
    for item in task.materials:
        try:
            path = resolve_material(task.root, item.source)
            if item.availability != "present":
                raise ValueError("required material is not available")
            if (item.kind == "file" and not path.is_file()) or (
                item.kind == "directory" and not path.is_dir()
            ):
                raise ValueError("material kind does not match filesystem")
            checksum = content_digest(path)
            if item.digest is not None and checksum != item.digest:
                raise ValueError("material digest changed")
            sources.append((item, path.resolve()))
        except (OSError, ValueError) as error:
            issues.append(TaskIssue("invalid_material", item.id, str(error)))
        if "solver" in item.audiences and item.target is not None:
            target = relative_path(item.target)
            if any(target.is_relative_to(old) or old.is_relative_to(target) for old in targets):
                issues.append(TaskIssue("target_overlap", item.id, "Solver targets overlap"))
            targets.append(target)
    for item, source in sources:
        if "solver" in item.audiences:
            for private, private_source in sources:
                if "solver" not in private.audiences and (
                    private_source.is_relative_to(source) or source.is_relative_to(private_source)
                ):
                    issues.append(
                        TaskIssue("visibility_overlap", item.id, "Public/private sources overlap")
                    )
    return tuple(issues)


def freeze_task(task: TaskDefinition) -> TaskSnapshot:
    issues = validate_task(task)
    if issues:
        raise ValueError("task is not ready: " + ", ".join(issue.code for issue in issues))
    digests = tuple(
        (item.id, content_digest(resolve_material(task.root, item.source)))
        for item in task.materials
    )
    return TaskSnapshot(
        "sha256:" + hashlib.sha256(canonical(task_document(task)).encode()).hexdigest(),
        digests,
    )
