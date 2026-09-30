# Orbit 设计

状态：R0 已确定的目标设计；R1（单机科研闭环）已实现；R2（认证与通知）按 §6 实现中。实现进度见 [status.md](status.md)。本文是架构与接口的唯一权威来源；
改变模块边界、公共契约或关键决策时，在同一分支更新本文。

## 1. 定位

> Orbit 让 Codex / Claude Code 等 Agent 在隔离的 Docker 中按资源规则运行实验，
> 并完整记录过程与结果；Web 用于本地复盘。

- **Agent 是本体**：规划、写代码、分析由 Agent 和人完成。Orbit 不启动"规划 Agent"、不审批研究方案、不编排科研流程。
- **Orbit 是插件和规范**：提供 CLI（Agent 通过 bash 调用，`--json` 输出）、薄 MCP、skill 与约定（指标、产物、实验笔记的写法）。
- **两种用法，同一个执行原语 Run**：
  1. 日常科研：宿主机上的 Agent 改代码 → `orbit run` 把代码快照放进容器跑 → 监控、比较、复盘。
  2. 刷榜：`Agent + 方法包 × Benchmark`，每个 trial 在容器中运行 Agent，再独立评测，保留轨迹和分数。
- **使用范围**：单人使用；一台或多台自己的机器（可跨网络，Tailscale）；空闲资源都可以用。
- **不做**：多用户/权限、云控制面、自研 Agent 循环、自研实验追踪全功能替代品、官方榜单自动提交、手机对话（后续再议）。

## 2. 总体结构

```
Agent (Codex / Claude Code, on host)
  │  plugin: skill + hooks      CLI: orbit ... --json      MCP (thin, optional)
  ▼
orbit daemon (one per node; single writer of local state)
  ├─ resources   ledger of GPUs/CPU/memory (+ future devices), probes, leases, queue
  ├─ runs        Run lifecycle, scheduling loop, sweeps, rerun
  ├─ executor    docker backend (process backend for native benchmark runners)
  ├─ workspace   code snapshot (commit + diff), mounts, named datasets/weights
  ├─ images      base images, project Dockerfile build cache
  ├─ auth        credential profiles for harnesses (login / API key / relay base URL)
  ├─ harness     how each Agent CLI is installed, configured and parsed inside containers
  ├─ records     logs, metrics, artifacts, events, notes
  ├─ sessions    host Agent session capture (Codex, Claude Code) linked to runs
  ├─ bench       adapters, agent profiles + method bundles, trials, outcomes
  └─ cluster     node join, heartbeat, remote placement (R4)
  ▼
Web (local SPA served by the daemon): runs, compare, logs, sessions, bench review
```

技术栈：TypeScript（Node 24，开发时直接运行 `.ts`），`node:sqlite`（无原生依赖，便于 npm 安装），
直接调用 `docker` / `nvidia-smi` / `git` 命令行，Hono HTTP，zod 契约，commander CLI，
vitest 测试，Biome 格式/lint，tsdown 打包。发布为单个 npm 包 `@zjunlp/orbit`，命令 `orbit`。

## 3. 代码布局与依赖方向

```
packages/orbit/src/
  contracts/   zod schemas + types shared by daemon, CLI, MCP and Web (no runtime deps on modules)
  lib/         small generic helpers (process exec, ids, time, fs)
  config/      paths (~/.orbit), config file, daemon endpoint/token
  store/       sqlite access and migrations
  resources/ auth/ images/ workspace/ executor/ harness/ records/ notify/ sessions/   domain modules
  runs/        orchestrates domain modules into a Run
  bench/       builds trials on top of runs
  cluster/     multi-node (R4)
  daemon/      HTTP API + scheduler loop wiring (composition root)
  client/      typed HTTP client for the daemon API
  cli/         commander commands; talks to daemon through client only
  mcp/         MCP tools; talks to daemon through client only
  bin.ts       composition root of the `orbit` executable (wires cli + daemon); nothing imports it
packages/web/  React SPA (Vite, uPlot); imports `@zjunlp/orbit/contracts` types only; built into
               packages/orbit/dist/web and served by the daemon
plugin/        skills/orbit/SKILL.md for Codex / Claude Code (+ .claude-plugin manifest)
```

规则（由 `pnpm check:boundaries` 强制，定义在 `scripts/boundaries.ts`）：

| 模块 | 可以依赖 |
| --- | --- |
| contracts, lib | 无（contracts 仅依赖 zod） |
| config, store | contracts, lib |
| resources, auth, images, workspace, executor, records, notify | contracts, lib, config, store |
| harness | 上一行 + auth |
| sessions | contracts, lib, config, store, records, harness |
| runs | 以上所有 domain 模块 |
| bench | runs 及其可依赖的模块 |
| cluster | runs, resources 及基础模块 |
| daemon | 除 cli/mcp/client 外全部 |
| client | contracts, lib, config |
| cli, mcp | client, contracts, lib, config |
| web (`packages/web/src`) | 自身文件；`@zjunlp/orbit` 只能 `import type` 自 `@zjunlp/orbit/contracts` |

- **daemon 是本机状态的唯一写者**。CLI/MCP/Web 只通过 HTTP API 访问；CLI 需要时自动拉起 daemon。
  daemon 只监听 `127.0.0.1`（默认端口 7717，`ORBIT_PORT` 可改），启动时生成随机 token，与地址一起写入
  `~/.orbit/daemon.json`（0600）；所有 `/api/v1` 请求需 `Authorization: Bearer <token>` 或 Web 登录后的
  HttpOnly cookie。`ORBIT_HOME` 可覆盖 `~/.orbit`。
- `src/` 根目录下的文件（如 `bin.ts`）是组合根，可引用任意模块，但不能被模块引用。
- 同类能力只有一份实现：一个 Run 状态机、一个资源账本、一个记录库。
- Docker、sqlite 句柄不出现在 contracts 中。

## 4. 核心契约（R1 目标，字段以 `contracts/` 为准）

**ResourceRequest**：`{ gpus, gpuMemGB?, gpuIds?, cpus, memGB, node? }`。Agent 按任务估算后提交；
不满足时排队，而不是失败。

**Lease**：`{ id, runId, node, gpuIds, cpus, memGB, state: active|released }`。
只有确认容器已清理才释放。

**资源可用性**：可用 = 探测到的硬件 − Orbit 活动租约 − 外部占用。外部进程占用显存超过阈值
（默认 1 GiB）的 GPU 视为不可用；外部进程退出后自动变为可用。

**RunSpec**：
```
{ name?, project?(repo path), image | dockerfile, command(argv), resources,
  mounts[{ source | dataset, target, mode: ro|rw }], env, network(default true),
  snapshot(default true when project set), auth?(profile name), tags, parentId? }
```

**Run**：`{ id, spec, state, exitCode?, node, leaseId?, containerId?, code{commit, dirty, diffRef},
createdAt/startedAt/endedAt, cleanup: pending|done|failed, usage{peakGpuMem, peakMem, …} }`

- `state`: `queued → starting → running → succeeded | failed | cancelled | lost`。
- 执行结果（state/exitCode）、清理状态（cleanup）、评测有效性（bench 中）是三个独立字段。

**容器内约定**（skill 告诉 Agent；实验代码直接用环境变量）：

| 路径 / 变量 | 含义 |
| --- | --- |
| `/workspace` | 代码快照（可写副本；原仓库不受影响） |
| `$ORBIT_OUTPUT` = `/orbit/output` | 产物目录，自动归档 |
| `$ORBIT_METRICS` = `/orbit/metrics.jsonl` | 每行一个 JSON：`{"step": 10, "loss": 0.3}`，Web 画曲线 |
| `$ORBIT_RUN_ID` | 当前 Run ID |

**代码快照**：记录 `HEAD` commit、未提交 diff 与未跟踪文件列表；复制 `git ls-files -co --exclude-standard`
的文件到快照目录。数据和权重不进快照，用命名 dataset 只读挂载。

**容器**：GPU 优先用 CDI（`--device nvidia.com/gpu=<UUID>`，检测到 `/etc/cdi` 或 `/var/run/cdi` 中的
NVIDIA spec 时），否则 `--gpus device=<UUID>`；启动后核对 `nvidia-smi -L` 与租约一致。默认以宿主用户
`uid:gid` 运行（产物归属正确），`--root` 例外。每个 Run 的记录目录挂载为 `/orbit`（rw）。

**会话关联**：CLI 提交时识别调用它的 Agent：`ORBIT_AGENT=<harness>[:<id>]` 优先；否则祖先进程中最近的
`claude` / `codex` 决定 harness（Agent 相互嵌套时子进程会继承父 Agent 的环境变量），会话 ID 取
`CLAUDE_CODE_SESSION_ID` / `CODEX_THREAD_ID`；Codex 无 ID 时按 cwd 找最近的会话文件。daemon 读取
`~/.claude/projects/**/<id>.jsonl` 或 `~/.codex/sessions/YYYY/MM/DD/rollout-*-<id>.jsonl`，
归一为 `SessionMessage`（text / thinking / tool_call / tool_result），Web 标出提交该 Run 的那一步。

**失败也要保留证据**：任何终态都先采集日志与 `$ORBIT_OUTPUT`，再清理容器；日志读到 EOF，截断必须标记。

## 5. HTTP API 与 Web

`/api/v1`：`health`、`resources`、`doctor`、`ledger`（资源 + 活动租约 + 排队原因）、`GET/POST runs`、
`runs/:id`、`runs/:id/{cancel,note,wait,events,logs,log.txt,metrics,artifacts,files/*,diff,session}`、
`stream`（SSE，Run 变化推送）、`GET/POST auth`、`DELETE auth/:name`、`POST auth/:name/test`、
`GET/POST notify`、`DELETE notify/:name`、`POST notify/:name/test`。`GET /login?token=&next=` 设置 cookie 后跳转到站内路径（拒绝 `//`、外站）。
`orbit web [id]` 用 token 打开浏览器并定位到 Run。

Web 页面（参考 W&B / Neptune 的实验对比、Modal / E2B 的沙箱运行详情、GitHub 的 diff 视图）：

- **Runs**：按 group 折叠、状态筛选、全文过滤（名称/参数/标签/分支），多选对比，键盘导航。
- **Run 详情**：Overview（生命周期时间线、清理核对、笔记、指标迷你图、日志尾）、Logs（虚拟列表、ANSI、
  搜索、跟随）、Metrics（uPlot，平滑、同步十字线）、Artifacts、Code（相对快照 commit 的 diff）、
  Session（Agent 轨迹，标出提交点）、Events。
- **Compare**：`?ids=` / `?group=`，按 seed 聚合 mean ± std、相对基线的变化、曲线叠加、配置差异。
- **Resources**：GPU 卡片（Orbit 租约 / 外部占用 / 空闲、显存与利用率）、租约与队列。
- **Settings**：容器内 Agent 版本、auth profile（掩码、测试、删除）、通知目标（发测试、删除）、浏览器通知开关。
  Web 不录入密钥：添加 profile / 目标只走 CLI。

## 6. 认证（auth）、harness 与通知

**Auth profile**（`contracts.AuthProfile`，公开字段不含密钥）：

```
{ name, harness: codex | claude-code, kind: login | api-key | relay, baseUrl?, model?,
  env(非密钥附加变量，如 HTTPS_PROXY), hostNetwork, secretHint, createdAt, updatedAt }
```

- 保存在 `~/.orbit/auth.json`（0600，只有 daemon 写），codex 登录态（Codex 的 `auth.json` 内容）也内联在其中。
  API 与 Web 只返回公开字段和掩码提示；密钥只经本机 HTTP 提交一次，CLI 从 stdin 或环境变量读取，不走 argv。
- 注入方式：

| harness / kind | 容器内 |
| --- | --- |
| codex login | `$CODEX_HOME/auth.json` 为 profile 登录态的副本；run 结束后若 token 已刷新则写回 profile |
| codex api-key | `$CODEX_HOME/auth.json` = `{ OPENAI_API_KEY }` |
| codex relay | `$CODEX_HOME/config.toml` 定义 provider（`base_url`、`env_key = ORBIT_RELAY_API_KEY`），密钥经环境变量 |
| claude-code login | `CLAUDE_CODE_OAUTH_TOKEN`（`claude setup-token` 生成的长期 token） |
| claude-code api-key | `ANTHROPIC_API_KEY` |
| claude-code relay | `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` |

- 密钥环境变量通过 0600 的 `--env-file` 传给 `docker run`，启动后删除（`docker inspect` 仍可见，仅限本机
  docker 用户）。run 结束后删除容器内写下的凭据文件；日志写入前按当前所有密钥脱敏（`[redacted]`）。
- `orbit auth test <name>` 用该 profile 提交一个真实的小 Run（`auth-test` 组），让 Agent 回复固定口令并检查日志；
  结果作为 Run 保留。

**Harness**：`RunSpec.auth = <profile>` 时，Orbit 把宿主机上已安装的 Agent CLI 只读挂载进容器
（codex 为静态 musl 二进制，挂到 `/opt/orbit/codex`；Claude Code 原生二进制需 glibc，挂到 `/opt/orbit/claude`），
按镜像的 `PATH` 追加这些目录，并在事件中记录版本。版本固定 = 宿主机当前版本；`orbit doctor` 显示两者版本。
Agent 的 home 放在 `/orbit/agent/{codex,claude}`（`CODEX_HOME`、`CLAUDE_CONFIG_DIR`），会话轨迹随 Run 记录保留。
容器本身就是沙箱：容器内 codex 用 `--dangerously-bypass-approvals-and-sandbox`，claude 用
`--dangerously-skip-permissions`。profile 设置 `hostNetwork` 时 Run 使用宿主网络（例如代理只监听 127.0.0.1）。

**通知**：`~/.orbit/notify.json`（0600）中的目标 `{ name, kind: feishu | dingtalk | wecom | slack | webhook, url, on[] }`，
`on` ⊆ `succeeded | failed | group`。单个 Run（无 group）结束时按状态通知；group 中的 Run 不单独通知，
该 group 不再有排队/运行中的 Run 时发一条汇总（成功/失败计数、失败的 Run 与原因）。失败通知附原因与日志最后几行
（已脱敏）。发送失败只记 daemon 日志，不影响 Run。Web 可开启浏览器通知（页面打开时）。

## 7. 刷榜（bench）

```
AgentProfile = harness + version + model + auth + method bundle (directory)
Benchmark    = tasks + per-task environment + instruction + verifier + aggregation
Trial        = task × AgentProfile × seed → solve Run (Agent inside) + verify Run (separate)
Outcome      = { execution, evaluation: valid|invalid|unknown, score?, issues[], cleanup }
```

- 只有 `evaluation=valid` 的分数进入均分；无效或未知单独列出，不静默计入。
- **适配器两类**：
  1. **Harbor 格式**（首选）：任务目录含 `instruction.md`、`environment/Dockerfile`、`tests/`、`solution/`、
     `task.toml`。Orbit 自己的执行器直接运行这种目录。Harbor 已有的适配器可直接导出任务目录复用。
  2. **原生包装**：benchmark 有不可拆分的原生 runner（如 ASI 的 BenchFlow），以 process 后端运行原 runner，
     Orbit 管资源租约、跟踪其子容器（label/代理）、解析结果。
- **接入验收（任意新 benchmark）**：oracle 满分、空答案零分、抽样与原版结果一致。
- 首批：ASI（原生包装）→ TerminalBench-Science（Harbor 格式）。

## 8. 多节点（R4）

每台机器运行 daemon；Agent 所在节点为主节点，其他节点用 token 加入（Tailscale 或直连）。主节点汇总
资源并放置 Run；代码快照按内容哈希传输并缓存；数据/权重按"名字 → 节点本地路径"登记，调度只选有数据的
节点，不自动搬运。日志与指标回传主节点，大产物留在原节点按需读取。不引入 Ray。

## 9. 预留

- 具身：资源类型可扩展为独占设备（如机械臂），executor 可增加设备后端。现在不写代码。
- 手机监控/对话、Slurm：出现具体需求再设计。

## 10. 路线

| 阶段 | 目标 | 验收 |
| --- | --- | --- |
| R0 | 清理旧实现、TS 骨架、规则与设计 | `pnpm verify` 通过；`orbit resources` 在本机读出真实 GPU/CPU/内存 |
| R1 | 单机日常科研闭环 | Codex 估算资源并提交 3-seed GPU sweep，排队、`orbit wait`、失败留证据；Web 看到 diff、曲线、日志、会话；Codex 与 Claude Code 都走通 |
| R2 | 认证模块与通知 | login / API key / relay 三类 profile 可用于容器内 Codex、Claude Code；完成/失败通知 |
| R3 | 刷榜 | ASI 原生包装、TB-Science Harbor 格式在同一 Run/租约上运行；方法对比页面；新 bench 接入指南 |
| R4 | 多节点 | 一个 Agent 调度两台机器 8 张 GPU |

## 11. 来自 v0（Python 版）的教训

v0 的代码、文档与任务记录保留在标签 `v0-python-final`。

- 控制权放在 infra（冻结 Task、容器 Planner、研究方案审批）导致流程重、不被使用。Agent 主导，Orbit 只执行和记录。
- 科研与 benchmark 各有一套控制器、租约、存储和结果格式，互相看不见资源。只保留一套。
- 失败路径先抛异常后收集产物，丢失证据；日志按固定块读取可能截断。终态先采集、读到 EOF。
- ASI 60 题中 19 题评测链异常仍显示为已评分；原生 timeout 标签与真实终止事件不一致。评测有效性必须独立判定并参与汇总。
- ASI 容器内旧版 Codex CLI 导致模型拒绝；harness 版本必须固定并在 doctor 中检查。
- GPU 映射：Docker `--gpus device=<UUID>` 或 CDI `--device nvidia.com/gpu=<UUID>`，启动后核对实际映射与租约一致。
- 文档与流程记录量接近代码量，拖慢迭代。只保留本文、status 与必要的任务记录。
