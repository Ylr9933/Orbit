# 宿主机科研：长期环境、后台 Job 与 MCP

状态：H 批实现；单机、单管理员、CPU、已有 Python 3 镜像。真实验收范围见
[任务记录](../changes/20260920-host-research-mcp-a81f2c.md)。任务分支实现不等于已经合并或常驻部署。

## 适合什么工作

在宿主机与 Codex 讨论研究目标，通过 MCP 把代码写入隔离 Docker，启动实验、查看日志和指标，
调整参数后在同一个环境再运行。Agent/MCP 退出不影响 Job；重新连接相同项目即可继续查询和控制。
现有 D 批“冻结 Task → 容器内 Codex → 收集结果”入口继续保留。

一个研究 Run 对应一个长期环境；其中可以串行运行多个 Job。要比较独立实验、使用不同资源或重新
获得干净工作区，应结束旧环境、创建新 Run。H 路径可直接从已初始化项目开始，不要求先编译 Task；
这表示交互式研究执行，不代表自动采用或确认了某个实验方案。

## 前提和启动

安装项目及锁定依赖，确保本机 Docker 可用、已有包含 `python3` 的镜像。
镜像不能声明隐式 volumes；镜像 ID 在创建前解析固定。科研容器不安装 Agent、没有账号副本、不开网络。
需要 NumPy/PyTorch 等依赖时，由用户预先准备镜像，当前不会自动安装。

```bash
uv sync --locked
uv run --locked agent-infra init /absolute/research/demo \
  --goal '比较两个学习率对线性回归收敛的影响' --state-dir /absolute/infra-state

# 独立终端；可用 tmux 或用户级服务维持运行。
uv run --locked agent-infra controller serve \
  --state-dir /absolute/infra-state --cpu 1 --memory-gib 2 --port 8766
```

保存 init 返回的 `project_id`。所有入口使用同一 `--state-dir`。Controller 的 CPU/内存参数是
管理员允许分配的总上限，环境申请不能超过该上限，资源不足明确拒绝，不隐式扩容或排队。
当前 Controller 同时只允许一个长期研究环境或一个 D 批 Run。

## 接入 Codex

MCP 的实际启动命令如下，可供支持 stdio 的 Agent 客户端配置：

```bash
/absolute/infra/.venv/bin/agent-infra mcp \
  --state-dir /absolute/infra-state --project-id PROJECT_ID --session-id SESSION_ID
```

`SESSION_ID` 是此次外部会话的关联标识，自行选择一个稳定名称；重连可以沿用它，新会话使用新名称。
不要把登录 token 放进这个字段。工具 schema 不允许 Agent 切换绑定项目。

Codex 的 TOML 配置片段（替换绝对路径和 ID 后放入你选择的配置；平台不会自动修改全局配置）：

```toml
[mcp_servers.research]
command = "/absolute/infra/.venv/bin/agent-infra"
args = ["mcp", "--state-dir", "/absolute/infra-state", "--project-id", "PROJECT_ID", "--session-id", "SESSION_ID"]
```

交互使用时按客户端提示批准工具。若使用 `codex exec` 且审批策略为 `never`，必须在已授权
此次执行范围后显式设置 `mcp_servers.research.default_tools_approval_mode="approve"`，否则工具会被
拒绝；可用单次 `-c` 覆盖，仅作用于这个 MCP，不必放宽宿主机 Shell 权限。

配置机制参见 [Codex 官方 MCP 文档](https://developers.openai.com/codex/mcp/)；本项目使用
[官方 Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.26.0)，固定版本 `1.26.0`。
其他支持 stdio MCP 的客户端可复用这条命令；真实模型验收以任务记录中的客户端为准。

可给 Agent 的提示：

> 先读取项目 context。使用已准备的 python:3.12-slim 镜像，最多 1 CPU、2 GiB，不联网。
> 在 Docker 内编写一个小型线性回归训练程序，先试一个学习率，检查指标后调整学习率再跑一次。
> 使用 MCP 的后台 Job，不在宿主机训练。归档两轮指标和报告，最后结束环境，确认清理和资源释放。

## 工具与 CLI

| MCP 工具 | 对应 CLI 子命令 | 作用 |
| --- | --- | --- |
| `project_context` | `research context` | 原始目标、研究方案、运行关联 |
| `environment_open/status/close` | `research open/status/close` | 申请环境、查看所有 Job、结束并归档 |
| `job_start/logs/stop` | `research start/logs/stop` | 后台命令、增量日志、停止进程组 |
| `workspace_read/write/list` | `research read/write/list` | 容器工作区内文件操作 |
| `artifact_save` | `research archive` | 保存单文件快照到 Records |
| `artifacts_list/artifact_read` | `research artifacts/artifact` | 容器删除后的产物读取 |
| None | `research events/trajectory/import-trace` | 查看统一轨迹、显式导入宿主机 Agent 原始流 |

CLI 都需要 `--project-id`，可指定 `--session-id`（默认 `cli`）。有副作用的命令必须带
`--operation-id`：网络重试复用同一个 ID 和相同参数，新操作使用新 ID。
幂等键按项目和会话划分；不确定的中断操作不会自动重放，需先查看 context/status/jobs。
重试创建环境可能返回原创建回执；当前状态以 `status` 为准。

```bash
export AGENT_INFRA_STATE_DIR=/absolute/infra-state
agent-infra research open --project-id PROJECT_ID --operation-id env-1 \
  --image python:3.12-slim --cpu 1 --memory-gib 2

# 使用 open 返回的 run_id；先把本地脚本复制到容器工作区。
agent-infra research write RUN_ID code/train.py --project-id PROJECT_ID \
  --operation-id code-1 --file ./train.py

# --argv 必须放在最后；其后全部是容器命令的参数，不再解析平台参数。
agent-infra research start RUN_ID --project-id PROJECT_ID \
  --operation-id train-1 --timeout 600 --argv python3 code/train.py --lr 0.02
agent-infra research logs RUN_ID JOB_ID --project-id PROJECT_ID --cursor 0
agent-infra research status RUN_ID --project-id PROJECT_ID
agent-infra research read RUN_ID metrics.json --project-id PROJECT_ID
agent-infra research archive RUN_ID metrics.json --project-id PROJECT_ID --operation-id metrics-1
agent-infra research close RUN_ID --project-id PROJECT_ID --operation-id close-1
agent-infra research artifacts RUN_ID --project-id PROJECT_ID
```

Job 状态包括 `accepted/running/completed/failed/cancelled/timed_out/interrupted/rejected`。
成功退出不等于科学结论正确。停止 Job 保留环境及资源；结束环境才清理和释放。
请检查 close 返回的 `cleanup_complete`、`lease_released` 和 `archive_complete`，不要只看 HTTP 成功。
工作区不合规或超过归档限额时可能已经清理容器并释放资源，但 `archive_complete=false`；状态目录
保留工作区供管理员排查。关闭 Controller 会结束环境，关闭 MCP 或提交命令不会。

## 文件、日志和轨迹

- 工作区为 `/workspace`，文件路径为相对路径。拒绝绝对路径、`..`、符号链接和特殊文件；
  文件操作在容器内使用目录描述符，不接受宿主机任意路径。项目目录不会整体挂入容器。
- 文件写入为 UTF-8、每次最多 32 KiB；读取每页 64 KiB，用 `next_offset` 继续；目录最多 200 项。
  当前不提供大型数据上传或宿主机目录自动同步，大数据场景需要后续材料挂载接口。
- 每个 Job 的 stdout/stderr 合并保存，最多 8 MiB，超过后仍持续排空管道并标记 truncated。
  每次日志读取最多 64 KiB，游标是字节偏移。环境最多 128 个 Job；下一组实验新建环境。
- Controller 主动采集日志，完成后封存为 Records Blob；客户端无需持续轮询。
  Controller 崩溃窗口未采集内容明确标记 partial，不伪造完整轨迹。
- 单文件 artifact 最多 16 MiB；环境结束时冻结整个工作区，沿用现有 1 GiB 归档上限。
  运行中保存 artifact 应先停止相关写入；只有结束环境后的工作区归档代表冻结提交。
- 项目、外部 session、Run、Job、工具调用关联保存在事件中；完整调用参数/响应用 Blob 引用保存。
  平台工具轨迹不等于捕获了宿主机 Agent 的全部活动。

若显式捕获了 `codex exec --json` 等原始 JSONL，可导入所选会话：

```bash
agent-infra research import-trace RUN_ID --project-id PROJECT_ID --session-id SESSION_ID \
  --operation-id import-1 --provider codex --file ./selected-session.jsonl
```

仅读取明确指定的文件，不扫描个人会话目录。复用现有 Codex/Claude Code/DSH normalizer，保留原始
内容，按来源摘要与行号去重。输入上限 16 MiB、单行上限 32 KiB；未知原生事件保留而不猜测。
导入仍标记 partial：没有证明该文件覆盖全部宿主机行为；provider 不同格式的覆盖程度不同。

## 归档文件的可读视图

状态：随 [artifact-readable-views 修复](../changes/20260921-artifact-readable-views-a7c9e2.md)
交付；需要 Controller 和 MCP 同时更新，任务分支不代表已部署。底层 Records 内容与索引格式不变。

`artifact_read(run_id, artifact_id, member=None, format="auto", offset=0, limit=16384)`
用于读取已归档产物；不传 member 仍列出成员。路径必须精确匹配归档清单，不接受宿主机路径。
以下格式也适用于 `research artifact --format ... --offset ... --limit ...`：

| format | 行为 |
| --- | --- |
| `auto`（默认） | UTF-8 文本返回 `text`；图片/二进制先返回类型、大小、摘要和引用；MCP 将小图片转为原生图片内容 |
| `text` | 显式要求 UTF-8 文本；遇到非法编码、二进制控制字符或字符中间的 offset 时明确报错，不替换原文 |
| `base64` | 返回这一页原始字节的 `content_base64`，用于兼容或按需读取二进制；不自动返回整份大文件 |
| `metadata` | 只返回元信息和引用，不内联文本或图片 |

文本范围以**字节**计数：默认 16 KiB，每页 4–65536 字节。返回 `offset`、`bytes_read`、
`next_offset`、`eof`、`truncated`。UTF-8 页尾不拆开字符；下一次必须使用返回的 `next_offset`，
不要自己加 limit。`next_offset=null` 表示末尾；`truncated=true` 表示本页后还有内容，
不是原始文件丢失。空文件返回空 text 与 eof=true。

例如默认读取指标：

```json
{"run_id":"RUN_ID","artifact_id":"ARTIFACT_ID","member":"outputs/metrics.json"}
```

结果包含 `text: "{\"loss\":0.1}"`，不会再为普通 JSON 返回 Base64。保留 JSON 原文作为文本，
不同时复制一份解析后的大对象。CSV、Markdown、代码、日志采用同样规则。
自动判断基于有界内容采样与类型：不可信/非 UTF-8 页回退为元信息并给出原因，
用户可显式读取 Base64；已知权重/压缩格式不会因为部分字节恰好是文本就被自动展开。

```bash
agent-infra research artifact RUN_ID ARTIFACT_ID --project-id PROJECT_ID \
  --member outputs/metrics.json

# 分页：下一页把 offset 替换为上一次返回的 next_offset。
agent-infra research artifact RUN_ID ARTIFACT_ID --project-id PROJECT_ID \
  --member outputs/loss.csv --format text --offset 0 --limit 8192

# 明确需要原始字节时读取一页。
agent-infra research artifact RUN_ID ARTIFACT_ID --project-id PROJECT_ID \
  --member outputs/model.bin --format base64 --limit 65536
```

MCP 的 PNG/JPEG/WebP 在不超过 1 MiB 且从头读取时返回标准 `ImageContent`；图片二进制仍按
MCP 协议编码，但不会放在普通 JSON 文本里让模型自行解码。较大图片、GIF 和其他二进制返回
`ResourceLink`。资源 URI 的形式为 `agent-infra://artifacts/<type>/<run>/<artifact>/<member>`，
各路径字段按 URI 编码；直接使用工具给出的 URI，通过同一 MCP 的 `resources/read` 获取原始字节。
每次资源读取仍校验项目、Run、可见性和清单成员，资源链接不授予额外权限。

元信息中的 `download.controller_path` 是当前 Controller 上的相对 HTTP API 路径，
需要已有管理员认证，并返回兼容的 Base64 JSON；它不是公网 URL、宿主机路径或带凭据的分享链接。
整文件下载与 MCP resource 读取仍限 16 MiB，超限时 `download.available=false`，可通过显式
Base64 分页读取。`resource_uri` 用于定位，不表示大文件能一次加载到模型上下文。
既有 `run artifact --member ... --output ...` 和 Web 下载行为不变，不会误把第一页当作完整文件。

这是归档产物接口的更新；运行中 `workspace_read` 和 `job_logs` 的现有传输字段未在本轮修改。
MCP 客户端的图片显示、资源交互取决于其实现；CLI 图片默认只显示元信息，不输出大段图片 Base64。
采用标准 [MCP 工具内容类型](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
和 [资源读取](https://modelcontextprotocol.io/specification/2025-11-25/server/resources)，
已用锁定的 Python SDK 检验协议响应，不等于已做真实模型视觉验收。

升级时先结束并归档活动实验，再按原参数重启 Controller、重新连接 MCP，以加载新代码和工具 schema。
不要为了更新读取接口中断尚未结束的训练。新客户端遇到仍运行旧代码的 Controller 会明确要求重启，
不静默恢复为向 Agent 展示 Base64。只更新源码不会替换已运行 Python 进程里的代码。

## 重启与范围

沿用 D04：Controller 重启先按所有权日志清理自有容器，再把未完成 Run/Job 标为 interrupted，
不自动重新执行命令或恢复训练内存。已采集日志与 Records 产物可继续读取；同幂等键不会重复启动。
只在已确认容器清理后重新开放容量，无法确认则保留隔离状态。

这是同一可信 OS 用户的科研服务；项目绑定防止工具误操作其他项目，不替代多用户安全边界。
容器内监督进程和科研命令共享 UID，不承诺抵抗恶意命令破坏监督进程或逃离其进程组；结束环境会
删除整个容器。当前无 GPU 准入、网络开关、PTY/SSH、队列、自动构建、磁盘硬配额、多节点或 Web 控制接入。

## E 批环境准备接入

同一 MCP 另提供六个环境准备工具；`environment_open` 可传 `environment_lock`，
CLI 对应 `research open --environment-lock`。验证、依赖提案、有限修复与兼容边界见
[环境准备指南](environment-preparation.md)。原直接 `image` 路径仍可用。
