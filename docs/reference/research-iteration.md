# 结果分析与有界科研迭代

状态：I 批首版，CLI / HTTP / MCP 已实现；集成与实际验收范围见[任务记录](../changes/20260920-research-iteration-i73c9a.md)。
依赖已初始化 Project、已采用的研究 Plan、本机 Controller 和已编译的科研 Task。
本入口只处理无私有评测的科研任务，不给原 benchmark 添加反馈或额外重试。

## 使用路径

1. 按[本机运行说明](local-run-controller.md)完成实验；或通过 H 宿主机 Agent 完成 Job 并关闭、归档环境。
2. 查询真实 Run 和 Artifact，把解释保存为 Analysis。失败实验也可保存分析。
3. 用户接受、修改或拒绝建议；接受/修改生成下一版研究快照并采用，随后复用 C 的 compile 和 D 的 submit。
4. 对已经冻结的候选 Task 建立有限授权，外部 Agent 或容器 Planner 在授权集合内选择下一次执行。
5. 新方法、新数据或超预算的建议需要新决策与授权。首版不自动把任意自然语言建议当作执行权限。

`STATE` 是已有状态目录，`PROJECT` 是项目 UUID。先保持 Controller 运行：

```bash
agent-infra controller serve --state-dir "$STATE" --cpu 1 --memory-gib 2 --port 8766
```

## I01：分析引用证据

先使用 `run status`、`run artifacts`、`run artifact` 查询归档成员；H 环境也可用 `research artifacts`。
复制并修改[分析示例](../../examples/research-iteration/analysis.json)，替换真实标识和解释：

```bash
agent-infra study analysis-save --state-dir "$STATE" --project-id "$PROJECT" \
  --operation-id analysis-round-1 --file analysis.json
agent-infra study analyses --state-dir "$STATE" --project-id "$PROJECT"
```

`results` 每项字段：

| 字段 | 语义 |
| --- | --- |
| `run_id` | 本项目已经结束的 Run，失败结果保留 |
| `artifact_id`、`member` | 此 Run 的公开或用户可见归档及精确文件名；私有评测/凭据不可读 |
| `metrics` | 可选：name、JSON pointer、unit、direction；数值从归档 JSON 提取，不接受手工 value |
| `data_version`、`code_version` | 已知时记录；缺失可留 null。声明来源明确标记为 caller_declared |

顶层还要求 `observations`、`interpretation`、`uncertainty`、`recommendation`。
指标文件限 1 MiB；方向为 maximize/minimize/inspect，数值必须有限。
没有输出的失败分析可只提供 run_id。分析保存 Run 结果、冻结 Task lineage、成员内容 SHA-256；
原始轨迹/文件仍由 Records 保存。修改解释使用新 operation-id，并可提供 `supersedes` 旧 analysis_id。
同一操作 ID 重试不创建重复分析，改参数则报冲突。

比较仅按同一声明的数据版本、指标名、单位和方向分组，不自动排名、不证明协议等价。
未知版本、失败执行不能被当作“改进”的可靠证据。调用者声明不是代码对数据内容真实性的认证。

## I02：用户决策

准备 decision.json：

```json
{
  "analysis_id": "真实分析 ID",
  "choice": "reject",
  "reason": "当前证据不足，暂不增加实验",
  "authorization": "用户本次选择及其可追溯来源",
  "expected_revision": 1,
  "expected_digest": "sha256:当前研究快照摘要"
}
```

```bash
agent-infra study decide --state-dir "$STATE" --project-id "$PROJECT" \
  --operation-id decision-1 --file decision.json
agent-infra study decisions --state-dir "$STATE" --project-id "$PROJECT"
```

`choice` 为 accept/modify/reject。前两者还需完整 B 格式 `draft`，Brief 保持不变，至少新增一个实验 ID；
新的研究 revision 与原因关联 analysis/decision。确认旧 revision 或错误 digest 拒绝。
reject 不产生研究 revision、不执行实验。所有决定都不会修改旧 Task/Run。

操作中断可用同一 ID、同一参数重试：持久决策 → 幂等保存 → 精确采用 → 完成回执。
若之后已有其他研究修改，恢复会报告冲突，需用户重新审阅；不会强行覆盖。
Markdown 投影若和手工笔记冲突，按 B 的 export/check 流程处理，数据库快照仍为权威。
新的计划采用后，复用 `agent-infra project compile`，不另造编译链路。

## I03：授权与迭代

授权绑定当前已采用研究 revision/digest、冻结 Task 集合和实际本地镜像 ID。
任务列表中的每项采用 D 的 SubmissionRequest：task_id、task_revision、model；
可选 provider（当前实际 D 为 codex）、timeout_seconds、network、reasoning_effort。
以下是 authorization.json 的结构示意，标识须替换：

```json
{
  "authorization": "用户批准最多两次 CPU 实验",
  "expected_revision": 1,
  "expected_digest": "sha256:实际研究摘要",
  "tasks": [{
    "task_id": "已编译 Task ID",
    "task_revision": "冻结 Task revision",
    "model": "用户选择的模型",
    "network": true,
    "timeout_seconds": 180
  }],
  "max_experiments": 2,
  "total_seconds": 360,
  "wall_seconds": 900,
  "cpu": 0.5,
  "memory_bytes": 536870912,
  "stop_on_failure": true
}
```

```bash
agent-infra study authorize --state-dir "$STATE" --project-id "$PROJECT" \
  --operation-id approval-1 --file authorization.json
agent-infra study workflows --state-dir "$STATE" --project-id "$PROJECT"
agent-infra study step --state-dir "$STATE" --project-id "$PROJECT" \
  --workflow-id "$WORKFLOW" --task-key "$TASK_KEY" --operation-id round-1
agent-infra study status --state-dir "$STATE" --project-id "$PROJECT" --workflow-id "$WORKFLOW"
agent-infra study read --state-dir "$STATE" --project-id "$PROJECT" \
  --workflow-id "$WORKFLOW" --run-id "$RUN"
agent-infra study stop --state-dir "$STATE" --project-id "$PROJECT" \
  --workflow-id "$WORKFLOW" --reason '用户停止本轮研究'
```

authorize 返回 workflow_id 和 tasks 中的 task_key。step 异步返回原有 D Run，刷新 status 读取结果。
相同 task_key 可作为重复试验，但每次新 operation-id 消耗一次实验额度。
进程锁串行检查预算、保存动作和执行提交；同一动作重试沿用原提交 ID。
响应丢失、Controller 重启或 Planner 更换后，先查 actions；已启动 Run 不重放。
中断按 D 的清理恢复规则处理，默认失败即停止；用户可在初次授权中关闭 stop_on_failure。

时间采取保守预算：每次预扣完整 timeout，不返还提前结束的剩余时间；崩溃同样保留扣款。
wall_seconds 是授权截止期限，只接受能在期限内运行完整 timeout 的新动作。
进程超时按 D 执行，控制调用和清理有额外宽限。并发实验为 1；CPU/内存还受宿主机 Controller 总额度约束。
无 GPU；无权威模型账单接口，返回 cost.observable=false，不承诺精确费用硬上限。
费用记录不是收费限额；操作系统用户仍可显式发起新的独立授权或使用旧手动接口。

MCP 增加 analysis_save/list、iteration_workflows/status/step/read。
授权和采用入口保留在操作员 CLI，不向容器 Planner 暴露。

## I04：可替换的容器 Planner

使用已有可信 Codex 0.154.0 镜像及宿主机文件认证，前置条件同 D。
Planner 资源必须给独立实验留余量：例如总 1 CPU / 2 GiB，Planner 用 0.5 CPU / 1 GiB，
Task 用 0.5 CPU / 512 MiB。分配不足会拒绝，不会超卖。

```bash
agent-infra planner start --state-dir "$STATE" --project-id "$PROJECT" \
  --workflow-id "$WORKFLOW" --operation-id planner-session-1 \
  --image agent-infra/codex-research:0.154.0 --model "$MODEL" \
  --cpu 0.5 --memory-bytes 1073741824 --timeout-seconds 180 \
  --prompt '执行下一项已授权实验，分析真实指标后结束会话'
agent-infra planner status --state-dir "$STATE" --project-id "$PROJECT" --run-id "$PLANNER_RUN"
agent-infra planner stop --state-dir "$STATE" --project-id "$PROJECT" --run-id "$PLANNER_RUN"
```

start 创建独立 Planner Run 并异步返回。相同操作重试返回同一 Run；更换容器用新 operation-id 和原 workflow_id。
Planner 每次从外置 context/actions 恢复，不依赖旧聊天、旧容器目录或 Codex resume。
Planner 会话次数和模型时长由启动者授权并控制，和 workflow 的实验次数/时长分别计量；首版不后台自动重启 Planner。

容器仅有私有临时认证副本、空工作区和只读标准库 helper。
helper 支持 context/status/step/read/analysis，通过有大小限制的文件请求由宿主机代理执行；
不传 Controller token、宿主机项目目录、Docker socket 或私有 scorer 文件。
它与宿主机入口调用同一 Projects/Run 用例，不能改 project/workflow 绑定或扩大任务集合。
宿主机 Agent 使用 MCP；容器 Planner 首版使用此窄 CLI helper，不需要容器安装完整 infra 包。
原始 stdout/stderr、标准化 Agent 事件及代理请求结果进入 Records。
停止 Planner 不撤回已启动实验，停止 workflow 会请求取消它所属的活跃 Run。

首版不包含科学结论自动裁决、通用 DAG、自动构建任意新实验、分布式 Planner、Web 操作页。
