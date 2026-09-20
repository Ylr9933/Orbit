import { useState } from "react";
import { bytes, pretty, request } from "../api/console";
import { finishOperation, operationId } from "../api/operations";
import type {
  Capabilities,
  CompiledTask,
  Experiment,
  Preflight,
} from "../api/workflow";
import { Notice, Panel } from "../components/common";

export function ExperimentSubmit({
  token,
  projectId,
  revision,
  experiments,
  compiledTasks,
  capabilities,
}: {
  token: string;
  projectId: string;
  revision: number;
  experiments: Experiment[];
  compiledTasks: CompiledTask[];
  capabilities?: Capabilities;
}) {
  const [experiment, setExperiment] = useState(experiments[0]?.id ?? "");
  const [execution, setExecution] = useState("");
  const [compiled, setCompiled] = useState<CompiledTask>();
  const [taskKey, setTaskKey] = useState("");
  const [model, setModel] = useState("");
  const [timeout, setTimeoutValue] = useState(600);
  const [network, setNetwork] = useState(false);
  const [preflight, setPreflight] = useState<{
    key: string;
    value: Preflight;
  }>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const tasks = [...(compiled ? [compiled] : []), ...compiledTasks].filter(
    (item, index, all) =>
      item.experiment_id === experiment &&
      item.research_revision === revision &&
      all.findIndex(
        (t) =>
          t.task.revision === item.task.revision &&
          t.task.task_id === item.task.task_id,
      ) === index,
  );
  const selected =
    tasks.find((t) => `${t.task.task_id}:${t.task.revision}` === taskKey) ??
    tasks[0];
  const selectedExperiment = experiments.find((e) => e.id === experiment);
  const body = {
    task_id: selected?.task.task_id,
    task_revision: selected?.task.revision,
    model,
    provider: "codex",
    timeout_seconds: timeout,
    network,
  };
  const key = JSON.stringify(body);
  const ready = preflight?.key === key && preflight.value.ready;
  const base = `projects/${encodeURIComponent(projectId)}`;
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="提交已采用的实验">
      <p className="muted">
        只执行已确认的方案（版本 {revision}
        ）。编译与预检不运行模型；确认提交才会启动一次容器实验。
      </p>
      <label>
        选择实验
        <select
          value={experiment}
          onChange={(e) => {
            setExperiment(e.target.value);
            setPreflight(undefined);
          }}
        >
          {experiments.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title} · {e.id}
            </option>
          ))}
        </select>
      </label>
      <p>{selectedExperiment?.method}</p>
      <p>停止条件：{selectedExperiment?.stopping_condition}</p>
      <p>资源配置：{selectedExperiment?.resource_request ?? "待补充"}</p>
      <details open={!selected}>
        <summary>编译任务 / 更新材料快照</summary>
        <label>
          执行配置（项目内 YAML 路径）
          <input
            placeholder="configs/execution.yaml"
            value={execution}
            onChange={(e) => setExecution(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={busy || !execution || !experiment}
          onClick={() =>
            void action(async () => {
              setPreflight(undefined);
              const result = await request<{
                status: string;
                issues: unknown[];
                compiled: CompiledTask | null;
              }>(token, `${base}/compile`, {
                experiment_id: experiment,
                research_revision: revision,
                execution,
              });
              if (!result.compiled) {
                setError(`需要补充：${pretty(result.issues)}`);
                return;
              }
              setCompiled(result.compiled);
              setTaskKey(
                `${result.compiled.task.task_id}:${result.compiled.task.revision}`,
              );
            })
          }
        >
          编译材料快照
        </button>
      </details>
      {selected && (
        <label>
          已编译任务
          <select
            value={`${selected.task.task_id}:${selected.task.revision}`}
            onChange={(e) => setTaskKey(e.target.value)}
          >
            {tasks.map((item) => (
              <option
                key={`${item.task.task_id}:${item.task.revision}`}
                value={`${item.task.task_id}:${item.task.revision}`}
              >
                {item.experiment_id} · {item.task.revision.slice(0, 12)}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="form-grid">
        <label>
          Codex 模型
          <input
            required
            placeholder="明确填写模型名称"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        </label>
        <label>
          运行时限（秒）
          <input
            type="number"
            min={1}
            max={86400}
            value={timeout}
            onChange={(e) => setTimeoutValue(Number(e.target.value))}
          />
        </label>
      </div>
      <label className="inline">
        <input
          type="checkbox"
          checked={network}
          onChange={(e) => setNetwork(e.target.checked)}
        />
        允许本次实验联网（模型访问需要）
      </label>
      {!capabilities?.run_control && (
        <p role="status">
          {capabilities?.controller_reason ?? "正在检查 Controller…"}
        </p>
      )}
      {preflight?.key === key && (
        <div className="result-box">
          <strong>{preflight.value.ready ? "预检通过" : "预检未通过"}</strong>
          {preflight.value.resources && (
            <p>
              CPU {preflight.value.resources.cpu_cores} 核 · 内存{" "}
              {bytes(preflight.value.resources.memory_bytes)} · GPU{" "}
              {preflight.value.resources.gpu.count}
            </p>
          )}
          <p>本次最多运行 {timeout} 秒。模型费用由已配置账号承担。</p>
          {preflight.value.issues?.length > 0 && (
            <pre>{pretty(preflight.value.issues)}</pre>
          )}
        </div>
      )}
      <Notice error={error} />
      <div className="actions">
        <button
          type="button"
          disabled={
            busy || !selected || !model.trim() || !capabilities?.run_control
          }
          onClick={() =>
            void action(async () => {
              setPreflight({
                key,
                value: await request<Preflight>(
                  token,
                  `${base}/preflight`,
                  body,
                ),
              });
            })
          }
        >
          检查环境与资源
        </button>
        <button
          type="button"
          className="primary"
          disabled={busy || !ready || !capabilities?.run_control}
          onClick={() =>
            void action(async () => {
              const scope = `submit:${projectId}`;
              const run = await request<{ run_id: string }>(
                token,
                `${base}/submit`,
                { ...body, operation_id: operationId(scope, body) },
              );
              finishOperation(scope);
              location.hash = `execution/${run.run_id}`;
            })
          }
        >
          {busy ? "处理中…" : "确认提交一次实验"}
        </button>
      </div>
    </Panel>
  );
}
