---
record_version: 1
task_id: "20260921-trajectory-visibility-eligibility-c4e2b7"
title: "修复科研执行事件展示和训练资格误判"
branch: "fix/trajectory-visibility-and-eligibility"
base_commit: "2eb04e588b5f8cec8bc0afdbea4e5a6de130df7f"
work_status: completed
updated_at: "2026-09-21T17:13:31+08:00"
pull_request: null
---

## Goal and acceptance

- 解释 first-study 的平台执行轨迹、Codex 原生轨迹与训练数据资格的区别，依据真实 Run 和现有实现陈述限制。
- 让 Web 在不暴露原始请求体、私有评测或凭据的情况下显示已有的平台工具事件，并用容易理解的标签、时间与采集范围呈现。
- 收紧派生轨迹的 SFT/RL 候选判断：纯平台工具调用或已知不完整的宿主机 Agent 轨迹不能标为完整训练候选；保留可用于排障的步骤与来源引用。
- 相关服务、权限、前端构建与回归测试通过，不改用户真实实验数据或正在运行的服务。

## Changes

- `runs/console.py` 的安全事件摘要加入 Environment 工具请求/结果，并返回允许公开的 `platform_tools`、`host_agent` 采集范围；原始参数、结果和 blob 引用仍不进入响应。
- Web 运行详情将同页工具请求/响应合并为中文操作项，展示本地时间、状态和采集范围，明确区分平台执行记录与 Codex 原生会话。
- `records/trajectory.py` builder 更新至 2.0.2：纯平台操作和已知宿主机采集不完整的 Attempt 不再被误列为 SFT/RL 候选；分析 step 和原始证据保持可重建。
- 更新 Records 参考、实现导读与 Web 使用说明，并加入隐私、训练资格和浏览器夹具回归。

## Decisions

- 本次 first-study 有 48 条 Records 事件，Web 白名单遗漏 Environment 产生的 22 对 tool 事件，故页面仅显示 4 条；数据没有丢失。
- 该 Run 的 22 个派生 step 全是平台工具调用，Attempt 标注 host_agent=partial，且没有 reward。当前 sft_candidate 为过于宽松的标记，应改为保守资格说明。
- 修复现有过滤/展示与派生语义，不从原始 blob 自动公开命令参数或工具输出；完整宿主机 Codex 原生会话需要单独采集。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| first-study Run 状态、事件类型与现有轨迹只读查询 | 2eb04e5 + 用户状态目录 | passed | 48 条事件、22 个平台工具 step、host_agent=partial、无 reward |
| `uv run --locked pytest -q tests/unit/records/test_trajectory.py tests/unit/web/test_console.py` | 本分支工作区，修复后 | passed | 10 项通过；包含平台工具可见性/隐私和训练资格回归 |
| `make verify` | 本分支工作区，采集范围文案微调前 | passed | lint、mypy、依赖边界、299 项非集成测试、Python/Web 构建通过；23 项集成/E2E 未运行 |
| `pnpm check`、`uv run --locked ruff check src/agent_infra/runs/console.py`、`git diff --check` | 本分支最终工作区 | passed | 文案格式修正与安全字段收紧后通过 |
| first-study 原 Attempt 只读重新派生 | 本分支工作区 + 用户状态目录 | passed | 22 step，`eligible_for=('analysis',)`，action unavailable，capture partial；原始数据未改动 |
| `node tests/web/console.smoke.cjs` | 本分支工作区 | not_run | 本机缺少可选 `playwright` 模块，浏览器夹具未启动；Web 构建与 HTTP 单测通过 |

## Open items and blockers

- 本轮未采集完整宿主机 Codex 原生会话，也未构造可直接训练的 RL 数据；这是后续独立任务。
- 可选浏览器验收因本机缺少 Playwright 依赖未运行；无模型/容器服务变更。

## Next steps

- 经审查后合并任务分支；部署/重启 Web 时再用真实 first-study 页面确认展示。
- 若要推进 Agentic RL，另立任务采集完整 Agent 原生观测/动作、明确奖励，并按训练算法补必要元数据。

## Compatibility and rollback

- 仅查询展示和按构建器版本派生的资格变化，不迁移或改写已存 Records；旧导出文件保持原样，新导出需明确新版本。
