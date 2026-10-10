# Orbit

[English](README.md)

Orbit 让 Codex、Claude Code 等编程 Agent 在你的 GPU 机器上安全地跑实验。Agent 负责规划和写代码；
Orbit 在隔离的 Docker 容器里、按 GPU / CPU / 内存租约运行它，并保留事后复盘所需的一切：确切的代码
（commit + 未提交的 diff）、日志、指标、产物，以及提交它的 Agent 会话。你可以通过命令行或本地 Web
界面查看。

> 状态：0.1.0，开发中。单机使用（R0–R2）已验证；刷榜（R3）与多节点调度（R4）已实现，仍在测试。
> 详见 [docs/status.md](docs/status.md) 与设计文档 [docs/design.md](docs/design.md)。

[项目演示稿](docs/ppt/README.md)：在浏览器中打开 `docs/ppt/index.html` 即可离线演示。

## 功能

- **隔离运行**：每个 Run 是一个 Docker 容器（原生 benchmark runner 可用宿主进程），代码快照放在
  `/workspace`，原仓库不会被修改。
- **资源租约与排队**：每个 Run 按需租用 GPU、CPU、内存；放不下的 Run 排队并说明原因。Orbit 之外的进程
  占用也会被计入：被占用的 GPU 不会被分配；其他进程占满 CPU 时，新的 Run 会排队等待。
- **Sweep 与分组**：一条命令提交参数网格；`wait`、`ps` 和 Web 都可以按组操作。
- **可复盘的记录**：commit 与 diff、日志、JSON Lines 指标与曲线、输出文件、事件、笔记，以及发起该 Run
  的 Codex / Claude Code 会话。
- **Web 界面**：Run 列表、Run 详情（概览、日志、指标、产物、diff、会话）、多 Run 对比、资源、设置和
  刷榜页面，由本地 daemon 提供。
- **Agent 凭据**：Codex 与 Claude Code 可以在容器*内*运行，支持 login、API key、中转（relay）三种
  profile；密钥不出现在命令行，日志中自动脱敏。
- **通知**：Run 或分组结束时发送到飞书、钉钉、企业微信、Slack 或通用 webhook。
- **手机上查看**：`orbit feishu init` 扫码即建好飞书机器人，收带指标曲线的结果卡片，随时发 `/gpu`、`/runs` 查看状态。
- **刷榜**：任务 × 方法 × 种子的 job；每个 trial 是一个 solve Run 加上它的验证，只有有效分数计入均值。
  内置 [Harbor](https://github.com/harbor-framework/harbor) 任务格式的读取器（separate / shared verifier、
  docker-compose 服务、collect hooks），[Terminal-Bench-Science](https://github.com/harbor-framework/terminal-bench-science)、
  Terminal-Bench 等 Harbor 数据集都按 Orbit 的资源规则运行；另有 ASI-Bench 与外部适配器。
- **多机**：一台机器把 Run 放到已加入的 worker 上；代码按内容哈希传输，数据集在各节点按名字登记，
  日志与指标回传。不需要 Ray。
- **Agent skill**：给 Claude Code 和 Codex 的 skill，教它们用 `orbit` 估算资源、提交、等待并记录结论。

## 环境要求

- Linux。
- Node.js 24.18 及以上（24.x）。源码开发和 dsh 插件安装需要 pnpm 10。
- Docker，当前用户无需 `sudo` 即可使用（例如加入 `docker` 组）。
- GPU 运行：NVIDIA 驱动，以及 NVIDIA CDI spec 或 NVIDIA Container Toolkit 之一。
- git（用于代码快照）。
- 可选：宿主机上的 `codex` / `claude` CLI（需要在容器内运行 Agent 时）。

## 安装

npm 分发已准备好，首次公开发布尚待完成。发布后，无需源码即可试用：

```bash
npx -y @zjunlp/orbit doctor
```

或者一条命令永久安装 CLI：

```bash
npm install -g @zjunlp/orbit
```

下文示例使用 `orbit`；未全局安装时替换为 `npx -y @zjunlp/orbit` 即可。
包内包含 CLI、daemon 和构建好的 Web 界面，不需要 pnpm、手动构建或软链接。
更新：`npm install -g @zjunlp/orbit@latest && orbit daemon --stop`（下一条命令启动新版 daemon；
运行中的容器不受影响，会被重新接管）。从源码使用见[开发](#开发)。

## 初次使用

```bash
orbit doctor                    # 检查 docker、nvidia-smi、git、node 与 Agent CLI
orbit resources                 # GPU、CPU、内存、磁盘、租约与队列
```

第一条 `orbit` 命令会自动在后台启动 daemon。它只监听 `127.0.0.1:7717`，状态保存在 `~/.orbit`。每个用户各跑自己的
daemon：如果 7717 已被其他用户的 daemon 占用，会自动换一个空闲端口（CLI 通过 `~/.orbit` 找到它）。

在某个 git 仓库里运行一个命令：

```bash
cd ~/my-project
orbit run --image python:3.12-slim -n hello -- python -c 'print("hello from orbit")'
orbit ps -a                     # Run 及其状态
orbit logs <id>                 # 输出
orbit web                       # 打印 Web 界面的登录 URL（加 --open 直接打开浏览器）
```

选项写在 `--` 之前，`--` 之后是要运行的命令。命令在 `/workspace` 中执行，这是当前 git 仓库的副本，
包含未提交的修改和未跟踪（未被忽略）的文件。

要让 Agent 使用 Orbit，安装 skill（见 [Agent 接入](#agent-接入)），然后让它用 Orbit 运行实验即可。

## 使用说明

### 容器内约定

| 路径 / 变量 | 含义 |
| --- | --- |
| `/workspace` | 代码的可写副本（原仓库不受影响） |
| `$ORBIT_OUTPUT`（`/orbit/output`） | 结果写到这里，会被保留并在 Web 中展示 |
| `$ORBIT_METRICS`（`/orbit/metrics.jsonl`） | 每行一个 JSON，如 `{"step": 10, "loss": 0.3}`，Web 中画曲线 |
| `$ORBIT_RUN_ID` | 当前 Run ID |

容器内只能看到租到的 GPU。默认以宿主用户的 `uid:gid` 运行，产物文件归你所有（`--root` 以 root 运行）。

### 运行

```bash
orbit run --image pytorch/pytorch:latest --gpus 1 --mem 32 -n baseline -- python train.py
orbit run --dockerfile docker/Dockerfile --gpus 2 --gpu-mem 40 -- python train.py   # 构建镜像
orbit run --gpus 1 --timeout 120 -w --image ... -- python eval.py   # 等待结束；退出码即结果
```

常用选项：

| 选项 | 含义 |
| --- | --- |
| `--image` / `--dockerfile` | 使用的镜像，或要构建的 Dockerfile（构建上下文为其所在目录） |
| `--gpus`、`--gpu-mem <GB>`、`--gpu-ids` | GPU 数量、每卡最小显存、指定 GPU |
| `--cpus`（默认 4）、`--mem <GB>`（默认 16） | CPU 与内存上限 |
| `-n`、`-g`、`-t KEY=VALUE` | 名称、分组、标签 |
| `-m src:dst[:rw]`、`-d name[:dst[:rw]]` | 挂载宿主路径或已登记的数据集（默认只读） |
| `-e KEY=VALUE` | 环境变量（随 Run 保存，不要放密钥） |
| `--pass-env VAR` | 从 daemon 环境传入变量（用于密钥，值不保存） |
| `--project <dir>`、`--no-project`、`--no-snapshot` | 指定仓库、不使用仓库、只读挂载而不复制 |
| `--no-network`、`--host-network` | 禁用网络，或使用宿主网络 |
| `--timeout <min>` | 超时后停止 |
| `--node <name>` | 指定节点（多机） |
| `-w`、`--json` | 等待结果；输出 JSON |

### Sweep

```bash
orbit sweep --image python:3.12-slim --gpus 1 -g lr -p lr=1e-4,3e-4 -p seed=1,2,3 \
  -- python train.py --lr {lr} --seed {seed}
orbit wait -g lr                # 等整组结束；有失败则退出码为 1
```

命令中的 `{key}` 被替换为每个取值；上例提交 2 × 3 = 6 个 Run，按资源情况排队执行。

### 跟踪与复盘

```bash
orbit ps                        # 活动的 Run；排队的 Run 会显示原因
orbit ps -a -g lr               # 某个分组的全部 Run
orbit show <id>                 # 详情与最新指标
orbit logs <id> -f              # 跟随日志（--tail BYTES 从末尾附近开始）
orbit wait <id>...              # 等待指定 Run
orbit cancel <id>...
orbit rm <id>... | -g <group>   # 永久删除已结束的 Run（需输入 id 或组名确认）
orbit note <id> "lr 3e-4 在 2k 步后发散"   # 记录结论（- 表示从 stdin 读取）
orbit web <id> --open           # 在 Web 中打开该 Run
```

大多数命令支持 `--json`，便于脚本和 Agent 使用。

### Web 界面

`orbit web` 打印一个带 daemon token 的 URL，浏览器打开后以 cookie 登录。页面包括：Run 列表（筛选、
分组、多选）、Run 详情（概览、可搜索的日志、指标曲线、产物预览、代码 diff、Agent 会话）、对比
（多个 Run 的指标）、资源（GPU、租约、队列、worker 节点）、刷榜 job 与对比、设置（doctor、凭据与
通知配置）。按 `?` 查看快捷键。

daemon 只监听 `127.0.0.1`。从其他机器查看时用 SSH 隧道：
`ssh -L 7717:127.0.0.1:7717 gpu-server`，然后在本地打开打印出的 URL（daemon 不在 7717 时，用 `orbit web`
打印的 URL 里的端口）。

### Agent 接入

已安装对应 Agent CLI 后，选择一条命令安装（npm 发布后可用）：

```bash
npx -y @zjunlp/orbit plugin install claude
npx -y @zjunlp/orbit plugin install codex
npx -y @zjunlp/orbit plugin install dsh --profile headless
npx -y @zjunlp/orbit plugin install pi
```

不指定 Agent 时默认安装 Claude Code 插件。重启 Agent 后加载 `orbit` 和 `orbit-bench`；
四个平台共享同一份 skills，未全局安装 `orbit` 时通过 `npx` 调用。dsh 需要 pnpm，并显式指定
带 skills 服务的 profile。支持版本、本地开发、更新和卸载见 [plugin/README.md](plugin/README.md)。

CLI 需要网络权限访问本地 daemon。会话采集与容器内 Agent 目前支持 Codex 和 Claude Code；
dsh/pi 的宿主机插件通过已有 CLI 提交实验，其会话解析与容器内 harness 尚未实现。MCP 仍未实现。

### 在 Run 中运行 Agent（凭据 profile）

Run 可以在容器内执行 Codex 或 Claude Code（用于 Agent 实验和刷榜）。Orbit 挂载宿主机上安装的 CLI，
并按 profile 注入凭据：

```bash
orbit auth add codex --harness codex --kind login     # 在私有目录中执行 `codex login --device-auth`
orbit auth add gpt --harness codex --kind api-key --key-env OPENAI_API_KEY
orbit auth add claude --harness claude-code --kind login --key-stdin    # 粘贴 `claude setup-token` 生成的 token
orbit auth add relay --harness claude-code --kind relay --base-url https://relay.example --key-env RELAY_KEY
orbit auth add claude --harness claude-code --kind relay --from-env    # 从环境变量 / Claude 设置读取 key、URL、模型
orbit auth list
orbit auth test claude          # 提交一个真实的小 Run：Agent 必须正确回答
orbit run --auth claude --image python:3.12-slim -- claude -p --dangerously-skip-permissions "…"
```

密钥只从 stdin、环境变量或文件读取，不经过命令行参数。profile 保存在 `~/.orbit/auth.json`（权限 0600），
Run 日志中的密钥会被脱敏。Agent 需要访问 `127.0.0.1` 上的代理时，给 profile 加 `--host-network`。

### 通知

```bash
orbit notify add team --kind feishu --url-env FEISHU_HOOK --on failed,group
orbit notify test team
orbit notify list
```

类型：`feishu`、`dingtalk`、`wecom`、`slack`、`webhook`。事件：`succeeded`、`failed`、`group`（分组
全部结束时发一条汇总）。失败消息附带原因和日志最后几行。

### 手机上查看（飞书机器人）

```bash
orbit feishu init phone       # 终端打印二维码：用手机飞书扫码并确认
```

扫码会新建一个飞书应用（机器人能力、消息权限、接收消息事件已预填），并自动与扫码人配对，之后：

- Run 或分组结束时，机器人发来结果卡片：状态、资源与实测峰值、指标曲线（如 loss），失败时附日志尾。
- 随时私聊机器人（群里需 @ 它）：`/gpu` 看每张卡的显存、利用率和占用者，以及 CPU、内存、队列；`/runs` 看最近的
  Run；`/show <run id>` 看某个 Run 的卡片。命令都是只读的。

daemon 主动向飞书建立长连接，不需要公网地址，daemon 仍只监听本机。若 `init` 提示长连接或测试卡片失败，按它
给出的后台页面修改（订阅方式选「长连接」、开通权限、发布版本），再运行 `orbit feishu check phone` 重连并测试。

- 可以绑定多个机器人（名字不同即可），但同一个应用只能绑一次，也不要绑到两台机器的 daemon 上（飞书每个事件
  只投递给其中一条连接）。同时配对多个机器人会收到重复的通知。
- 已有的应用：`orbit notify add phone --kind feishu-app --app-id cli_… --secret-stdin`。其他人私聊机器人会收到
  配对码，在本机运行它回复的 `orbit notify pair phone <code>` 后才能使用；未配对的人看不到任何数据。
- `orbit notify list` 查看配对人数和连接状态，`orbit notify rm phone` 删除。

### 刷榜

```bash
orbit bench add tbs ../terminal-bench-science --adapter harbor
# 发布在 Harbor Hub 上的数据集：用 Harbor 自己的 CLI 下载，再登记目录
harbor download terminal-bench/terminal-bench@latest -o ~/datasets
orbit bench add tb ~/datasets/terminal-bench --adapter harbor
orbit bench add asi ../ASI-Bench --adapter asi -c python=/path/to/venv/bin/python --pass-env JUDGE_KEY
orbit bench add rcb ../ResearchClawBench --adapter ./examples/bench-adapters/researchclawbench/adapter.py \
  --pass-env OPENAI_API_KEY --pass-env OPENAI_BASE_URL
orbit bench tasks tbs           # 任务列表，以及不支持的任务的原因
orbit bench run tbs -t symbolic-regression -m oracle -m empty \
  -m gpt=codex,auth=gpt,model=gpt-5,effort=high --seeds 3 -n first-try
orbit bench jobs
orbit bench show <job>
orbit bench compare <job>...    # 按任务对比；paired 均值只用所有方法都有效的任务
orbit bench usage <job>...      # 每个任务实测的内存 / CPU / 显存峰值与建议资源
orbit bench cancel <job>
orbit bench rm-job <job>        # 删除已结束的 job 及其 trial 和 Run（需输入 job id 确认）
```

方法格式为 `name=agent[,auth=P,model=M,effort=E,bundle=DIR]`，agent 可为 `codex`、`claude-code`、
`oracle`（参考解）或 `empty`（不提交任何内容，用于检查 verifier 给 0 分）。每个 trial 分别记录执行结果
（solve Run 如何结束）、评测有效性（`valid` / `invalid` / `unknown`）与清理状态；只有有效分数计入统计。
Web 的 **Bench** 页面展示 job、任务 × 方法矩阵和跨 job 对比。`--pass-env` 传入的评审密钥只给 verify
Run。每个任务的 solve 资源（GPU、内存、CPU、超时）可由 `orbit bench add --resources` 指定的 JSON 文件给出；
每个 Run 都记录实测峰值，solve 因内存不足被杀时该 trial 记为 invalid，而不是 0 分。其他 benchmark 只需一个说小型 JSON 协议的适配器可执行文件，不用重新构建 Orbit，见
[docs/guides/bench-adapter.md](docs/guides/bench-adapter.md)。

ASI 的 Agent 运行需要完整源码 checkout，支持 `--fail-on-agent-error` 且已修复沙箱超时判定。
Orbit 在启动 Agent 前检查所选 Codex/Claude adapter；发现把后台超时警告当成执行失败的已知旧版逻辑时，
明确提示升级。需要更新的是**注册的 ASI 源码目录**（包括冻结快照），仅升级 Orbit 不能修复该目录里的代码。
原生 attempt 状态与评分 valid 分开显示，见 [ASI 版本兼容](docs/guides/bench-adapter.md#asi-bench-版本兼容)。

### 多机

每台机器都运行 Orbit。Agent 所在的机器（主节点）把 Run 放到已加入的 worker 上，优先使用本机资源。

```bash
# 在 worker 上（例如 Tailscale 地址 100.64.0.12）；防火墙需允许主节点访问 7718
orbit node expose --listen 100.64.0.12:7718
orbit node token                                # 复制打印出的 token
# 在主节点上：会提示输入 token（粘贴，不回显，回车结束）
orbit node add http://100.64.0.12:7718
orbit node ls
orbit data add imagenet /data/imagenet          # 在每台有这份数据的机器上执行
orbit run -d imagenet --gpus 1 --image pytorch/pytorch -- python train.py
```

代码快照按内容哈希只传一次；数据集从不复制；日志与指标同步到主节点；产物留在 worker，经主节点读取。
集群协议是带 token 的明文 HTTP：请使用 Tailscale、内网或 SSH 隧道，不要暴露到公网。
详见 [docs/guides/multi-node.md](docs/guides/multi-node.md)。

## 配置与文件

| 项 | 默认值 | 覆盖方式 |
| --- | --- | --- |
| 状态目录（数据库、profile、配置） | `~/.orbit` | `ORBIT_HOME` |
| 数据目录（Run 目录、bench staging、代码 bundle） | 同状态目录 | `orbit config data <dir>` 或 `ORBIT_DATA` |
| daemon 端口（`127.0.0.1`） | 7717，被占用时换空闲端口 | `ORBIT_PORT` 或 `orbit daemon --port`（此时端口被占用直接报错） |
| 节点名 | 主机名 | `ORBIT_NODE` |
| Orbit 可用的 GPU | 全部 | `ORBIT_GPUS=0,1` |
| daemon 地址与 token | `~/.orbit/daemon.json`（0600） | |

Run 数据可能达到数百 GB。系统盘小的机器，在第一次运行前把它放到大盘：`orbit config data /data/$USER/orbit && orbit daemon --stop`。
`orbit doctor` 会在数据目录或 Docker 数据目录位于系统盘或空间不足时提示。文件夹用于整理 Run 与 bench job，不移动文件：
`orbit run --folder rcb/noskills`、`orbit mv <id...> rcb/archive`、`orbit folders`；需要实体副本时 `orbit export rcb /path/to/copy`。

daemon 是 Orbit 状态的唯一写者；CLI、Web 和 Agent 都通过它的本地 HTTP API 访问。`orbit daemon --stop`
停止 daemon，运行中的容器继续执行，daemon 重启后重新接管。`orbit daemon` 在前台运行。

## 常见问题

| 现象 | 检查 |
| --- | --- |
| `orbit doctor` 报 docker 错误 | Docker 在运行，且当前用户不加 sudo 能执行 `docker ps` |
| GPU Run 无法启动 | `nvidia-smi` 正常；已安装 NVIDIA Container Toolkit 或 CDI spec |
| Run 一直 `queued` | `orbit ps` 会显示原因（GPU 被占用、CPU 被其他进程占满、内存不足、指定节点离线等） |
| Agent 连不上 Orbit | `orbit` 在其 `PATH` 上；Codex 沙箱已允许网络 |
| 快照过大 | 把数据和权重加入 `.gitignore`，用 `-m` 或 `orbit data` 挂载 |

## 开发

需要 pnpm 10（`corepack enable`）。包验证与发布见[发布指南](docs/guides/releasing.md)。

```bash
git clone https://github.com/zjunlp/Orbit.git
cd Orbit
pnpm install
pnpm build
pnpm orbit doctor
pnpm --filter @zjunlp/orbit-web dev   # Vite 开发服务器；/api 代理到 daemon
pnpm orbit <args>                     # 从源码运行 CLI
pnpm verify                           # lint + 类型检查 + 模块边界 + 测试 + 构建
```

```
packages/orbit/   `@zjunlp/orbit` 包（CLI `orbit`、daemon、各模块）
packages/web/     Web 界面（React + Vite，由 daemon 提供）
plugin/           给 Codex / Claude Code 的 Orbit skill
scripts/          仓库检查（模块边界）
docs/             design.md、status.md、tasks/、guides/、ppt/
```

贡献者与编程 Agent 请先阅读 [AGENTS.md](AGENTS.md)。

## 致谢

Orbit 的 `harbor` 适配器读取由 Terminal-Bench 团队的 [Harbor](https://github.com/harbor-framework/harbor)（Apache-2.0）
定义的任务格式；它是独立实现，不是 Harbor 官方运行器，也未获其作者背书。只有经过对照的部分，Orbit 的分数才与
Harbor 的可比；对照情况见 `docs/tasks/`。

## 许可

[MIT](LICENSE) © 2026 ZJUNLP
