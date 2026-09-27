import type { BenchmarkRun, Comparison, Step } from "./types";
export const workspace = "benchmarks/workspace";
export const number = (value: number | null | undefined) =>
  value == null
    ? "—"
    : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
export const duration = (seconds: number | null | undefined) =>
  seconds == null
    ? "—"
    : seconds < 60
      ? `${Math.round(seconds)} 秒`
      : `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`;
export const stateLabels: Record<string, string> = {
  queued: "排队",
  accepted: "已准入",
  running: "运行中",
  collecting: "归档中",
  quarantined: "需要核对",
  finished: "已结束",
  not_submitted: "未提交",
};
export function outcome(run: BenchmarkRun) {
  if (run.cancel_requested && run.state !== "finished")
    return "已请求取消，等待 worker";
  if (run.state !== "finished") return stateLabels[run.state] ?? run.state;
  if (run.score_valid) return "已评分";
  if (run.execution === "cancelled") return "已取消";
  if (run.execution === "timed_out") return "执行超时";
  if (run.execution === "failed") return "执行失败";
  if (run.protocol === "invalid") return "协议无效";
  return "未获得有效评分";
}
export function link(
  values: Record<string, string | number | null | undefined>,
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    if (value != null && value !== "") query.set(key, String(value));
  return `#benchmarks/workspace?${query}`;
}
export function download(
  name: string,
  content: string,
  mime = "text/plain;charset=utf-8",
) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function csv(rows: unknown[][]) {
  return (
    "\ufeff" +
    rows
      .map((row) =>
        row
          .map((value) => {
            let text = value == null ? "" : String(value);
            if (/^[=+@\-\t\r]/.test(text) && typeof value !== "number")
              text = `'${text}`;
            return `"${text.replaceAll('"', '""')}"`;
          })
          .join(","),
      )
      .join("\r\n")
  );
}
export function comparisonCsv(data: Comparison) {
  return csv([
    [
      "task",
      "baseline",
      "candidate",
      "delta",
      "reason",
      "baseline_run",
      "candidate_run",
    ],
    ...data.rows.map((r) => [
      r.unit_id,
      r.left?.score_valid ? r.left.metrics[data.metric] : null,
      r.right?.score_valid ? r.right.metrics[data.metric] : null,
      r.delta,
      r.reason,
      r.left?.run_id,
      r.right?.run_id,
    ]),
  ]);
}
export function isError(step: Step) {
  return (
    step.metadata.is_error === true ||
    (step.metadata.exit_code != null &&
      ![0, "0"].includes(step.metadata.exit_code as number | string))
  );
}
export function groupSteps(steps: Step[]) {
  const result: { step: Step; response?: Step }[] = [];
  const calls = new Map<string, number>();
  for (const step of steps) {
    const id = step.metadata.tool_call_id ?? step.metadata.call_id;
    const key = id == null ? null : String(id);
    if (key && /result|response/.test(step.step_type) && calls.has(key)) {
      const index = calls.get(key) as number;
      if (!result[index].response) {
        result[index].response = step;
        continue;
      }
    }
    if (key && /call|request/.test(step.step_type))
      calls.set(key, result.length);
    result.push({ step });
  }
  return result;
}
export function configDiff(
  left: unknown,
  right: unknown,
  prefix = "",
): { field: string; left: string; right: string }[] {
  if (JSON.stringify(left) === JSON.stringify(right)) return [];
  if (
    left &&
    right &&
    typeof left === "object" &&
    typeof right === "object" &&
    !Array.isArray(left) &&
    !Array.isArray(right)
  ) {
    const a = left as Record<string, unknown>,
      b = right as Record<string, unknown>;
    return [...new Set([...Object.keys(a), ...Object.keys(b)])].flatMap((k) =>
      configDiff(a[k], b[k], prefix ? `${prefix}.${k}` : k),
    );
  }
  return [
    {
      field: prefix,
      left: JSON.stringify(left) ?? "—",
      right: JSON.stringify(right) ?? "—",
    },
  ];
}
