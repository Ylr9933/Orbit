import { useState } from "react";
import { useData } from "../api/console";
import { Badge, Empty, Notice, Panel } from "../components/common";

interface BenchmarkRun {
  run_id: string;
  state: string;
  benchmark: string;
  unit_id: string;
  candidate_id: string;
  execution: string | null;
  evaluation: string | null;
  protocol: string | null;
  cleanup_complete: boolean | null;
  resources: {
    requested: unknown;
    authorized: unknown;
    actual_allocation: unknown;
    usage: unknown;
  };
}
interface CampaignCandidate {
  candidate_id: string;
  parent_id: string | null;
  state: string;
  score: number | null;
  run_id: string | null;
  feedback: Record<string, number> | null;
}
interface Campaign {
  campaign_id: string;
  state: string;
  stop_reason: string | null;
  selected_candidate_id: string | null;
  candidates: CampaignCandidate[];
}
interface Compatibility {
  adapter_id: string;
  adapter_version: string;
  suite_digest: string;
  runner_digest: string;
  profile: string;
  backend: string;
  agent: string;
  agent_version: string;
  model: string;
  level: string;
  official_submission: string;
  evidence: string[];
  limitations: string[];
}
interface BenchmarkSnapshot {
  available: boolean;
  capacity: { max_concurrent: number } | null;
  active_leases: number;
  queued: number;
  runs: BenchmarkRun[];
  campaigns: Campaign[];
  compatibility: Compatibility[];
}

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

export function BenchmarksPage({ token }: { token: string }) {
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const { data, error, refresh, updated } = useData<BenchmarkSnapshot>(
    token,
    "benchmarks",
    5000,
  );
  const { data: trajectory, error: trajectoryError } =
    useData<BenchmarkTrajectory>(
      token,
      selectedRun
        ? `benchmarks/runs/${encodeURIComponent(selectedRun)}?cursor=${cursor}`
        : null,
      5000,
    );
  return (
    <>
      <div className="section-line">
        <p className="muted">
          本机管理员视图，每 5 秒读取持久状态。不会启动任务或读取私有评测文件。
        </p>
        <button type="button" onClick={refresh}>
          刷新
        </button>
      </div>
      <Notice error={error} loading={!data} />
      {data && !data.available && (
        <Empty>尚无 Benchmark 状态。先通过 CLI 规划和提交一次 trial。</Empty>
      )}
      {data?.available && (
        <>
          <div className="stats">
            <Panel title="队列等待">
              <strong className="metric">{data.queued}</strong>
            </Panel>
            <Panel title="活动租约">
              <strong className="metric">{data.active_leases}</strong>
            </Panel>
            <Panel title="授权并发">
              <strong className="metric">
                {data.capacity?.max_concurrent ?? "—"}
              </strong>
              <small>仅为调度准入，不等于容器硬限额</small>
            </Panel>
          </div>
          <Panel title="最近 Benchmark 运行">
            {data.runs.length === 0 ? (
              <Empty>暂无运行。</Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Run / Candidate</th>
                      <th>任务</th>
                      <th>执行 / 评测 / 协议</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.runs.map((run) => (
                      <tr key={run.run_id}>
                        <td>
                          <strong>{run.candidate_id}</strong>
                          <small>{run.run_id}</small>
                          {run.benchmark === "ASI-Bench" && (
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedRun(run.run_id);
                                setCursor(0);
                              }}
                            >
                              查看轨迹
                            </button>
                          )}
                        </td>
                        <td>
                          {run.benchmark}
                          <small>{run.unit_id}</small>
                        </td>
                        <td>
                          {run.execution ?? "—"} / {run.evaluation ?? "—"} /{" "}
                          {run.protocol ?? "—"}
                        </td>
                        <td>
                          <Badge>{run.state}</Badge>
                          <small>
                            清理：
                            {run.cleanup_complete === true ? "确认" : "待确认"}
                          </small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <small>
              仅显示最近 50 条；原始日志和完整 Records 请用管理员 CLI 查询。
            </small>
          </Panel>
          {selectedRun && (
            <Panel title="ASI-Bench 原生 Agent 轨迹">
              <button type="button" onClick={() => setSelectedRun(null)}>
                关闭
              </button>
              <Notice error={trajectoryError} loading={!trajectory} />
              {trajectory && (
                <>
                  <p className="muted">
                    Run {trajectory.run_id} · Attempt {trajectory.attempt_id} ·{" "}
                    {trajectory.instance_id} / {trajectory.prompt_level ?? "—"}{" "}
                    · Codex session {trajectory.session_id ?? "未捕获"}
                  </p>
                  <p className="muted">
                    证据 {trajectory.capture_status} · 可见轨迹{" "}
                    {trajectory.trajectory.capture_status} (
                    {trajectory.trajectory.total_steps ?? 0} 步，
                    {trajectory.trajectory.origin ?? "原生"})
                  </p>
                  <p className="muted">
                    Codex 完成轮次{" "}
                    {trajectory.calls.completed_turns ?? "未记录"} · 调用用量{" "}
                    {trajectory.calls.last_reported_usage
                      ? JSON.stringify(trajectory.calls.last_reported_usage)
                      : "未记录"}
                  </p>
                  <p className="muted">
                    Docker {trajectory.docker.container_id ?? "ID 未捕获"} ·
                    镜像 {trajectory.docker.image_id ?? "未记录"} · 限额{" "}
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
                      最近采样：CPU{" "}
                      {trajectory.docker.last_sample.CPUPerc ?? "—"} · 内存{" "}
                      {trajectory.docker.last_sample.MemUsage ?? "—"} · 网络{" "}
                      {trajectory.docker.last_sample.NetIO ?? "—"} · 磁盘{" "}
                      {trajectory.docker.last_sample.BlockIO ?? "—"}
                    </p>
                  )}
                  {trajectory.steps.length === 0 ? (
                    <Empty>
                      暂无可展示的可见步骤；请检查轨迹覆盖状态和原始产物。
                    </Empty>
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
          )}
          <Panel title="Campaign 候选比较">
            {data.campaigns.length === 0 ? (
              <Empty>暂无 Campaign；候选创建与提交仍使用 benchmark CLI。</Empty>
            ) : (
              data.campaigns.map((campaign) => (
                <div className="event" key={campaign.campaign_id}>
                  <div className="section-line">
                    <strong>{campaign.campaign_id}</strong>
                    <Badge>{campaign.state}</Badge>
                  </div>
                  <p className="muted">
                    当前选择：{campaign.selected_candidate_id ?? "未选出"} ·
                    停止原因：
                    {campaign.stop_reason ?? "—"}
                  </p>
                  {campaign.candidates.map((candidate) => (
                    <div className="section-line" key={candidate.candidate_id}>
                      <span>
                        {candidate.candidate_id}
                        {candidate.parent_id
                          ? ` ← ${candidate.parent_id}`
                          : " (baseline)"}
                      </span>
                      <span>
                        {candidate.state} · 分数 {candidate.score ?? "—"}
                      </span>
                    </div>
                  ))}
                </div>
              ))
            )}
          </Panel>
          <Panel title="兼容性证据矩阵">
            {data.compatibility.length === 0 ? (
              <Empty>
                尚无已发布的兼容性声明；请通过 CLI 发布带证据的矩阵。
              </Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>适配器 / Profile</th>
                      <th>Agent / Backend</th>
                      <th>级别</th>
                      <th>提交</th>
                      <th>证据</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.compatibility.map((entry) => (
                      <tr
                        key={`${entry.adapter_id}:${entry.adapter_version}:${entry.suite_digest}:${entry.runner_digest}:${entry.profile}:${entry.agent}:${entry.agent_version}:${entry.model}:${entry.backend}`}
                      >
                        <td>
                          {entry.adapter_id} {entry.adapter_version}
                          <small>{entry.profile}</small>
                        </td>
                        <td>
                          {entry.agent}
                          <small>
                            {entry.model} · {entry.backend}
                          </small>
                        </td>
                        <td>{entry.level}</td>
                        <td>{entry.official_submission}</td>
                        <td>{entry.evidence.length} 条引用</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <small>刷新于 {updated || "—"}。兼容性声明不代表官方认证。</small>
        </>
      )}
    </>
  );
}
