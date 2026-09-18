# 科研规划：保存方案、用户修订和新会话恢复

状态：Agent Infra 0.1.0，B01–B04 本地实现。B05 实际验收见[任务记录](../changes/20260918-research-planning-b6f2a1.md)。
前置条件：已有[初始化项目](projects.md)与相同 state-dir；Linux、Python 环境可用。
本轮不会启动实验或调用模型；用户在自己的 Agent 会话中规划。测试脚本的模型调用需单独显式启用。

## 1. 日常怎么用

初始化后，先把研究 Skill 安装到这个项目：

```bash
uv run --locked agent-infra project research skill /path/to/project --install
```

进入项目目录，在 Codex 中让它使用 `$agent-infra-research`，并告诉它目标，例如：

> 读取项目。帮我比较两种位置编码在长上下文上的效果，最多一张 GPU，数据尚未选好。
> 先和我讨论一个小规模实验，保存研究方案，暂时不要执行。

Skill 安装在 `.agents/skills/agent-infra-research/`，内容随 wheel 交付；不会修改全局 Agent 配置。
其他 Agent 可直接读取同一说明并调用 CLI；其自动 Skill 发现未在本轮验收。
如果是自定义状态根，请告诉 Agent 使用同一绝对 `--state-dir`；本项目仍不自动加载 `.env`。
如果命令仅在仓库 venv 中可用，可以向 Agent 提供该 venv 下 `agent-infra` 的绝对路径。

Agent 的工作是读取上下文、检查已有材料、询问必要问题、形成研究说明和实验方案，再用 CLI 保存。
不要求每次把所有字段填完。无数据、未选指标或只需人工查看结果都可以先保存，缺项以后再补。
使用限制写入的 Plan 模式时，先讨论，再在允许写入的阶段保存。

换一个会话时，让 Agent 读取：

```bash
uv run --locked agent-infra project research context /path/to/project
```

它会得到原始目标、最新 Brief/Plan、此前采用的版本、用户决定、未决问题、下一步和最近修改原因。
当前没有真实实验关联，因此 run_references 为空，execution_links_supported 为 false。
新建 revision 不会清除此前采用的版本，context 会明确标记还有未采用的新变化。

## 2. 开发者和 Agent 使用的最小接口

所有命令接受项目 UUID 或原目录，以及可选 `--state-dir PATH`。下面省略 `uv run --locked` 前缀；
已安装环境直接执行即可。JSON 参数格式见随包提供的[命令与 schema 说明](../../src/agent_infra/projects/skills/agent-infra-research/references/commands.md)。

| 命令 | 用途 |
| --- | --- |
| `project research context PROJECT` | 恢复上下文；初次保存前 research_revision 为 0 |
| `project research save PROJECT --file draft.json --expected-revision N --reason TEXT` | 保存完整快照，非增量 patch；保留未修改字段 |
| `project research show PROJECT [--revision N]` | 查询最新或历史快照 |
| `project research history PROJECT [--limit 20] [--before N]` | 分页查询版本、摘要、原因和确认记录 |
| `project research diff PROJECT --from-revision A --to-revision B` | 比较两个版本的结构化内容 |
| `project research confirm PROJECT --revision N --digest SHA --decision TEXT` | 记录对具体当前版本的采用决定 |
| `project research check PROJECT [--revision N]` | 报告待定项、材料缺失、资源 YAML 错误，不分配资源 |
| `project research export PROJECT` | 重试当前 Markdown 投影 |
| `project research import-notes PROJECT --section background --file notes.md --expected-revision N --reason TEXT` | 原文导入一个字段，section 可为 background/question/plan |
| `project research skill PROJECT [--install]` | 查询包内说明，或安装到当前项目 |

第一次保存的最小 JSON 可以只有 `{"schema_version":1}`，但实际应逐步补充有用的研究内容。
文档最大 256 KiB，单个文本字段最大 20,000 字符，实验最多 50 个。
`sourced` 关键结论需要引用；引用的真实性由 Agent 与用户核对，代码不声称自动验证文献。
指标方向支持 maximize/minimize/inspect；不要求科研任务带 evaluator。
资源建议通过已有 ResourceRequest YAML 表达，不能将建议数量当作已分配资源。
输入路径必须在项目内；外部数据可以先用项目中的 manifest 描述，实际材料接入留到 Task 编译。

保存成功返回 `saved=true`、revision、digest 和 projection 状态。普通参数/业务错误退出码 2；
check 只报告问题，退出码 0，不可把它当作“允许执行”的信号。
确认允许不完整方案，但只适用于当前精确版本；不会启动 Task 或 Run。
决策说明记录调用者所表达的用户选择，并不提供多人审批身份认证。

## 3. 如何处理手工改动

SQLite 是版本和决定的权威存储；`docs/research-goal.md`、`background.md`、`research-plan.md`
是最新草稿的可读投影。它们的头部标明研究 revision/digest，与 project.yaml 的初始化/项目 revision 分开。

如果用户手改了生成文件，后续保存仍会登记新研究版本，但不会覆盖该文件，返回 projection pending。
context 的 projection_pending 表示数据库中尚未完成的导出，不是实时文件监控；手改内容在 save/export 时检查。
可以保留手工文档，继续保存草稿；也可以从独立笔记导入内容，或显式导入对应生成文档后重建投影。
导入是把整份文本放到所选字段，不会把 Markdown 自动解释成结构化实验或用户授权。

删除文件、符号链接、身份不匹配和权限错误都不会被自动“修复”。查看返回的具体冲突，先处理原因，
然后运行 export。进程中途退出时，数据库的草稿可读，重新 export 或重试同一次 save 可完成剩余文件。
初始化 recover 处理 Project 身份/清单；research export 处理研究文档，两者职责不同。

## 4. 存储兼容与当前边界

研究存储在 B 批引入 schema 2，C 批进一步增加编译关联并升级为 schema 3；仅查询不会触发升级。
旧 Project、研究摘要和原始目标不变。升级前备份状态与工作区，回退需恢复升级前备份，详见[当前编译 ADR](../adr/20260918-experiment-compilation.md)。

当前只支持本机可信单管理员；方案确认不是独立的身份授权服务。
Brief/Plan 版本、背景笔记和待办已可持续保存；采用方案可通过[C 批命令](experiment-compilation.md)编译成 Task。
context 增加最近 5 个 compiled_tasks 引用，但真实训练、MCP、结果关联及 Web 接入属于后续批次。
研究 Skill 不会让模型变得必然正确，也不替代实验验证。

## 5. 验证与真实交互重跑

自动验收：`make verify`；安装验收：`uv run --locked python scripts/ci/smoke_wheel.py`。
真实模型验收使用独立目录，用户修订放在本地 UTF-8 文件中：

```bash
uv run --locked python scripts/acceptance/research_codex.py \
  --run-real-codex --model gpt-5.6-sol \
  --output-dir /tmp/agent-infra-research-acceptance-new \
  --correction-file /path/to/actual-user-correction.txt --seconds 600
```

前提是用户已同意模型和预算、Codex 已登录、输出目录尚不存在。脚本最多启动三次全新 Codex CLI，
共用累计 600 秒上限；一次 CLI 可包含多轮模型请求，不等同于只发出三次底层 API 请求。
三次分别保存初稿、处理用户修订、仅从持久数据恢复；事件、回答和快照保存在输出目录，不能进入 Git。
返回码 0 仅说明三次进程正常退出，还必须核对实际 CLI 工具调用、研究版本、修订内容和新会话回答。
