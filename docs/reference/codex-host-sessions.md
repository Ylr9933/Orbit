# 宿主机 Codex 会话绑定与采集

状态：任务分支 `feat/codex-host-session-capture` 的本机实现；与 Docker Run 无关，不需要启动 Controller。
适用于**本机 Codex CLI 写入的交互式会话文件**。本功能不启动模型，也不修改 Codex 账号配置。

Codex 默认把会话记录放在 `$CODEX_HOME/sessions`，归档会话放在
`$CODEX_HOME/archived_sessions`（未设置 `CODEX_HOME` 时为 `~/.codex`）。
发现命令只读取每个文件的第一条 `session_meta`，用其中的 `cwd` 过滤到项目根目录及子目录；
它不扫描对话内容。目录只是候选条件，必须显式绑定具体 `thread_id`；一个会话不能绑定两个项目。

```bash
# 项目先用 agent-infra init 创建，所有命令沿用同一个状态目录。
agent-infra project codex discover PROJECT_ID --state-dir /absolute/infra-state
agent-infra project codex bind PROJECT_ID THREAD_ID --state-dir /absolute/infra-state

# 已绑定的会话继续产生对话后，可随时增量同步；重复执行不会重复记事件。
agent-infra project codex sync PROJECT_ID THREAD_ID --state-dir /absolute/infra-state
```

`bind` 会立即导入前 2000 条完整 JSONL 行，返回 `records_run_id`、
`records_attempt_id`、`next_line` 和 `has_more`。若 `has_more=true`，重复运行 `sync`；
`--max-lines` 可设为 1–10000。活跃会话未写完的最后一行留待下次同步。
单行超过 16 MiB 会明确报错，不跳过原始证据。

导入后可用现有 Records CLI 阅读统一事件和轨迹：

```bash
agent-infra records events RECORDS_ATTEMPT_ID \
  --root /absolute/infra-state/controller/records
agent-infra records trajectory RECORDS_ATTEMPT_ID \
  --root /absolute/infra-state/controller/records
```

Records 为每个宿主机 Codex 会话建立独立的 Run/Attempt，带项目 ID、Codex thread ID 和
`host_agent=partial` 覆盖声明。原始 JSONL 行作为私有 Blob 保存；规范事件提取用户/助手消息、
工具调用及结果、轮次结束和部分 token 用量。每条事件含原始 Blob 引用和原文件行号。
工具输入/输出和消息超过 16 KiB 时规范事件截断并标记，原始行仍完整保留。
Codex 没记录到的宿主机进程或手动操作不会凭空出现；隐藏推理内容也不会被推断出来。
交互式会话 JSONL 是 Codex 的本地实现格式，与 `codex exec --json` 不同；
本采集器带独立的 normalizer 版本，遇到未知事件保留原始行，不伪造语义。
如果同一 Codex 会话还使用科研 MCP，建议将 MCP 配置的 `--session-id` 设为发现到的
`THREAD_ID`。这样宿主机轨迹与平台工具记录拥有相同的会话关联键；此前使用自定义
`SESSION_ID` 的记录仍按项目可查，但不会自动推断两种 ID 必然相同。

若希望每轮 Codex 完成后自动同步，可以在**用户级** `$CODEX_HOME/config.toml` 中设置
Codex 的 `notify`（Codex 当前仅在 `agent-turn-complete` 触发）：

```toml
notify = ["/absolute/infra/.venv/bin/agent-infra", "project", "codex", "notify", "--state-dir", "/absolute/infra-state"]
```

Codex 会追加一个 JSON 参数；回调根据其中的 `thread-id` 找到**已绑定**会话，并检查通知的
`cwd` 仍在项目目录下，再做增量同步。未绑定会话不会自动导入。若用户已经配置了其他
`notify` 程序，应由用户自行把本命令接入现有通知脚本；不要直接覆盖原配置。
可先手动 `sync` 验证，再配置通知。通知是轮次结束触发，不保证正在生成时的实时流；
异常退出后可手动 `sync` 补采。

注意：会话可能含提示词、命令、工具响应与敏感数据。状态目录和 Records 保持仅限本机用户访问，
不要提交到 Git 或把原始 Blob 公开分享。项目目录本身不保存会话副本。

Codex 官方说明：[会话文件位置](https://learn.chatgpt.com/docs/reference/troubleshooting)、
[notify 字段与触发时机](https://learn.chatgpt.com/docs/config-file/config-advanced)、
[`codex exec --json` 格式](https://learn.chatgpt.com/docs/non-interactive-mode)。
