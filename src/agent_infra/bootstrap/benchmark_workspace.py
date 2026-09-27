"""Compose registered batches and run evidence for the administrator workspace."""

from pathlib import Path
from typing import Any

from agent_infra.benchmarks.batch import BatchPlan
from agent_infra.benchmarks.execution import read_execution
from agent_infra.projects.benchmark_workspace import BenchmarkWorkspaceStore
from agent_infra.records.api import DataClass, Visibility
from agent_infra.records.local import LocalRecordsStore
from agent_infra.runs.benchmark_evidence import BenchmarkEvidence
from agent_infra.runs.benchmark_views import compare_runs, digest, project_run, summarize_runs
from agent_infra.runs.control_store import RunControlStore


def _real_path(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("批次与状态路径不能包含符号链接")


def _batch(path: Path) -> BatchPlan:
    _real_path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024**2:
        raise ValueError("需要有效的 batch.json（不超过 8 MiB）")
    return BatchPlan.model_validate_json(path.read_bytes())


class BenchmarkWorkspace:
    def __init__(self, state: Path) -> None:
        self.state = state
        self.metadata = BenchmarkWorkspaceStore(state / "benchmarks" / "console")

    def register(self, body: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(body.get("path", ""))).expanduser()
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise ValueError("请输入已有批次的绝对目录路径")
        _real_path(path)
        _real_path(path / "state/benchmarks/control.sqlite3")
        path = path.resolve()
        batch = _batch(path / "batch.json")
        for member in batch.members:
            execution = (path / member.execution).resolve()
            if not execution.is_relative_to(path) or not execution.is_file():
                raise ValueError("批次执行计划缺失或越界")
            if read_execution(execution).digest != member.execution_digest:
                raise ValueError("批次执行计划摘要不匹配")
        sources = self.metadata.all("source")
        key = "batch-" + digest(str(path))[:20]
        if key in sources:
            if sources[key]["digest"] != batch.digest:
                raise ValueError("已登记批次发生变化，请使用新的批次目录")
            return {"id": key}
        if len(sources) >= 100:
            raise ValueError("最多登记 100 个批次")
        self.metadata.save(
            "source", key, {"path": str(path), "digest": batch.digest, "name": path.name}
        )
        return {"id": key}

    def _sources(self) -> dict[str, dict[str, Any]]:
        return self.metadata.all("source")

    def _local(self) -> dict[str, list[dict[str, Any]]]:
        root = self.state / "benchmarks"
        if not (root / "control.sqlite3").is_file():
            return {}
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in RunControlStore(root, read_only=True).ordered():
            if item["request"].get("kind") != "benchmark":
                continue
            row = project_run(item)
            config = row["config"]
            key = (
                "local-"
                + digest(
                    {
                        "candidate": config["candidate"],
                        "parameters": config["parameters"],
                        "benchmark": row["benchmark"],
                        "profile": config["suite"].get("profile"),
                    }
                )[:20]
            )
            groups.setdefault(key, []).append(row)
        return groups

    def _load(self, key: str) -> tuple[Path, str, list[dict[str, Any]]]:
        if key.startswith("local-"):
            groups = self._local()
            if key not in groups:
                raise KeyError(key)
            rows = groups[key]
            return self.state, rows[0]["candidate_id"], rows
        source = self._sources().get(key)
        if source is None:
            raise KeyError(key)
        root = Path(source["path"])
        batch = _batch(root / "batch.json")
        if batch.digest != source["digest"]:
            raise ValueError("已登记批次发生变化")
        _real_path(root / "state/benchmarks/control.sqlite3")
        _real_path(root / "state/benchmarks/records/records.sqlite3")
        state = root / "state"
        control = state / "benchmarks" / "control.sqlite3"
        items = (
            RunControlStore(control.parent, read_only=True).ordered() if control.exists() else []
        )
        runs = {r["operation_id"]: r for r in items}
        rows = []
        for member in batch.members:
            item = runs.get(member.operation_id)
            if item is not None:
                if item["request"]["execution"]["digest"] != member.execution_digest:
                    raise ValueError("执行状态与登记计划不一致")
                rows.append(project_run(item))
            else:
                file = (root / member.execution).resolve()
                if not file.is_relative_to(root):
                    raise ValueError("批次计划路径越界")
                execution = read_execution(file)
                if execution.digest != member.execution_digest:
                    raise ValueError("批次执行计划已改变")
                rows.append(
                    project_run(
                        {
                            "request": {"execution": execution.model_dump(mode="json")},
                            "operation_id": member.operation_id,
                            "run_id": None,
                            "attempt_id": None,
                            "state": "not_submitted",
                            "created_at": "",
                            "updated_at": "",
                        }
                    )
                )
        return state, source["name"], rows

    def _describe(self, key: str, name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        annotation = self.metadata.all("note").get(key, {})
        return {
            "id": key,
            "name": annotation.get("name") or name,
            "annotation": annotation,
            "models": sorted({r["model"] for r in rows}),
            "benchmarks": sorted({r["benchmark"] for r in rows}),
            **summarize_runs(rows),
        }

    def overview(self) -> dict[str, Any]:
        batches, errors = [], []
        for key, rows in self._local().items():
            batches.append(self._describe(key, rows[0]["candidate_id"], rows))
        for key in self._sources():
            try:
                _, name, rows = self._load(key)
                batches.append(self._describe(key, name, rows))
            except (OSError, ValueError, KeyError) as error:
                errors.append({"id": key, "message": str(error)})
        batches.sort(key=lambda b: b["created_at"], reverse=True)
        return {
            "batches": batches,
            "errors": errors,
            "settings": self.metadata.all("settings").get("workspace", {}),
        }

    def detail(self, key: str) -> dict[str, Any]:
        _, name, rows = self._load(key)
        notes = self.metadata.all("note")
        return {
            **self._describe(key, name, rows),
            "runs": [
                {**row, "annotation": notes.get(key + ":" + row["unit_id"], {})} for row in rows
            ],
        }

    def _run(self, key: str, run_id: str) -> tuple[Path, dict[str, Any]]:
        state, _, rows = self._load(key)
        if not any(r["run_id"] == run_id for r in rows):
            raise KeyError(run_id)
        return state, RunControlStore(state / "benchmarks", read_only=True).get(run_id)

    def evidence(self, key: str, run_id: str) -> BenchmarkEvidence:
        state, run = self._run(key, run_id)
        records = state / "benchmarks/records"
        return BenchmarkEvidence(
            LocalRecordsStore(records, read_only=True)
            if (records / "records.sqlite3").is_file()
            else None,
            run,
        )

    def logs(self, key: str, run_id: str) -> dict[str, Any]:
        state, run = self._run(key, run_id)
        root = state / "benchmarks/records"
        if not (root / "records.sqlite3").is_file():
            return {"text": "", "capture_status": "unavailable", "total_bytes": 0}
        records = LocalRecordsStore(root, read_only=True)
        try:
            tail = records.read_stream_tail(run["attempt_id"], run["attempt_id"] + ":combined")
        except KeyError:
            return {"text": "", "capture_status": "unavailable", "total_bytes": 0}
        if tail.visibility == Visibility.EVALUATOR or tail.data_class in {
            DataClass.PRIVATE_EVALUATION,
            DataClass.CREDENTIAL,
            DataClass.SECRET,
        }:
            raise KeyError("stream is not available to the console")
        return {
            "text": tail.data.decode("utf-8", errors="replace"),
            "offset": tail.offset,
            "total_bytes": tail.total_bytes,
            "capture_status": tail.capture_status.value,
        }

    def annotate(self, key: str, body: dict[str, Any], unit: str | None = None) -> dict[str, Any]:
        _, _, rows = self._load(key)
        if unit is not None and not any(r["unit_id"] == unit for r in rows):
            raise KeyError(unit)
        if set(body) - {"name", "notes", "project", "tags", "revision"}:
            raise ValueError("unknown annotation field")
        for field, limit in (("name", 120), ("notes", 12000), ("project", 200), ("tags", 500)):
            if not isinstance(body.get(field, ""), str) or len(body.get(field, "")) > limit:
                raise ValueError(f"invalid {field}")
        return self.metadata.save("note", key + ":" + unit if unit else key, body)

    def route(
        self, method: str, parts: list[str], query: dict[str, list[str]], body: dict[str, Any]
    ) -> dict[str, Any]:
        def q(key: str, default: str = "") -> str:
            return query.get(key, [default])[0]

        if not parts:
            return self.overview() if method == "GET" else self.register(body)
        if parts == ["settings"] and method == "POST":
            baseline = str(body.get("baseline", ""))
            if baseline:
                self._load(baseline)
            return self.metadata.save(
                "settings", "workspace", {"baseline": baseline, "revision": body.get("revision", 0)}
            )
        if parts == ["compare"] and method == "GET":
            _, _, left = self._load(q("left"))
            _, _, right = self._load(q("right"))
            return compare_runs(left, right, q("metric"))
        key = parts[0]
        if len(parts) == 1 and method == "GET":
            return self.detail(key)
        if parts[1:] == ["note"] and method == "POST":
            return self.annotate(key, body, q("unit") or None)
        if len(parts) == 4 and parts[1] == "runs":
            run_id, action = parts[2:]
            if action == "cancel" and method == "POST":
                state, run = self._run(key, run_id)
                store = RunControlStore(state / "benchmarks")
                with store.exclusive():
                    run = store.get(run_id)
                    if run["state"] != "finished":
                        run = store.update(run_id, cancel_requested=True)
                return {"cancel_requested": run["cancel_requested"], "state": run["state"]}
            if method == "GET":
                if action == "detail":
                    _, run = self._run(key, run_id)
                    row = project_run(run)
                    row["annotation"] = self.metadata.all("note").get(
                        key + ":" + row["unit_id"], {}
                    )
                    return row
                if action == "logs":
                    return self.logs(key, run_id)
                evidence = self.evidence(key, run_id)
                if action == "files":
                    return evidence.file(q("member")) if q("member") else evidence.inventory()
                if action == "trajectory":
                    return evidence.trajectory(
                        cursor=int(q("cursor", "0")),
                        limit=int(q("limit", "50")),
                        search=q("search"),
                        kind=q("kind", "all"),
                    )
        raise KeyError("/".join(parts))
