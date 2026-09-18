# Project 初始化：命令与使用说明

状态：A00–A07 已实现，适用于 Agent Infra 0.1.0 的本地 Linux CLI。
本页描述项目骨架、持久元数据和恢复；研究规划见[独立说明](research-planning.md)，Task 编译与目录重绑定见[C 批命令](experiment-compilation.md)。Docker 启动与 Web 关联仍在后续阶段。
设计取舍见 [ADR](../adr/20260918-project-initialization.md)，验收见[任务记录](../changes/20260918-project-init-72a94b.md)。

## 1. 最直接的用法

在仓库中先执行 `uv sync --locked`，然后运行：

```bash
uv run --locked agent-infra init ./position-encoding \
  --name "位置编码研究" \
  --goal "比较不同位置编码在长上下文任务中的效果，先用小规模实验验证。"
```

目标目录必须尚不存在，父目录必须已存在。`--name` 是显示名称，显式指定目录时不会改变路径。
命令直接创建项目，不调用模型、不启动 Docker、不安装研究依赖，也不自动执行 Git 操作。
安装 wheel 后可从其他目录直接执行 `agent-infra`，无需 `uv run --locked` 前缀。

也可以只给名称，让程序生成目录名：

```bash
uv run --locked agent-infra init --name position-encoding --goal "研究位置编码"
```

或者只给目标，让程序生成 `project-<标识>` 目录：

```bash
uv run --locked agent-infra init --goal "研究位置编码"
```

这一步的命名由参数和代码确定，不调用 Agent 猜测研究主题。Agent 可以先和用户商定名称，再调用同一个命令。
默认在当前目录创建；指定 `--root /existing/research` 可换到已有研究根目录。
使用 `--root` 时目标必须位于其内部；也可以通过 `AGENT_INFRA_PROJECTS_DIR` 设置这个默认根目录。
相对 `directory` 按该根目录解释，绝对路径保持不变并接受边界校验。

## 2. 会得到什么

```text
position-encoding/
├── project.yaml                  # 项目 ID、原始目标、状态、revision 和绝对工作区路径
├── README.md                     # 新会话阅读顺序
├── .gitignore
├── docs/
│   ├── research-goal.md           # 保存原话，细化目标暂标为待讨论
│   ├── background.md             # 背景和来源待补充
│   ├── research-plan.md           # 不生成虚构的实验方案
│   ├── decisions/
│   ├── analyses/
│   └── reports/
├── code/                         # README.md、src/、tests/
├── configs/                      # experiments/、resources/、environments/
├── data/                         # README.md、manifests/、raw/、processed/
├── runs/                         # README.md 和空 index.jsonl
├── artifacts/                    # README.md
└── .agent-infra/                  # 初始化身份信息和预留 locks/，默认忽略
```

`project_id` 与目录名、显示名称分开；原始目标在 SQLite 与 `project.yaml` 中精确保留。
`status=draft` 表示科研尚未开始，`initialization=ready` 只表示初始化已完成。
科研文档可以由用户或 Agent 编辑；重跑 init 不会重写这些文件。
`runs/index.jsonl` 目前为空，未来用于引用 Records，不能作为另一套运行事实源。
生成的 `.gitignore` 默认忽略原始数据、处理后数据、运行输出、模型权重和凭据。

下一步可以让宿主机 Agent 阅读 README 和目标文档，与用户澄清背景、方法和成功标准。
可安装 B 批提供的研究 Skill 并在 Agent 中继续；初始化命令本身不自动调用模型或生成方案。

## 3. 预览、查询、重试和恢复

```bash
# 输出拟生成的文件及内容，不创建目录或数据库
uv run --locked agent-infra init ./position-encoding --goal "研究位置编码" --dry-run

# 查询原路径或初始化输出中的 project_id
uv run --locked agent-infra project show ./position-encoding
uv run --locked agent-infra project list

# 意外退出后按 ID 恢复，不需要重新输入原始目标
uv run --locked agent-infra project recover PROJECT_UUID
```

`agent-infra project init` 等同于 `agent-infra init`；`project preview` 等同于 `init --dry-run`。
也支持 `--directory PATH`，它与位置参数 directory 二选一。
成功输出 JSON，退出码 0；业务或文件错误输出 JSON 到 stderr，退出码 2。
参数解析错误使用 argparse 的说明和退出码 2。

重复相同目标路径、原始目标和名称，返回同一个项目；参数发生变化则报 `project_conflict`。
即使是空目录，只要不是此 store 已登记的工作区，也不会覆盖或接管。
默认自动命名每次新建一个项目；如果需要安全重试，第一次就传入固定操作 ID：

```bash
uv run --locked agent-infra init --goal "研究位置编码" --operation-id my-position-study-01
```

重试时保持操作 ID、根目录、目标和名称相同。预览输出中的 `project.operation_id` 也可用于正式 init，
以固定自动目录名和项目 ID；预览不会预留目录，创建时间以实际初始化为准。
初始化中断后，可先 `project list` 找出 `pending` 项目，再按 ID 恢复。

恢复仅继续本次初始化：从保存的文件快照补全暂存目录，再原子发布。
若已写入的文件被用户改过，返回冲突并保留现场，没有 `--force`。
可以检查并备份修改，将冲突文件恢复为原生成内容后重试；不要删除控制库来绕开冲突。
已经 ready 的项目不会因重试重置科研文档。

## 4. 元数据保存在哪里

状态根优先级：

1. 命令参数 `--state-dir PATH`。
2. 环境变量 `AGENT_INFRA_STATE_DIR`。
3. `$XDG_STATE_HOME/agent-infra`；未设置 XDG 时为 `~/.local/state/agent-infra`。

实际数据库位于 `<状态根>/projects/projects.sqlite3`。它与研究工作区分离，是 Project 元数据、
revision、初始化请求和恢复快照的权威来源；`project.yaml` 是可读投影。
项目命令使用固定用户级默认状态根，因此切换终端工作目录仍能查到同一个项目。
这与当前 `config-check` 的 `./var` 默认值不同；项目命令不读取 TOML，也不自动加载 `.env`。
需要固定团队或 worktree 配置时，显式指定状态根：

```bash
uv run --locked agent-infra init ./my-research --goal "研究目标" --state-dir /existing/state
uv run --locked agent-infra project show ./my-research --state-dir /existing/state
```

项目目录和状态目录不能互相包含。以后备份时应同时保留工作区与控制状态目录；仅复制工作区不等于恢复登记。
自动选择的用户状态路径会先解析系统已有的链接（如服务器将 `~/.local` 移到数据盘）。
显式 `--state-dir` / `AGENT_INFRA_STATE_DIR` 与项目路径仍拒绝链接，建议直接填写真实绝对路径；
查询和恢复应使用同一配置，CLI 输出会返回实际 `state_dir`。

`project show` 返回 store 中的项目，并报告 `manifest_matches` 和 `workspace_error`。
使用 ID 查询仍可检查丢失工作区的元数据；使用路径查询需要该目录内有可解析的 `project.yaml`。
手工修改 `project.yaml` 不会自动更新 store，也不会形成新的 revision。请将研究笔记写到 `docs/`。
本版不自动移动目录或导入任意目录。用户自行移动工作区后，可用 C 批 `project rebind` 显式绑定新路径，保留 ID 和历史；详见[操作说明](experiment-compilation.md)。

## 5. 开发接口与验证边界

- `projects/api.py`：不可变 Project、InitRequest、状态及错误类型；导入不产生 IO。
- `projects/service.py`：preview/initialize/get/recover；入口只负责参数转换。
- `projects/local.py`：本机 SQLite；元数据 `update(..., expected_revision=...)` 支持标题和科研状态，
  更新后标记 `projection_pending`，调用 service.recover 才完成清单投影。
  过期 revision 或尚未恢复的变更会被拒绝；原始目标不可修改。
- `projects/rendering.py` 与包内模板：纯渲染；`_filesystem.py` 实现安全创建与不覆盖发布。
- `bootstrap/projects.py`：对象组装及默认路径；`gateways/cli` 提供参数解析和 JSON 输出。

当前 CLI 不暴露 Project 元数据 update；研究草稿通过独立的 research 命令和研究 revision 管理。
原 Web Project catalog 保持不变，CLI 初始化的项目尚不会自动出现在 Web 中，W01 再统一适配。
支持 Linux 本机单管理员与本地文件系统；拒绝路径中的符号链接和 `..`，不支持 NFS 多机共享控制库。
初始化测试包含真实子进程并发、中断恢复和独立 wheel 安装；不代表研究规划或真实 Agent 实验已验收。
