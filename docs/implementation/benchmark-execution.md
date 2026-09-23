# BM01 / BM05 执行实现逻辑

状态：BM01 与 BM05-A 已集成，BM05-B 在任务分支实现；公共命令和边界见
[使用参考](../reference/benchmark-execution.md)。BM05-A 沿用原执行与事件格式，增加持久租约账本和
控制库中的 FIFO 等待语义，没有另建评分状态机。

## 调用链

```text
独立适配包：discover / plan / validate / invocation
  → benchmarks：FrozenPlan → PreparedExecution（冻结确定的 argv）
  → bootstrap：检查声明和实际后端，组装 store / records / backend
  → runs：保存 operation 意图并排队；队首向 resources 申请持久租约
  → runs：reconcile，再 submit / observe / cancel
  → environments：独立监督器启动命令，保存日志与清理收据
  → runs：停止后 collect，写入 Records，再释放持久租约
```

| 文件 | 职责 |
| --- | --- |
| [benchmarks/execution_api.py](../../src/agent_infra/benchmarks/execution_api.py) | 可选执行扩展 1.0：`NativeInvocation` 和纯翻译 `invocation(plan)`；旧规划包不用补空方法 |
| [benchmarks/execution.py](../../src/agent_infra/benchmarks/execution.py) | 重建计划、命令冻结及摘要、执行规格转换、首个后端可支持范围检查 |
| [environments/execution_api.py](../../src/agent_infra/environments/execution_api.py) | 公共 ExecutionSpec/Handle/Observation/Reconciliation/Backend；复用 ProcessCommand、Submission、CleanupResult |
| [environments/managed_process.py](../../src/agent_infra/environments/managed_process.py) | 幂等提交、身份对账、字节游标、取消标记、收据检查、冻结输出；不解释 benchmark |
| [environments/_process_supervisor.py](../../src/agent_infra/environments/_process_supervisor.py) | 独立进程寿命、墙钟预算、管道排空、有界日志、后台子进程清理；不依赖 CLI 存活 |
| [environments/_process_state.py](../../src/agent_infra/environments/_process_state.py) | Linux 锁、boot/PID/starttime 身份与 pidfd 定向信号；不广播清理其他进程 |
| [runs/benchmark_execution.py](../../src/agent_infra/runs/benchmark_execution.py) | 一个原子 Run 的持久意图、保守恢复、Records 衔接和完成门槛 |
| [runs/control_store.py](../../src/agent_infra/runs/control_store.py) | 复用既有 SQLite；增加本地跨进程事务范围锁，不改表结构 |
| [resources/persistent.py](../../src/agent_infra/resources/persistent.py) | 独立 SQLite 租约账本；幂等申请、容量判断、owner epoch、native ID、对账与释放历史 |
| [bootstrap/benchmark_execution.py](../../src/agent_infra/bootstrap/benchmark_execution.py) | 命令编排、实际后端和存储组装；CLI 只解析参数 |

`ExecutionBackend` 不依赖 Benchmark/Run/资源后端，公开的 handle 不包含 Popen、Docker client 或数据库连接。
BM01 ExecutionSpec 只覆盖当前受管命令能力，后续容器、外部分配引用和大文件交接要通过明确的扩展契约补齐。
默认 backend 只承诺自己的 `cleanup_scope=process_group`，Run 记录该范围，不将其泛化为整个宿主机清理成功。

## 四份持久状态各管什么

1. **控制 store**：用户 operation ID 对应一个 Run/Attempt，保存完整冻结请求、FIFO 状态和游标。
   跨 CLI 文件锁保护“查询操作 → 队首准入 → 调用后端 → 写结果”，避免同一 state-dir 两个提交者同时准入。
2. **资源 lease store**：request/Run 对应唯一租约，保存 claim、owner epoch、状态和 native ID。
   `allocated/active/reconciling` 都占容量；只有正向清理证据才能转为 `released`。等待队列不复制到这里。
3. **后端 journal/spool**：启动意图、原生身份、进程原始字节和清理收据。不等于另一套 Records，
   它是控制端离线期间的运行恢复依据；不会尝试解释对话或成绩。
4. **Records**：统一 Run/Attempt、事件、流和产物引用。只追加确认的字节；原生日志不做 UTF-8 改写。
   本地 raw stream 修复了创建 spool/提交数据库之间，以及 fsync 字节/提交游标之间的崩溃窗口：
   重试以已提交游标为准，丢弃未提交尾部后重新采集；缺失已提交字节则报错，不补零、不伪造完整记录。

`STATE/benchmarks` 与原科研 Controller 的状态分开，避免后者已有的“重启标记 interrupted 并清理”语义
影响原生任务续查。两者复用代码和 Records 协议；当前 Web/HTTP/MCP 没有自动聚合这套 benchmark 状态。

## 为什么不会因重试再跑一次

控制端先保存请求；后端在 fsync `launch.json` 后才能创建监督器。监督器先 fsync 自己的 owner 身份，再启动
真正命令。重试依次查这些证据：没有 launch 才可确认未提交；有 launch 但没有可靠 owner/result 就是未知。
因此宁可让极小的崩溃窗口需要人工处理，也不会把昂贵实验重复启动。

监督器启动新 session，命令和后台子进程留在该进程组。取消只写标记，由活着且身份明确的监督器发信号。
PID、starttime、session 和 boot ID 检查避免 PID 复用误杀；pidfd 在信号发送时绑定具体进程。
主进程退出也要清理组内后台进程；监督器退出且完整收据确认后才能冻结输出。
主动逃逸进程组的程序不属于这个 backend 的支持范围，不能把该实现当容器沙箱。

## 故障窗口与完成门槛

| 发生位置 | 恢复行为 |
| --- | --- |
| 等待项已写入，协调器退出 | 重启后仍按控制库顺序等待；`reconcile` 从最早未完成项推进 |
| 租约已提交，Run 尚未写回 | 同一 attempt 的幂等申请返回原租约；不会再次占容量 |
| 控制意图已写，但没有后端 launch | status 不启动；用户显式重试原 operation 才可启动，也可以取消 |
| 后端已启动，但提交响应丢失 | 保留 operation；重连查原 handle，不重放 |
| 监督器死亡/身份未知 | quarantined，继续占槽；没有证明时不能推断进程已清理 |
| Records 字节已写，控制游标没提交 | 按相同 offset 重发；既有字节必须一致，不重复追加 |
| 产物已提交，控制状态未完成 | 通过名称和内容摘要复用本次产物；不产生第二次执行 |
| Records attempt 已完成，控制表未完成 | 从该 attempt 的持久结果恢复 finished |
| 清理未确认或证据归档失败 | 保留槽位和源 spool，重试查询/归档；不把实验失败与清理失败混为一谈 |

生命周期事件使用稳定 producer sequence 和每 Attempt 独立的幂等键。结果分别描述 execution、exit_code、
cleanup、capture、missing_outputs；evaluation/protocol 为未解释/未验证。租约释放是持久资源状态；
结果中的 `slot_held=false` 只在收尾后出现。BM05-A 租约负责准入，普通进程 backend 仍不提供
CPU/GPU 物理限制或实际用量证明。

## 扩展时沿用的边界

- 新 bench 的目录理解、原生参数和产物含义留在独立包，不在 core 按 benchmark 名分支。
- `invocation` 必须确定性、无执行副作用。`prepare/run` 前后校验源快照和重新生成的计划/命令，
  但不会神奇验证任意远端 URL 的内容；不可变外部资源预检是适配器/相应 backend 的职责。
- 本机命令的 capability 不代表能管理其创建的 Docker/Slurm/Harbor 作业。首次出现这些后端时，
  先补原生 job ID、资源和清理证据，再复用 Run 编排；不能只套一层 subprocess 就宣布支持。
- 后续接入原生轨迹解释和 Outcome 时保留原始文件、协议预算/可见性，复用当前 Records 引用。
- BM05-B 的受控并发、资源采样、预算和本地大文件恢复见[实现说明](benchmark-batch-bm05b.md)；远端调度、原生评分和优化循环仍分别实施。

验证入口：[BM01 任务记录](../changes/20260922-benchmark-execution-bm01-a4f8d2.md)和
[BM05-A 任务记录](../changes/20260922-benchmark-reliability-bm05a-91d7c4.md)。
