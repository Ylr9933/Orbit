# BM01：Benchmark 受管执行

状态：执行扩展 **1.0**，基于 SDK **1.0**；本任务分支实现，集成状态以 Git 为准。
适用于 Linux、单管理员、同一状态目录下的一个可信本机进程任务。真实短时 CPU 进程和独立 wheel
已验收；本文描述 BM01 通用进程后端。TB-Science 的新增原生容器入口见
[BM02-A 操作说明](../operations/tb-science-native-trial.md)，其余三个原生 benchmark 尚未验收。

BM00 负责描述和检查协议；BM01 增加“冻结具体命令 → 持久提交 → 查询/取消 → 归档”。
原生评分、容器资源控制、批量调度、Web 页面及外层优化仍按[阶段计划](../development/benchmark-development-plan.md)推进。

## 适用范围

| 项目 | BM01 行为 |
| --- | --- |
| 运行单位 | 一个 WorkUnit、一个 `owner=native` 的 Phase；原生程序可以拥有内部顺序 |
| 后端 | `managed-process-v1`，独立监督进程管理协作式本机命令 |
| 凭据与输入 | 不继承宿主机完整环境变量；stdin 和显式环境注入暂不支持。适配器通过非敏感 argv/固定路径描述输入 |
| 超时 | 支持命令墙钟超时；协议声明了预算时必须是 `process_start`，且与命令 timeout 一致 |
| 资源 | 没有 CPU/内存/GPU 硬限额。显式资源要求（含外部分配器声明）会拒绝，不能视为已经分配资源 |
| 隔离 | 同 UID、本机权限；不是沙箱。含不允许 solver 读取的材料会拒绝；不能运行不可信 Agent 或秘密 grader |
| 清理 | 本次监督进程拥有的进程组。子进程必须遵守该范围；脱离会话的 daemon、Docker 子容器不属于已支持能力 |
| 重试 | 同 operation ID 查询/续采，不再启动。新试验需新 ID；平台拥有的协议重试尚不支持 |
| 记录 | stdout/stderr 合并原始字节、生命周期事件、声明的输出和执行收据；不自动解析 Agent 原生消息或评分 |

适配器是受信任 Python 包。所有 inspect/plan/check/prepare 都可能调用其代码，显式启用和命令摘要
不是恶意代码防护。`--allow-host-process` 表示用户接受审核过的命令以当前用户身份执行。
不要通过删除资源、可见性或能力要求来绕过预检；需要新后端时单独实现、验收。
这里的 `process_start` 是本后端监督器进入执行阶段的单调时钟起点，包含子进程启动开销；
不能将原 bench 的首次模型调用、首个 episode 等不同起算点直接重命名成它。

## 从示例开始

已有核心安装的环境可以单独安装[执行示例包](../../examples/benchmark-execution/)；不要修改共享环境做验收。
示例只将 `[1,2,3,4]` 求和并输出 `result.json`，不调用 Agent、容器、GPU 或外部评分服务。
一次性完整验证使用独立临时环境，退出后删除本次测试状态：

```sh
uv build
uv run --locked python scripts/acceptance/benchmark_execution.py
```

实际使用时，将核心 wheel 和适配包 wheel 安装到同一专用 Python 环境；保留该环境直到执行结束。
以下假定 `agent-infra` 来自该环境，当前目录有适配器提供的
`adapters.toml`、`request.json`、`capabilities.json` 和不可变小型 `fixture/`：

```sh
agent-infra benchmark plan process-demo \
  --source fixture --request request.json --output plan.json --config adapters.toml
agent-infra benchmark check plan.json --config adapters.toml --capabilities capabilities.json
agent-infra benchmark prepare plan.json --output execution.json --config adapters.toml
cat execution.json

INFRA_BENCH_STATE=/absolute/path/to/benchmark-state
agent-infra benchmark run execution.json \
  --operation-id study-001 --allow-host-process \
  --config adapters.toml --capabilities capabilities.json --state-dir "$INFRA_BENCH_STATE"
```

`prepare` 将原生 argv、相对 cwd、超时、输出路径与 BM00 完整计划一起冻结，输出 0600 新文件；
不会覆盖旧文件或写进输入快照。`run` 再验证摘要、包身份、输入、重新生成的 invocation 和能力声明。
命令、源目录、Python 安装路径等改变后需重新规划/准备，不能直接改 JSON 后继续使用旧确认。
此阶段不注入任意宿主机凭据，argv 和冻结文件中也不要放令牌。

`run` 返回后命令可能仍在执行。记录返回的 `run_id` 和 `attempt_id`：

```sh
agent-infra benchmark status RUN_ID --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark events RUN_ID --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark artifacts RUN_ID --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark cancel RUN_ID --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark reconcile --state-dir "$INFRA_BENCH_STATE"
```

上述大写 ID 是替换位置，不是 literal 参数。`events --cursor CURSOR` 可续读；当前页上限 200。
`status/cancel/reconcile/events/artifacts` 不重新加载适配包；即使源目录暂时不可读，也可查询和收尾。
这些命令会同步日志、对账状态并尝试归档，因此不是纯只读查询。没有自动轮询守护服务，停止查询时
监督器仍会执行超时/清理并保存原始 spool；后续 `status` 或 `reconcile` 再将证据归入 Records。

退出码 `0` 表示控制命令成功，不表示实验成功；检查 `state` 和 `result.execution`。
检查报告不兼容为 `1`，配置/契约/调用错误为 `2`。`cancel` 返回也不代表资源立即清理完毕，需继续查询。

## 恢复语义

| 状态 | 含义与处理 |
| --- | --- |
| `accepted` | 控制意图已保存，后端确认没有提交；reconcile 不自动启动，可显式重复原 `run` 命令或取消 |
| `submitting` | 提交意图已经保存，正在联系后端；重启后先 reconcile |
| `running` | 找到本次真实进程身份，继续观察 |
| `quarantined` | 启动回执未到、身份失联或清理尚未确认；保留槽位，继续查询。短暂启动窗口也可能出现此状态 |
| `collecting` | 归档失败；保留执行源数据和槽位。修复存储故障后查询，只重试归档 |
| `finished` | 清理和证据归档已确认。实际结果可能是 completed、failed、timed_out 或 cancelled |

同一个 operation ID 的参数必须完全一致，否则拒绝。提交响应丢失时，重复提交/查询都先根据持久
operation 查原生身份，不产生第二次启动。监督器身份包含 boot ID、PID、进程 starttime；不只凭 PID 发信号。

持久 `launch.json` 写在真正创建进程之前：即使崩溃恰好发生在两者之间，也保守地视为“可能已启动”。
如果监督器死亡且没有完整清理收据，BM01 不自动重启、不自动释放、不提供强制遗忘命令。
管理员需要调查该次 native 目录、进程身份及输出，确认真实清理和数据保全；不要删除数据库或换 state-dir
绕过隔离。完整的人工解除隔离流程和外部 job 对账在后续可靠性阶段补充。

每个状态目录只有一个持久执行槽，**不等于资源租约**。多个状态目录之间没有全局 CPU/GPU 配额协调，
也不进入现有科研 Controller 的调度槽。本阶段只用于受控的小型本机任务。

## 日志和产物在哪里

```text
STATE/benchmarks/
  control.sqlite3        # operation、Run/Attempt、handle、日志游标、执行槽
  native/<operation摘要>/
    spec.json            # 具体命令和预算
    launch.json          # 持久启动意图
    owner.json           # 原生进程身份
    combined.log         # 合并 stdout/stderr 原始字节
    result.json          # 执行/清理收据
    collected/           # 冻结输出副本和 execution-receipt.json
  workspaces/<run_id>/    # 命令的可写工作区
  records/               # 复用现有 Records：事件、原始流、内容寻址产物
```

默认原始日志保留前 8 MiB，超出继续排空进程管道，并标记 `truncated`；声明输出总量上限 16 MiB。
仅收集 `NativeInvocation.outputs` 声明的相对路径，拒绝越界、符号链接和特殊文件；缺失输出记录
`missing_outputs`/`capture=partial`，不捏造成功材料。大模型权重和断点传输尚不在此版本能力范围。
本轮不会自动删除原始 spool、工作区或快照；备份/回收时应在 finished 后一并处理这套状态。

`result.stream.blob` 是原始流引用，`artifact_id` 对应一个 `native-submission` 产物。
原始流和产物默认 ADMIN 可见，不自动作为 solver/optimizer 反馈；当前 benchmark CLI 是本机管理员入口。
既有 Records 命令也可以查询同一数据：

```sh
agent-infra records attempt ATTEMPT_ID --root "$INFRA_BENCH_STATE/benchmarks/records"
agent-infra records trajectory ATTEMPT_ID --root "$INFRA_BENCH_STATE/benchmarks/records"
```

轨迹是执行生命周期，不是模型对话。`coverage.agent_native=not_instrumented`；后续原生适配器需要
声明并归档 agent 原始文件，再增加版本化解释器。执行成功不意味着评分成功或符合官方协议。
读取原始字节可以使用公共 Records 接口，不需要自己拼内容寻址路径：

```python
from pathlib import Path
from agent_infra.records.api import BlobRef
from agent_infra.records.local import LocalRecordsStore

records = LocalRecordsStore(Path("/absolute/path/to/benchmark-state/benchmarks/records"))
attempt = records.get_attempt("ATTEMPT_ID")
with records.open_blob(BlobRef(**attempt.result["stream"]["blob"])) as source:
    print(source.read().decode("utf-8", errors="replace"))
```

更多代码职责与故障窗口见[实现说明](../implementation/benchmark-execution.md)。
