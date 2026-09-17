# 项目当前状态

Updated at: 2026-09-17T11:23:27+08:00

Basis: 本文描述本地 `main@8a6c3f9` 已集成的事实。远端 `origin/main` 尚未包含该合并；
Git 历史和各任务记录仍是具体变更的依据。

当前结论：项目已经完成工程基础、核心模块首版和一条经过 Docker fixture 验证的
单机容器执行内核，但还没有形成普通用户可以直接提交真实 Agent 任务的完整产品闭环。
S1、S2 和早期 S4 正在并行推进，S3 尚未开始。

## 1. 阶段状态

| 阶段 | 状态 | 当前结论 |
| --- | --- | --- |
| S0：工程基础 | `accepted` | Python/Web 工程、锁文件、检查、测试、依赖边界、CI 配置和协作规范已经建立，并有本机验收证据。 |
| S1：模块契约与任务样例 | `in_progress` | Agent、Tasks、Resources、Environment、Run 和 Records 的首版契约已存在；ToolBinding、稳定任务目录和原生 benchmark 等价性尚未完成。 |
| S2：完整单节点工作流 | `in_progress` | CPU Docker fixture 已跑通求解、隔离评测、记录、取消和清理；还没有公开 Run 入口和真实 Agent 闭环。 |
| S3：两节点执行与故障处理 | `not_started` | 没有 Ray backend、Worker 服务、节点加入、跨节点记录上传和故障恢复。 |
| S4：Web 与批量评测 | `in_progress` | 本机 Web 可查看资源、项目、任务、Agent 状态和历史记录；不能启动/取消 Run，批量评测尚未实现。 |

## 2. 当前真正能运行什么

### 2.1 工程和开发入口

以下入口已经实现并经过检查：

```bash
make setup
make verify
uv run --locked agent-infra --version
uv run --locked agent-infra config-check --config configs/defaults.toml
```

最近一次在合并后的 `main` 上执行 `make verify`，结果为：

- Ruff、格式检查、Mypy、TypeScript、Biome 和模块依赖检查通过；
- 115 个非 E2E 测试通过；
- Python wheel/source distribution 和 Web 生产构建通过；
- 文档链接以及 `AGENTS.md` / `CLAUDE.md` 一致性检查通过。

另外执行了 7 个真实本机 Docker E2E，用 CPU fixture 验证了求解、独立评分、提交代码隔离、
私有材料不可见、只读输入、错误答案、超时、取消、后台进程清理、产物收集和 Records 归档。
全部通过；这些测试没有调用模型、没有使用 GPU，也不等于真实 benchmark 验收。

### 2.2 已提供的 CLI

当前 CLI 可以：

- 检查 Codex、Claude Code 和 DSH 的安装、版本及登录状态；
- 安装缺失的受支持 Agent CLI；
- 查看本机 CPU、内存和 NVIDIA GPU 快照；
- 校验资源请求 YAML；
- 创建、校验、冻结和准备 Task，索引 ResearchClawBench workspace；
- 查询本地 Run/Attempt、事件、产物和轨迹，导出固定 JSONL 数据集；
- 启动本机只读研究 Web 控制台。

CLI 目前不能提交、重试或取消 Run，也不能创建 Ray 集群。

### 2.3 Web 控制台

Web 启动方式：

```bash
pnpm build
uv run --locked agent-infra web \
  --records-root var/runs/_records \
  --console-dir var/console \
  --web-root src/web/dist \
  --task examples/task-packages/file-result/task.yaml
```

当前页面支持：

- 实时查看本机 CPU、内存和 NVIDIA GPU 观测值；
- 创建科研项目，维护目标、状态和人工确认的里程碑；
- 关联已经注册的 Task 和已有 Run；
- 查看 Agent 安装、认证和能力状态；
- 查看 Run、Attempt、规范事件、Agent 轨迹摘要和产物元数据；
- 过滤 evaluator/private evaluation、credential 和 secret 记录。

Web 只监听 `127.0.0.1`，使用每次启动生成的令牌，定位为本机单管理员工具。
它当前是查询和整理界面，不是执行控制台；详细边界见[使用说明](operations/web-console.md)。

### 2.4 已实现但只能由 Python 组装的执行内核

当前最完整的内部执行路径是：

```text
Task manifest
  → 任务可见视图与资源要求校验
  → LocalResourceManager 分配 Lease
  → LocalRunService 协调 Attempt
  → DockerEnvironment 启动求解容器
  → Agent 进程执行并产生结构化 stdout
  → 停止和删除求解容器
  → 冻结提交与保存 Artifact
  → 独立 submission/scorer 容器（可选）
  → Records 保存事件、原始流、产物、反馈和 reward
  → 核实清理后释放 Lease
```

这条路径已经由 fixture Agent 和真实 Docker 验证。调用者仍需自行构造 Monitor、
NodeCapacity、LocalResourceManager、DockerEnvironment、Agent adapter、凭据目录和可信评测 recipe。
目前没有 bootstrap 服务或公共命令替用户完成这套组装。

## 3. 各模块的实现状态

| 模块 | 已实现 | 还没有实现或打通 |
| --- | --- | --- |
| Agent | Codex、Claude Code、DSH 的 probe/install、宿主机与容器启动计划、凭据文件 staging、JSONL 事件归一化 | Run 入口自动选择 provider、自动准备凭据、真实模型任务验收、统一模型/Token/费用预算、稳定恢复语义 |
| Tasks | 版本化 manifest、材料可见性、Agent view、冻结摘要、资源边界、研究草稿、ResearchClaw/ASI workspace 索引 | 自然语言补全工作流、稳定 Task catalog、工具实际注入、原生 benchmark 执行和评分等价性 |
| Resources | Linux/NVIDIA 监控、资源 YAML、本机授权容量、线程安全 Lease、资源不足原因 | Web 采样与分配器共享状态、持久 Lease、等待队列、跨进程互斥、磁盘额度、Ray backend |
| Environment | 一次性 Docker 容器、只读输入、CPU/内存/GPU UUID 参数、网络控制、日志、取消、清理和冻结输出 | 镜像构建/叠加、长生命周期环境、后台作业、交互 Session、文件/工具 API、重启恢复 |
| Run | 同步单 Attempt 协调、求解/提交/评分分阶段、取消 Event、失败分类、清理后释放 | 后台 Controller、持久状态机、公开 submit/status/cancel/retry、排队、崩溃对账、远程 Worker |
| Records | SQLite/CAS、Run/Attempt、幂等事件、stream、Artifact、轨迹图、训练样本和 JSONL 导出 | 宿主机 Agent 全链路采集、跨进程 spool、远端归档、指标时序、Parquet/训练框架导出、保留策略 |
| Gateway | CLI 诊断与查询、本机鉴权 HTTP 查询 | Run 控制 API、SSE/WebSocket、MCP 工具服务器、Worker 协议、多用户鉴权 |
| Web | 总览、科研项目、Task、Run、Resources、Agents、Records 和设置页 | 提交/取消/重试、实时日志、交互对话、产物下载、批量实验、集群管理和细粒度权限 |

## 4. 当前没有打通的关键链路

### 4.1 用户还不能直接提交一次 Run

`LocalRunService.run()` 已实现，但 CLI、HTTP 和 Web 都没有调用它。Web 的 capabilities 明确返回
`run_control=false`。因此用户现在不能通过正式入口完成“选择 Task 和 Agent → 申请资源 →
运行 Docker → 查看结果”。这是当前最优先的集成缺口。

### 4.2 资源监控和资源分配尚未组成同一项服务

Web 的 ResourceSampler 负责展示机器观测值，LocalResourceManager 负责内存中的 Lease；
两者没有由 bootstrap 组装成共享生命周期。没有服务持续调用 `update_snapshot()`，也没有跨进程
Lease 持久化。启动两个控制进程可能重复分配同一资源。

### 4.3 真实 Agent 镜像与凭据流程尚未闭环

Agent adapter 可以生成容器命令，仓库也有安装单个 CLI 的 Dockerfile，但系统不会自动把
任务依赖和所选 Agent 叠加成同一个可信镜像。Run 还要求调用方事先准备凭据副本。
目前没有真实 Codex/Claude/DSH 在任务容器内完成任务的验收证据。

### 4.4 宿主机 Agent 控制 Docker 的科研模式尚未实现

设计中的 MCP、长作业、增量日志、Session 和环境绑定都还没有实现。当前 Run 固定使用容器内
Agent；Records 也只能记录平台当前能够观察到的容器 Agent stdout 和环境事件，不能宣称已经完整
记录宿主机 Agent 在平台外执行的命令。

### 4.5 Task Tool 和 benchmark 仍停留在契约/索引阶段

Task 可以声明 MCP、CLI 或 function Tool，但只要 required Tool 非空，Run 当前就会拒绝执行，
因为没有 ToolBinding。ResearchClawBench 和 ASI-Bench importer 只建立索引并保留原始材料，
尚未证明原生运行、预算、重试、聚合和评分协议等价。

### 4.6 多节点基础设施尚未开始

`gateways/worker`、`deploy/ray` 仍为空骨架。没有节点服务、心跳、远程派发、记录上传、节点失联
处理、资源对账或两节点验收。当前 Docker backend 明确只允许本机 Unix Docker socket。

## 5. 已知设计债务和风险

- Web 中 Project 关联 Task 使用任务清单绝对路径的哈希；仓库移动或换机器后关联可能失效。
  应改为稳定的 `task_id + revision + definition_digest` 或持久 Task ID。
- Task 通过 Web 启动参数临时注册，没有持久 Task catalog、版本检索和生命周期管理。
- Python HTTP DTO 与 TypeScript 类型目前手工维护，尚无 OpenAPI/JSON Schema 单一来源，存在契约漂移风险。
- Agent 规范事件在求解阶段结束后从 stdout 统一解析，尚不能提供真正的实时 token/工具事件。
- LocalResourceManager 只在单进程内可靠；控制进程崩溃后不能自动重建 Lease 或确认残留容器。
- Python wheel 不包含 Web 构建资产，仓库外安装时必须显式提供 `--web-root`。
- 当前 HTTP 是 loopback 单管理员实现，不适合直接暴露到公网或作为多人服务。
- GPU UUID 已传给 Docker，但没有实际 GPU 工作负载验证；资源参数存在不等于 GPU 闭环通过。

## 6. 接下来的实现顺序

### 第一优先级：打通单机可操作闭环

1. 实现持久化的 Run Controller 和后台执行器，定义 submit/status/cancel/retry 行为。
2. 在 bootstrap 中组装共享 Monitor、LocalResourceManager、DockerEnvironment、AgentRegistry 和 Records。
3. 增加 `agent-infra run submit/status/cancel`，再暴露对应 HTTP API。
4. 建立稳定 Task catalog，Project 使用稳定 Task 标识，不再依赖绝对路径哈希。
5. 为 Codex 构建一个任务依赖与 Agent CLI 共存的可信镜像，安全 staging 凭据。
6. 在明确模型、时间、CPU/内存和费用预算下完成一次真实 Codex 单机任务；验证取消、轨迹、产物和清理。
7. Web 接入 Run 创建/取消、状态轮询、增量事件和受控产物下载。

完成标准：用户通过一个正式入口提交 Task，系统自动分配本机资源并启动 Docker 中的真实 Agent；
进程结束或取消后，可以从 Web/CLI 查询状态、轨迹、产物和资源释放结果，控制服务重启后仍能对账。

### 第二优先级：完成两种使用模式和真实任务协议

1. 实现 Environment 的后台 Job、文件操作、增量日志和 Session 契约。
2. 实现本机 MCP gateway，使宿主机 Agent 能控制绑定环境，并将平台内工具调用写入 Records。
3. 实现 ToolBinding，支持声明式 MCP/CLI/function 工具注入和权限检查。
4. 为一个原生 benchmark 实现完整 adapter 和可信 EvaluationRecipe，再用第二种任务结构验证抽象通用性。
5. 增加任务/环境方案助手：先支持模板和已有镜像，再加入自然语言建议、人工修改和有限次修复。

### 第三优先级：持久化、分布式和规模化

1. 持久化队列、Lease、Worker 状态和崩溃恢复；实现节点容器与平台记录对账。
2. 定义 Worker 协议和本地节点服务，先证明单控制端/单 Worker 的远程执行。
3. 实现 RayResourceManager 和两节点部署/验收，处理节点失联、排空和资源回收。
4. 增加跨节点 Records spool、远端对象存储和备份恢复。
5. 实现批量实验、benchmark 聚合、对比分析，以及面向 Agentic RL 的 Parquet/训练框架导出。
6. 最后扩展多用户身份、项目级授权、审计、TLS/反向代理和生产监控。

## 7. 当前项目级阻塞条件

- 真实 Agent 验收需要用户授权的模型账号、可用凭据、网络以及明确费用和时间预算。
- GPU 验收需要获准占用的 GPU 和测试镜像；本轮只做了只读观测。
- 两节点/Ray 验收需要第二台获准节点、私网互通、统一版本和可达的数据/镜像来源。
- 远端 `main`、托管 CI、GitHub branch protection 和 reviewer 权限仍需要在 GitHub 上单独验证。
- 项目 License 尚未确定，当前空 LICENSE 不构成开源许可。

## 8. 相关文档

- [总体模块设计](architecture/agent-environment-modules.md)
- [开发顺序](development/development-sequence.md)
- [Run / Environment 契约](architecture/run-environment-contract.md)
- [单节点执行参考](reference/run-environment.md)
- [Records 设计](architecture/records-design.md)与[实现解读](implementation/records-implementation-guide.md)
- [Web 方案](architecture/web-console-design.md)与[使用说明](operations/web-console.md)
- [Web 实现记录](changes/20260916-web-console-3c7e91.md)
