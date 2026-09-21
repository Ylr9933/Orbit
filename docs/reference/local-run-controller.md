# 本机 Run 控制服务

状态：D 批实现，G2 任务分支增加单机 GPU 白名单；单节点、单管理员、单活跃 Run。此文描述当前命令，不代表 main 已合并或服务器已常驻部署。

## 可以完成什么

已采用的研究实验经 C 批编译后，使用冻结 Task ID 和 revision 提交。Controller 在后台调用现有
`LocalRunService`，分配 CPU/内存、启动容器内 Codex、收集输出、保存 Records、删除容器并释放资源。
提交 CLI 返回后实验继续。科研任务可以不设置 evaluator；指标作为普通产物保存，不自动等同于 benchmark 分数。

当前公开入口接受本状态目录登记的编译 Task，支持 Codex 0.154.0。其他 Agent 适配仍可通过既有 Python API 使用；
Controller 的容器凭据流程暂未泛化到 Claude Code / DSH。没有自动安装、自动生成镜像、队列、Ray 或 Web 运行按钮。冻结 Task 的单机 GPU 请求可通过 `controller serve --gpu-uuid` 授权；主机诊断与限制见[GPU 操作说明](../operations/gpu-local.md)。
宿主机 Agent 通过 MCP 控制长期科研 Job 的另一入口见[H 批参考](host-research-mcp.md)；两条路径共用 Controller 和资源准入。

## 准备镜像和账号

前提：本机 Linux、可访问的本地 Unix Docker daemon、Python 基础镜像、已安装并登录的 Codex。

```bash
uv run --locked agent-infra agent doctor codex
uv run --locked python scripts/dev/build_codex_research_image.py
```

构建脚本默认使用本机已安装的官方 Codex 0.154.0 原生软件包和本地 `python:3.12-slim`，不读取账号目录。
它校验 CLI 版本，复制软件包到临时构建上下文，输出二进制摘要和基础镜像 ID；构建器可能查询镜像元数据。
如无法定位 npm 内的软件包，用 `--package-dir` 指定包含 `bin/codex` 的 vendor 目录。
这不是通用任务环境生成器：示例镜像只有 Python 标准库和 Codex，任务需要其他依赖时须显式准备镜像。

任务的 execution YAML 应声明该镜像。预检要求 `agent-infra.provider=codex` 和
`agent-infra.codex.version=0.154.0` 镜像标签；标签是兼容性声明，真实可执行性仍需运行验证。
Run 固定预检得到的镜像 ID，不随同名标签后续变化。

完整小样例见 [CPU 统计实验](../../examples/research/cpu-statistics/README.md)。

若宿主机使用 HTTP 代理，Controller 默认读取 `HTTPS_PROXY` / `https_proxy`。
对于只监听 localhost 的代理，会建立有随机认证、只允许 `chatgpt.com:443` 与 `api.openai.com:443`
CONNECT 的 Docker bridge 转发；不会修改原代理，也不会将其开放为无认证通用代理。
可以用 `controller serve --model-proxy direct` 禁用，或指定 `--model-proxy http://host:port`。
当前不支持 SOCKS、带账号密码的上游代理、自定义模型服务域名或企业 CA 自动复制。
代理认证只保留在内存和任务进程环境，普通 Records 只记环境变量名称。首次环境连通性仍需实测。

## 启动和使用

终端一启动长期服务：

```bash
agent-infra controller serve --state-dir /absolute/state --cpu 1 --memory-gib 2 --port 8766
```

`--cpu` 和 `--memory-gib` 是管理员允许本服务分配的总容量，不会自动占满宿主机。`--gpu-uuid GPU-...` 可重复指定；缺省不授权 GPU，仅适用于冻结 Task 的容器执行。
同一 OS 用户的所有状态目录共享一个主机锁；第二个 Controller 无法同时启动。
Ctrl-C / SIGTERM 会请求取消并等待清理，不能把关闭服务当作让实验继续运行的操作。
需要脱离终端时使用 tmux、nohup 或用户级服务管理器；提交客户端与服务是两个独立进程。

终端二提交已经编译的 Task（将下面标记替换为 `project compile` 的实际输出）：

```bash
agent-infra run preflight TASK_ID --task-revision TASK_REVISION \
  --model gpt-5.6-sol --reasoning-effort low --network --timeout 180 --state-dir /absolute/state

agent-infra run submit TASK_ID --task-revision TASK_REVISION \
  --model gpt-5.6-sol --reasoning-effort low --network --timeout 180 \
  --operation-id experiment-pilot-1 --state-dir /absolute/state

agent-infra run status RUN_ID --state-dir /absolute/state
agent-infra run list --project-id PROJECT_ID --state-dir /absolute/state
agent-infra run cancel RUN_ID --state-dir /absolute/state
```

所有子命令的 `--state-dir` 必须相同；也可统一设置 `AGENT_INFRA_STATE_DIR`。
必须显式选择模型和网络权限；`--timeout` 限制本次求解进程时长，不是 token/费用硬预算。
预检不创建容器、不分配 Lease；动态空闲量在执行时重新检查。
资源不足或 Controller 忙时立即报告原因，没有自动排队。稍后重试不会自动扩大资源。

提交必须提供 `--operation-id`：断网重试使用相同 ID 和参数，返回原 Run；同 ID 不同参数报冲突。
想重新做同一实验，应使用新 ID，得到独立 Run/Attempt。Run 超时、取消或重启中断后也不会自动重跑。

`cancel_requested=true` 仅表示取消意图。确认结束要同时检查 `state`、`result.status`、
`cleanup_complete` 和 `lease_released`；启动前取消可能没有 Lease，此时释放字段为 false。
Run 原始结果与恢复过程分别保留，不能仅凭收到 HTTP 成功响应认定实验成功。

## 查看和取回结果

```bash
agent-infra run events RUN_ID --state-dir /absolute/state
agent-infra run trajectory RUN_ID --state-dir /absolute/state
agent-infra run artifacts RUN_ID --state-dir /absolute/state
agent-infra run artifact RUN_ID ARTIFACT_ID --state-dir /absolute/state
agent-infra run artifact RUN_ID ARTIFACT_ID --member artifacts/metrics.json \
  --output ./metrics.json --state-dir /absolute/state
agent-infra project research context PROJECT_ID --state-dir /absolute/state
```

先列出 Artifact 中的真实成员，再指定 `--member`。下载单文件上限 16 MiB；`--output` 是客户端路径，
拒绝覆盖已有文件。服务器只从 Records 已登记的 Artifact/Blob 读取，不接受宿主机任意文件路径，
拒绝跨 Run 的 Artifact、凭据类和私有评测类内容。更大文件仍可由本机管理员使用 Records 存储接口导出。
容器与运行工作区被删除后，Records 内独立保存的产物仍存在。

events 支持 `--cursor` 翻页。原生 Agent 流在运行时保存，统一 Agent 轨迹目前在进程结束时解析；
这不是实时聊天推流。进程被 SIGKILL 的窗口可能留下不完整轨迹，恢复明确标记 partial，不伪造完成事件。
研究 context 返回最近 20 条 Run 引用；更多结果用 `run list --limit ... --offset ...`。

## HTTP 与本机认证

服务仅绑定 `127.0.0.1`，每次启动生成随机 bearer token，写入权限受限的
`<state>/controller/endpoint.json`。CLI 自动读取，不把 token 放到命令行或日志。
不支持公开网络、多用户身份隔离或将本机管理 token 提供给容器内 Agent。

| 方法 / 路径 | 用途 |
| --- | --- |
| `GET /api/v1/health` | 服务健康与隔离状态；运行是否空闲另由预检/提交判断 |
| `POST /api/v1/runs/preflight` | Task / 模型 / 网络 / 超时预检 |
| `POST /api/v1/runs` | 同上字段加 `operation_id`，持久提交 |
| `GET /api/v1/runs?project_id=...&limit=100&offset=0` | 历史列表 |
| `GET /api/v1/runs/{run_id}` | 控制意图和 Records Attempt 状态 |
| `POST /api/v1/runs/{run_id}/cancel` | 幂等记录取消意图 |
| `GET /api/v1/runs/{run_id}/events?cursor=...` | 分页事件 |
| `GET /api/v1/runs/{run_id}/trajectory` | 统一轨迹 |
| `GET /api/v1/runs/{run_id}/artifacts` | 可读取产物列表 |
| `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}?member=...` | 成员目录或单文件 base64 内容 |

提交 JSON 字段为 `task_id`、`task_revision`、`model`、`provider`（默认 codex）、
`timeout_seconds`（默认 600，上限 86400）、`network`（默认 false）、`reasoning_effort`（可省略）。
未知字段被拒绝；POST body 上限 64 KiB。身份不符返回 401，Host 不符 403，缺失记录 404，
幂等冲突/忙/资源不足等返回 409，参数错误 400，后端不可用 503。

故障恢复与内部结构见[维护说明](../implementation/local-run-controller.md)。

## E 批验证结果

冻结 Task 的 `environment` 可附带 `lock_id`，同时 `image` 必须等于该锁的固定 image ID。
提交时检查当前提案、有效期、项目及 Codex 层；不会把过期或失败 smoke 当成 ready。
完整配置见[环境准备指南](environment-preparation.md)。没有 `lock_id` 的原手工镜像路径保留兼容。
