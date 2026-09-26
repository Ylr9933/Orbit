import { useState } from "react";
import { useData } from "../api/console";
import { Empty, Notice, Panel } from "../components/common";

interface NativeStep {
  step_index: number;
  timestamp_ms: number | null;
  step_type: string;
  content: string;
  metadata: Record<string, string | number | boolean>;
}
interface BenchmarkTrajectory {
  run_id: string;
  attempt_id: string;
  instance_id: string;
  prompt_level: string | null;
  session_id: string | null;
  capture_status: string;
  calls: {
    completed_turns?: number;
    last_reported_usage?: Record<string, number> | null;
    capture_status?: string;
  };
  trajectory: { capture_status: string; total_steps?: number; origin?: string };
  docker: {
    container_id?: string | null;
    image_id?: string | null;
    cpu_limit?: number | null;
    memory_limit_bytes?: number | null;
    usage_samples?: number;
    usage_status?: string;
    last_sample?: Record<string, string> | null;
    identity_status?: string;
  };
  steps: NativeStep[];
  next_cursor: number | null;
}

export function BenchmarkTrajectoryPanel({
  token,
  runId,
  onClose,
}: {
  token: string;
  runId: string;
  onClose: () => void;
}) {
  const [cursor, setCursor] = useState(0);
  const { data: trajectory, error: trajectoryError } =
    useData<BenchmarkTrajectory>(
      token,
      `benchmarks/runs/${encodeURIComponent(runId)}?cursor=${cursor}`,
      5000,
    );
  return (
    <Panel title="ASI-Bench 原生 Agent 轨迹">
      <button type="button" onClick={onClose}>
        关闭
      </button>
      <Notice error={trajectoryError} loading={!trajectory} />
      {trajectory && (
        <>
          <p className="muted">
            Run {trajectory.run_id} · Attempt {trajectory.attempt_id} ·{" "}
            {trajectory.instance_id} / {trajectory.prompt_level ?? "—"} · Codex
            session {trajectory.session_id ?? "未捕获"}
          </p>
          <p className="muted">
            证据 {trajectory.capture_status} · 可见轨迹{" "}
            {trajectory.trajectory.capture_status} (
            {trajectory.trajectory.total_steps ?? 0} 步，
            {trajectory.trajectory.origin ?? "原生"})
          </p>
          <p className="muted">
            Codex 完成轮次 {trajectory.calls.completed_turns ?? "未记录"} ·
            调用用量{" "}
            {trajectory.calls.last_reported_usage
              ? JSON.stringify(trajectory.calls.last_reported_usage)
              : "未记录"}
          </p>
          <p className="muted">
            Docker {trajectory.docker.container_id ?? "ID 未捕获"} · 镜像{" "}
            {trajectory.docker.image_id ?? "未记录"} · 限额{" "}
            {trajectory.docker.cpu_limit != null
              ? `${trajectory.docker.cpu_limit / 1e9} CPU`
              : "CPU 未证明"}{" "}
            /
            {trajectory.docker.memory_limit_bytes != null
              ? `${(trajectory.docker.memory_limit_bytes / 1024 ** 3).toFixed(1)} GiB`
              : "内存未证明"}{" "}
            · 资源样本 {trajectory.docker.usage_samples ?? 0}
          </p>
          {trajectory.docker.last_sample && (
            <p className="muted">
              最近采样：CPU {trajectory.docker.last_sample.CPUPerc ?? "—"} ·
              内存 {trajectory.docker.last_sample.MemUsage ?? "—"} · 网络{" "}
              {trajectory.docker.last_sample.NetIO ?? "—"} · 磁盘{" "}
              {trajectory.docker.last_sample.BlockIO ?? "—"}
            </p>
          )}
          {trajectory.steps.length === 0 ? (
            <Empty>暂无可展示的可见步骤；请检查轨迹覆盖状态和原始产物。</Empty>
          ) : (
            trajectory.steps.map((step) => (
              <div
                className="event"
                key={`${trajectory.attempt_id}:${step.step_index}`}
              >
                <strong>
                  #{step.step_index} · {step.step_type}
                </strong>
                <small>
                  {step.metadata.tool_name ??
                    step.metadata.parent_tool_name ??
                    ""}
                </small>
                <pre>{step.content}</pre>
              </div>
            ))
          )}
          {trajectory.next_cursor != null && (
            <button
              type="button"
              onClick={() => setCursor(trajectory.next_cursor ?? 0)}
            >
              下一页
            </button>
          )}
          {cursor > 0 && (
            <button
              type="button"
              onClick={() => setCursor(Math.max(0, cursor - 50))}
            >
              上一页
            </button>
          )}
          <small>
            页面展示有界可见轨迹；原始 JSONL 和完整证据保存在 Records。
          </small>
        </>
      )}
    </Panel>
  );
}
