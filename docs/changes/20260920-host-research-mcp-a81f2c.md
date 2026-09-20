---
record_version: 1
task_id: "20260920-host-research-mcp-a81f2c"
title: "H 批：长期科研环境、后台 Job 与宿主机 MCP"
branch: "feat/host-research-mcp"
base_commit: "c15f9469aa10e40f76dc2b6155bdab5026336ee5"
work_status: completed
updated_at: "2026-09-20T16:46:30+08:00"
pull_request: null
---

## Goal and acceptance

- 完成细分计划 H01–H05 的 CPU 范围；保留 D 批一次性求解，复用 Controller、资源准入与 Records。
- 项目绑定的长期环境、独立 Job/日志游标、受限文件操作；客户端退出不停止作业，确认环境清理后才释放资源。
- stdio MCP 连接独立服务，工具调用可追到 Run/Job/输出；宿主机原始轨迹显式导入、去重并声明覆盖范围。
- 验证跨项目拒绝、幂等请求、进程组取消、超时、重启清理、MCP 断连重连与真实宿主机 Codex 两轮 CPU 实验。

## Changes

- H01/H02：JobSpec/ResearchEnvironment 契约，DockerResearchEnvironment 复用现有 Docker 隔离与所有权日志；
  容器内只读标准库监督进程负责后台命令、进程组、超时、有界日志、目录描述符文件操作及孤儿进程回收。
- H03：`agent-infra mcp` 和 `agent-infra research`，13 个项目绑定的 stdio 工具，HTTP 入口保持协议转换职责。
  固定官方 `mcp==1.26.0` 并更新 uv.lock；只读工具标注 readOnlyHint；不修改全局 Agent 配置。
- 共用已有 Controller 单运行槽与资源管理器；research.sqlite3 只保存绑定摘要、Job 意图及操作回执，Run 状态仍在原控制库。
  MCP 退出不关闭环境，Controller 停止会清理环境；SIGKILL 后按 D04 清理并标记 interrupted，不自动重放。
- H04：拆出 ResearchEvidence，主动把日志和完整工具请求/回复写入 Records；保存项目/会话/Run/Job/调用关联。
  抽出共用 AgentEvent 记录转换；显式宿主机 JSONL 导入按来源/行号去重，标记 AGENT producer 和 partial 覆盖，
  对有 operation_id 的原生事件补充平台调用 span 引用；不扫描无关个人会话。
- H05：真实宿主机 Codex 使用 MCP 编写线性回归代码、运行两个学习率、读取指标、写报告并归档；
  Codex 退出后新 MCP 客户端读取并停止其后台作业，最终环境归档与清理通过。
- 新增[使用指南](../reference/host-research-mcp.md)、[实现导读](../implementation/host-research-mcp.md)，
  更新文档导航、README、项目概览、开发计划和独立 wheel 检查。

## Decisions

- 首版已有 Python 镜像、CPU/内存、单活跃 Run/环境、环境内单活跃 Job；不自动生成镜像，不涉及 GPU/Ray/PTY/SSH/Web。
- 容器无宿主机 Agent 凭据、无 Docker socket、网络关闭；工作区不直接挂载整个项目。当前面向同一可信 OS 用户科研，
  不承诺同容器 UID 下恶意命令与监督进程之间的安全隔离。边界和文件/日志/产物限额见命令参考。
- 环境结束后收集整个工作区，区分 cleanup_complete、lease_released 与 archive_complete。
  不确定操作保留 operation_uncertain，要求先查实际状态，而不是自动重复命令。
- 用户批准 H05：gpt-5.6-sol，最多 3 次 CLI、累计不超过 10 分钟；仅本机，单容器最多 1 CPU/2 GiB，不用 GPU，只清理任务资源。
  实际 2 次 CLI，共 123.507891 秒。未使用 gpt-6-astra；未修改全局 Codex 配置或复制账号到容器。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | 最终代码快照，子树如下 | passed | Ruff、mypy、模块依赖方向、文档、Web 检查、224 项非 E2E 测试及 Python/Web 构建通过 |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 最终代码构建 wheel | passed | 仓库外安装；原初始化/规划/编译场景、MCP 入口、SDK 和容器监督脚本打包检查通过 |
| `uv run --locked pytest -q -m e2e tests/e2e/test_host_research.py tests/e2e/test_research_mcp.py tests/e2e/test_controller_recovery.py tests/e2e/test_run_environment.py` | H 集成工作区，最后监督进程边界修正前 | passed | 13 项真实 CPU Docker/MCP 场景，含旧求解/隔离评测/取消与新路径；无模型/GPU |
| `uv run --locked pytest -q -m e2e tests/e2e/test_host_research.py tests/e2e/test_research_mcp.py` | 最终代码快照 | passed | 最后监督进程、取消入口修正后重验 4 项相关真实 Docker/MCP 场景；断连重连、跨项目拒绝、文件、日志、归档和 SIGKILL 恢复通过 |
| `uv run --locked python /tmp/h05-acceptance.py` | H05 实际工作区，Run 与摘要见下方 | passed | 第二次 CLI 使用真实 gpt-5.6-sol，16 次 research MCP 工具调用全部成功；两轮训练与跨 MCP 接管通过 |
| 独立公式重算、JSONL 工具类型检查 | H05 非版本化证据目录 | passed | 两个 loss 与独立计算一致；原始流未观察到 host command_execution，全程使用 research MCP |
| 最终 normalizer 重放真实 JSONL 两次 | 最终代码快照，临时 Records 库 | passed | 去重后 77 个事件、18 个原生事件关联平台 span、全部归类 AGENT producer；结果保存 final-native-replay.json |
| Docker 清单与进程检查、`git diff --cached --check` | 最终工作区 | passed | 原三个 RSI 容器保持运行；本任务 Controller/容器已停止，差异无空白错误 |
| GPU、多节点、其他真实 Agent 客户端、大数据、恶意同容器进程隔离 | None | not_run | 超出本批 CPU 验收范围，不据此宣称已支持 |

最终代码快照：`src=a2c909c3fbd4f706d277239fdeaa9e427db08da0`、
`tests=68ddfa9e4996b522cc36644e6c3bd4f4cd4f9216`、
`scripts=e2b54dcd25e556b88050195eb501b110dcba29b2`。依赖声明与锁文件一起提交。

第一次 H05 CLI 35.575028 秒，客户端默认 MCP 审批策略拒绝工具，未创建环境；按已获授权的范围
使用单次配置 `mcp_servers.research.default_tools_approval_mode="approve"` 后第二次成功，87.932863 秒。
没有通过扩大宿主机 Shell 权限绕过检查，也没有追加未授权模型调用。

H05 后仅追加原生来源分类/span 关联、清理重试释放状态、取消入口归属、监督进程关闭输出后仍执行超时及孤儿回收等修正，
由最终单元/真实 Docker/MCP 测试及原始流离线重放覆盖，没有再次调用模型。
测试开发时发现 `/proc` 在子进程已死亡时可能返回 ESRCH 或短暂 X 状态；修正终态检查后完整测试通过。

### H05 证据

非版本化目录 `/tmp/agent-infra-h05-20260920-a81f2c`；临时目录不是永久归档保证，运行证据不进入 Git。
项目 `962af22a-5552-511a-b8fb-26bc02877dfd`，Run `5304d10df8e94bfa88f28094886e5c28`。
两个训练 Job 为 `da04258d51054d188d783e2c10e521e3`、`adf915825c594ecd98ed993e28c91295`；
跨会话接管并取消的 Job 为 `aaf71a84398744529f7c82a5604268f6`。
镜像 `python:3.12-slim` 固定 ID 为 `sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`。

任务：x 从 -1 到 1，间隔 0.1；y=2x+1；w=b=0，全量 MSE 梯度下降 40 步。
学习率 0.02 的 loss 为 0.4879326905385478，0.2 的 loss 为 0.000004527185283199521。
产物包含两个 metrics JSON、report.md 和冻结工作区；没有隐藏 evaluator 或伪造 benchmark 分数。

- `acceptance.json` SHA-256：`1a001fc1c3d1c72c160f1424a2a87c5737143823dafbbafa817ab3847cbe2f19`
- `codex-2.jsonl` SHA-256：`70fca90b92a7f21e728f591e3a5b953fd187df1f42878861204a3d92e780fe64`
- `handoff.json` SHA-256：`b9ecd0d9a74f4b9dc0bf9e3e39f4260eed0eec83697b7595dda5ce4e528320dd`

## Open items and blockers

- None：H01–H05 CPU 范围实现与验收完成。GPU、大数据材料入口、环境自动构建、正式多用户服务及 Web 接入仍属后续。
- 未部署常驻服务；本分支未合并或推送，不代表远端已集成。

## Next steps

- 提交任务分支供审查；集成后按使用指南做实际科研试用，再按需要推进 GPU、E 批环境准备和 I 批分析。

## Compatibility and rollback

- 保留原 Run/Environment API 和控制库 schema；新增独立 research.sqlite3 schema 1、MCP SDK 及锁文件依赖。
  跨模块规范化函数移到 Agent 模块共用，旧托管 Agent 轨迹测试通过。
- 回退前关闭本版本 Controller，确认任务容器已删除，备份项目/控制库/Records 与工作区。禁止旧版本与新版本共同管理
  同一命名空间；不要删除主机锁或 Docker 创建不确定标记来绕过清理。
- 宿主机账号、全局 Agent 配置、既有 RSI 服务和远端分支未改动。
