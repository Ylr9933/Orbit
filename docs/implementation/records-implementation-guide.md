# Records 实现解读

> 对应分支：`feat/records-foundation`。本文说明当前代码实际行为；目标设计见 [Records 模块详细设计](../architecture/records-design.md)。

## 1. 代码入口

| 文件 | 当前职责 |
| --- | --- |
| `src/agent_infra/records/api.py` | 后端无关 DTO、枚举和 Writer/Reader/Sink 协议 |
| `src/agent_infra/records/local.py` | SQLite schema、CAS、事件、stream、Artifact 和查询 |
| `src/agent_infra/records/trajectory.py` | Attempt 轨迹派生和 JSONL 数据集导出 |
| `src/agent_infra/runs/service.py` | 创建记录上下文并把执行事实写入 Records |
| `src/agent_infra/bootstrap/cli.py` | 组装本地查询、轨迹和导出命令 |

## 2. 一次 Run 的写入链路

```text
LocalRunService.run
  ├─ begin_run / begin_attempt
  ├─ run.created / attempt.started
  ├─ task.snapshot
  ├─ lease.granted 或 lease.declined
  ├─ policy.snapshot + Agent 可见 Task Artifact
  ├─ phase.started
  │    ├─ environment.ready
  │    ├─ job.submitted / process.started
  │    ├─ stdout/stderr 分块写入 spool
  │    ├─ process.exited 或 job.failed
  │    ├─ finalize stream，写入 CAS
  │    ├─ Agent 原生事件规范化
  │    ├─ environment.cleanup_finished
  │    └─ submission Artifact + phase.finished
  ├─ evaluation.started / evaluation.finished / reward.assigned（可选）
  ├─ credential.cleanup_finished（使用凭据时）
  ├─ lease.released
  └─ finish_attempt / finish_run
```

Run 拥有生命周期和 ID 关联；Records 只持久化，不判断业务状态是否合法。Environment 仍负责真实进程和容器，Agent adapter 仍负责解释提供方事件。

## 3. SQLite 与 CAS

SQLite 当前包含：

- `schema_info`；
- `runs`、`attempts`；
- `producer_sequences`、`events`；
- `blobs`、`streams`、`artifacts`。

数据库启用 WAL、foreign key、busy timeout 和 `synchronous=FULL`。每个公共 mutation 使用独立事务，进程内写入由 `RLock` 保护。多个 producer 不共享序列计数器。

blob 写入流程是：计算 SHA-256、在目标目录创建临时文件、flush/fsync、原子替换、提交 SQLite 元数据。stream 在 `spool/` 中按 offset 追加，finalize 后转入 CAS。Artifact 目录中的每个文件分别进入 CAS，再生成目录 manifest。

## 4. Agent 轨迹

Solver stdout 同时作为 job stream 和 Agent 原生 stream。若 adapter 实现 `decode_events`，Run 会把 `AgentEventKind` 映射为：

| AgentEventKind | 规范事件 |
| --- | --- |
| `SESSION` | `agent.session_started` |
| `MESSAGE` | `agent.message` |
| `TOOL_CALL` | `tool.requested` |
| `TOOL_RESULT` | `tool.completed` |
| `USAGE` | `model.usage` |
| `COMPLETED` | `agent.turn_completed` |
| `ERROR` | `agent.error` |
| `UNKNOWN` | `agent.native_event` |

规范事件把 `AgentEvent.canonical` 放入载荷顶层，并附加 `source.native_sequence`、
`source.part_index`、`native_type` 和完整 `native`。工具请求与结果通过 `tool_call_id` 进入同一
correlation 和 Span；载荷 schema 使用对应的 `agent.*.v1`，normalizer 版本为 `2.0.0`。

事件通过 `raw_refs` 指回原始 stream blob。即使 Agent 失败，已捕获的 stdout/stderr 也会 finalize，
并尝试规范化。规范化失败产生 `capture.gap`，不删除原始记录。

## 5. 评测隔离

Solver、可选的 submission execution 和 scorer 使用不同 Phase。scorer stream、结果 Artifact 标记为 evaluator 可见和 `private_evaluation`。Trajectory builder 会过滤这些事件，因此隐藏答案不会成为 Agent observation。

Evaluator 返回的允许公开 feedback 记录在 `evaluation.finished`。只有 feedback 明确包含有限数值 `reward`/`score` 或布尔 `passed` 时，Run 才生成 `reward.assigned`；完整私有 evaluator payload 只保存在 scorer Artifact 中。

## 6. 轨迹派生

`AttemptTrajectoryBuilder` 读取已完成 Attempt 的事件图，而不修改原始数据。当前 schema 为
`records.trajectory.v2`，builder 为 `attempt-event-graph@2.0.0`。trajectory ID 由 Attempt、builder
版本和源 event ID 计算，因此同一输入和 builder 版本具有稳定 ID。

每个 step 保存 observation event、action event、后继 observation、reward、Span lineage、终止原因
和 PolicySnapshot ID。tool action 会按 `tool_call_id`（缺失时退回 Span）查找对应结果，即使并行
调用使结果出现在后一个 action 之后，也会进入正确 action 的 next observation。资格特征中的
`tool_call_correlation` 为 `complete`、`partial` 或 `unavailable`；partial 同时产生明确 limitation。

当前 CLI Agent 通常没有 token ID 和 behavior logprob，因此导出会明确标记 unavailable。训练使用者
必须按 `eligible_for`、`limitations` 和 features 筛选。

## 7. 当前限制和扩展点

- 本地 sink 可多线程写入，但没有跨进程 producer spool 协议。
- `durable_local` 只表示本机落盘，不表示远端备份。
- CLI 是本地管理员工具；HTTP/Web 接入前需要 AccessContext 和授权过滤。
- 当前 observation/action 切分是事件级规则，不是 token 级 credit assignment。
- Host Agent 和外部 Agent 只能在相应执行/gateway 能力实现后接入同一个 scoped sink。
- Resource 高频采样尚未接入；当前记录请求、分配和释放事实。

这些限制均通过现有公共协议扩展，不需要让业务模块直接访问 SQLite 或 CAS 路径。
