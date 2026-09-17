# Records API 与命令参考

> 实现状态：`records.event.v1` 与本地 SQLite/CAS 后端已实现。Web 首版增加 Run 列表查询；分支交付和合并状态见项目进度及任务记录。

## 1. 已实现范围

Records 当前提供：

- Run 和 Attempt manifest、终态与结果；
- 带 producer 顺序和幂等键的规范事件；
- Run、Attempt、Phase、Session、Span 和相关 ID；
- stdout/stderr 等可追加 stream；
- 文件或目录 Artifact 及内容寻址 blob；
- Run/Attempt 查询、事件分页、Span 图和 Artifact 查询；
- Agent 原生 stdout 引用、完整 native payload 及字段级 `AgentEvent` 规范化；
- Attempt 级 trajectory 派生、训练资格说明和固定 JSONL 导出；
- Run 对 task、lease、environment job、提交、评测、reward、清理和释放的记录。

尚未实现远端对象存储、多节点 spool 上传、多用户权限服务、托管宿主机 Agent 和 Parquet/训练框架专用导出。
本机单管理员 HTTP 查询见 [Web 控制台](../operations/web-console.md)。

## 2. 本地存储

`LocalRunService` 默认在其 `state_dir/_records/` 下创建：

```text
_records/
├── records.sqlite3
├── blobs/sha256/
├── spool/
└── exports/
```

SQLite 保存元数据和索引，blob 目录保存原生 stream、Artifact 文件和 Artifact manifest。调用方应通过 Records API 读取，不能依赖内部表或目录布局。

## 3. Python 入口

主要类型位于 `agent_infra.records`：

```python
from datetime import UTC, datetime
from pathlib import Path

from agent_infra.records import (
    AttemptManifest,
    EventDraft,
    EventQuery,
    ProducerKind,
    RecordContext,
    RunManifest,
)
from agent_infra.records.local import LocalRecordsStore

store = LocalRecordsStore(Path("var/records"))
store.begin_run(RunManifest("run-1", datetime.now(UTC), {"kind": "research"}))
store.begin_attempt(AttemptManifest("attempt-1", "run-1", datetime.now(UTC)))

sink = store.scoped_sink(
    RecordContext("run-1", "attempt-1", "controller-1", ProducerKind.RUN)
)
sink.append_events((EventDraft("attempt.started", {"status": "running"}),))

events = store.read_events(EventQuery(attempt_id="attempt-1"))
```

公共边界分为：

- `RecordsWriter`：开始和结束 Run/Attempt，创建 scoped sink；
- `RecordSink`：写事件、stream、blob 和 Artifact；
- `RecordsReader`：读取 Run/Attempt、事件、Trace 和 Artifact；
- `AttemptTrajectoryBuilder`：从 Attempt 事实生成版本化轨迹；
- `export_jsonl`：写入固定轨迹文件及 digest manifest。

### 3.1 写入语义

- 事件在同一 `producer_id` 下具有单调 `producer_sequence`。
- 显式 `idempotency_key` 的相同重试返回原事件；同一键对应不同内容时拒绝写入。
- `WriteReceipt.durability` 当前返回 `durable_local`。
- stream 必须按连续 offset 追加；完全相同的已写区间可以安全重试。
- `finalize_stream` 后 stream 不再接受写入。
- Artifact 中的文件按 SHA-256 去重，目录由带版本的 manifest 描述。

### 3.2 查询语义

`RecordsReader.list_runs(limit=100, offset=0)` 返回 RunRecord 元组，按创建时间倒序、run_id 排序。
limit 必须为 1–200，offset 非负；不创建新 Run。offset 分页不是冻结快照，新增运行期间跨页可能重复或移动。

`EventQuery` 支持 Run、Attempt、事件类型、producer 类型和数量限制。`next_cursor` 是不透明的本地游标；调用者不应解析或修改。

`read_trace(attempt_id)` 返回完整事件序列及按 `span_id` 聚合的 Span。跨 Span 的异步关系保存在 `EventLink` 中。

## 4. CLI

CLI 的 `--root` 指向 Records 根目录，例如 `var/runs/_records`。直接读取本地 Records 的用户等同本机管理员；当前 CLI 没有实现多租户权限校验。

```bash
agent-infra records run <run-id> --root var/runs/_records
agent-infra records attempt <attempt-id> --root var/runs/_records
agent-infra records events <attempt-id> --root var/runs/_records --limit 500
agent-infra records artifacts <attempt-id> --root var/runs/_records
agent-infra records trajectory <attempt-id> --root var/runs/_records
agent-infra records export <attempt-id> [<attempt-id> ...] \
  --root var/runs/_records \
  --destination exports/example
```

## 5. 轨迹语义

当前 `attempt-event-graph@2.0.0` 产生 `records.trajectory.v2`：

- 以 Attempt 为 rollout 边界；
- 把 `agent.message` 和 `tool.requested` 视为候选 action；
- 使用规范化 tool call ID、名称、参数、结果和状态，并按 call ID/Span 关联请求与结果；
- 同一原生消息中的多个工具调用作为独立 action；
- 只把 Agent 当时可见范围内的公开事件作为 observation；
- 排除 `private_evaluation`、credential、secret 和 evaluator-only 事件；
- 将 `reward.assigned` 关联到 Attempt、action event 或 action Span；
- 保留所有源 event ID 和 Span ID；
- 显式标注 token ID、behavior logprob、reward 和采集完整性。
- 用 `tool_call_correlation=complete/partial/unavailable` 标注工具轨迹关联完整性。

Agent 规范事件载荷使用 `agent.session.v1`、`agent.message.v1`、
`agent.tool_requested.v1`、`agent.tool_completed.v1`、`agent.model_usage.v1`、
`agent.turn_completed.v1`、`agent.error.v1` 或 `agent.native_event.v1`。公共字段位于 payload 顶层，
来源行和拆分序号位于 `source`，完整原生对象位于 `native`，原始 stream 由 `raw_refs` 引用。

该视图是可重建的分析/训练候选数据，不声称 CLI Agent 天然满足所有 RL 算法要求。

## 6. 数据边界

- 命令事件只保存环境变量名称，不保存值。
- 临时 Agent credential home 不进入 Artifact，并在环境清理后删除；只记录清理结果。
- scorer 输出与结果 Artifact 标记为 `evaluator/private_evaluation`。
- 公共 feedback 和由其明确导出的 reward 可以进入普通轨迹；私有答案不会进入 observation。
- `open_blob` 是控制面内部能力。面向远端用户开放前，需要在 gateway 中增加基于 Artifact/stream 元数据的访问检查。
