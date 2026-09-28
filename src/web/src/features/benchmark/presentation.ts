import type { Batch, BenchmarkRun } from "./types";

export type ViewParams = Record<string, string>;
export const domains: Record<string, string> = {
  astronomy: "天文学",
  biology: "生物学",
  biostat: "生物统计",
  chemistry: "化学",
  computer_science: "计算机科学",
  earth_science: "地球科学",
  electrical_engineering: "电气工程",
  materials: "材料科学",
  math: "数学",
  physics: "物理学",
  robotics: "机器人学",
};
export function taskLabel(unit: string) {
  const [prefix, ...rest] = unit.split(".");
  return domains[prefix] && rest.length
    ? rest
        .join(".")
        .replace(/__seed\d+$/, "")
        .replaceAll("_", " ")
    : unit;
}
export function taskDomain(unit: string) {
  return domains[unit.split(".")[0]] ?? "";
}
export const metricLabel = (metric: string) =>
  metric === "local_public_score" ? "本地公开评分" : metric || "得分";
export function score(run: BenchmarkRun, metric: string): number | null {
  const value = run.metrics[metric];
  return run.score_valid && Number.isFinite(value) ? value : null;
}
export function median(values: number[]) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b),
    middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}
export function resultStats(runs: BenchmarkRun[], metric: string) {
  const values = runs.flatMap((r) => {
    const v = score(r, metric);
    return v == null ? [] : [v];
  });
  const elapsed = runs.flatMap((r) =>
    r.elapsed_seconds != null && Number.isFinite(r.elapsed_seconds)
      ? [r.elapsed_seconds]
      : [],
  );
  return {
    count: values.length,
    mean: values.length
      ? values.reduce((a, b) => a + b, 0) / values.length
      : null,
    median: median(values),
    zero: values.filter((v) => v === 0).length,
    duration: median(elapsed),
  };
}
export function resultRows(
  runs: BenchmarkRun[],
  metric: string,
  params: ViewParams,
) {
  const query = (params.search ?? "").toLowerCase();
  const filter = params.filter ?? "all";
  return runs
    .filter((r) => {
      const value = score(r, metric);
      return (
        `${r.unit_id} ${taskLabel(r.unit_id)} ${taskDomain(r.unit_id)} ${r.model} ${r.annotation.notes ?? ""}`
          .toLowerCase()
          .includes(query) &&
        (!params.domain || taskDomain(r.unit_id) === params.domain) &&
        (filter === "all" ||
          (filter === "zero"
            ? value === 0
            : filter === "unscored"
              ? value == null
              : filter === "failed"
                ? ["failed", "timed_out"].includes(r.execution ?? "")
                : filter === "cancelled"
                  ? r.execution === "cancelled"
                  : filter === "cleanup"
                    ? r.cleanup_complete === false
                    : r.state === filter))
      );
    })
    .sort((a, b) => {
      if (params.sort === "duration")
        return (b.elapsed_seconds ?? -1) - (a.elapsed_seconds ?? -1);
      if (params.sort === "task") return a.unit_id.localeCompare(b.unit_id);
      const av = score(a, metric),
        bv = score(b, metric);
      if (av == null)
        return bv == null ? a.unit_id.localeCompare(b.unit_id) : 1;
      if (bv == null) return -1;
      return (
        (av - bv) * (params.sort === "high" ? -1 : 1) ||
        a.unit_id.localeCompare(b.unit_id)
      );
    });
}
export function pageNumber(
  value: string | undefined,
  total: number,
  size: number,
) {
  const parsed = Number(value ?? 0);
  return Math.min(
    Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0,
    Math.max(0, Math.ceil(total / size) - 1),
  );
}
export function batchState(batch: Batch) {
  if (batch.states.quarantined) return "需要核对";
  if (batch.finished === batch.total)
    return batch.failed ? "已结束 · 有失败" : "已完成";
  if (batch.states.running || batch.states.collecting) return "运行中";
  if (batch.states.queued || batch.states.accepted) return "等待执行";
  return "待提交";
}
export function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
export function configFields(run: BenchmarkRun): [string, string][] {
  const params = object(run.config.parameters),
    candidate = object(run.config.candidate),
    resources = object(run.config.resources);
  const text = (v: unknown) => (v == null ? "未记录" : String(v));
  return [
    ["Benchmark", run.benchmark],
    ["模型", run.model],
    ["Agent", run.agent],
    ["Agent 版本", text(candidate.agent_version)],
    ["Codex 版本", text(params.codex_version)],
    ["任务条件", text(params.prompt_level)],
    ["思考强度", text(params.effort)],
    [
      "CPU",
      resources.cpu_cores == null ? "未记录" : `${resources.cpu_cores} 核`,
    ],
    [
      "内存",
      typeof resources.memory_bytes === "number"
        ? `${resources.memory_bytes / 1024 ** 3} GiB`
        : "未记录",
    ],
    ["GPU", text(resources.gpu_count)],
  ];
}
export function taskTimeout(run: BenchmarkRun) {
  const value = object(run.config.parameters).timeout_seconds;
  const seconds = Number(value);
  return value != null && Number.isFinite(seconds) && seconds > 0
    ? seconds
    : null;
}

export function batchTitle(batch: Batch, runs: BenchmarkRun[] = []) {
  if (batch.annotation.name) return batch.name;
  const levels = [
    ...new Set(
      runs
        .map((r) => object(r.config.parameters).prompt_level)
        .filter((v) => typeof v === "string"),
    ),
  ];
  return levels.length === 1 &&
    runs.every((r) => object(r.config.parameters).prompt_level === levels[0])
    ? `${batch.benchmarks.join(" · ")} · ${levels[0]}`
    : batch.name;
}
export function batchConditions(runs: BenchmarkRun[]) {
  const fields = [
    ["effort", "思考强度"],
    ["codex_version", "Codex"],
  ];
  return fields
    .flatMap(([field, label]) => {
      const values = [
        ...new Set(
          runs
            .map((r) => object(r.config.parameters)[field])
            .filter((v) => typeof v === "string"),
        ),
      ];
      const complete = runs.every(
        (run) => typeof object(run.config.parameters)[field] === "string",
      );
      return values.length === 1
        ? [`${label} ${values[0]}${complete ? "" : "（部分任务未记录）"}`]
        : values.length > 1
          ? [`${label} 多种配置`]
          : [];
    })
    .join(" · ");
}
