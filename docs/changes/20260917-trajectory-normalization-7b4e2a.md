---
record_version: 1
task_id: "20260917-trajectory-normalization-7b4e2a"
title: "Normalize Agent traces into canonical tool and message events"
branch: "feat/trajectory-normalization"
base_commit: "8708840309fcc45f0d803f00e2095e8617a27603"
work_status: completed
updated_at: "2026-09-17T22:12:00+08:00"
pull_request: null
---

## Goal and acceptance

- 在保留 Agent 原生 JSONL 和 native payload 的前提下，将 Codex、Claude Code 与 DSH
  的 message、tool call、tool result、usage、session、completion 和 error 映射为版本化的
  规范载荷。
- 每个原生消息中的独立工具调用产生独立规范事件，并稳定提取 tool call ID、工具名称、
  参数、结果与状态；无法识别的字段继续通过 native payload 和 raw stream 回溯。
- 轨迹派生使用规范字段而非 provider 私有路径，并声明工具关联与规范化完整性。
- 先更新架构与接口文档，再修改实现；补充单元、Run/Records 集成和轨迹导出测试。

## Changes

- 已在 `agent-module.md` 和 `records-design.md` 定义小型公共核心、完整 native、原生行拆分、
  tool call/result 关联以及 trajectory 完整性规则。
- `AgentEvent` 增加版本化 canonical payload、原生行号和 part index；Codex、Claude Code 与 DSH
  适配器提取 message、tool、usage、session、completion 和 error 公共字段。
- Claude Code 的多个 content block 拆成独立事件；Codex/Claude completion 与 usage 分别记录。
- Run 将规范字段写入 Records 顶层载荷，用 tool call ID 建立 correlation 和共享 Span，同时保留
  native payload 与 raw stream 引用。
- trajectory 升级为 `records.trajectory.v2` / `attempt-event-graph@2.0.0`，按 call ID 关联并行工具
  结果，并输出 `tool_call_correlation` 完整性。
- Web 查询只暴露允许展示的规范摘要字段；实现指南、Records 参考和项目状态已同步。

## Decisions

- 采用 Raw evidence、canonical event、derived trajectory 三层，而不是把所有 provider 字段
  平铺为公共字段。
- 内部 schema 由项目版本化，并参考 OpenTelemetry GenAI/OpenInference 的 tool call 核心语义；
  外部标准仍在演进，不直接作为本地持久化 schema。
- 一条原生消息中的每个工具调用独立成规范事件；公共字段只记录观测事实，无法确认的字段省略，
  provider 私有信息继续保留在 native。
- 轨迹是从不可变规范事件派生的版本化视图；工具结果通过 call ID 优先、Span 回退关联，不改写
  源事件。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `uv run --locked python scripts/ci/check_repository.py` | `feat/trajectory-normalization` documentation checkpoint workspace | passed | Policy mirror 与本地 Markdown 链接通过。 |
| `git diff --check` | `feat/trajectory-normalization` documentation checkpoint workspace | passed | 未发现空白错误。 |
| 首次 `make verify` | implementation workspace before `make setup` | failed | Python lint、依赖边界和 Mypy 已通过；新 worktree 缺少 `node_modules`，在 `biome: not found` 停止。 |
| `make setup` | `feat/trajectory-normalization` workspace | passed | 锁定的 Python 与 Node 依赖安装完成。 |
| 定向 Agent/Run/Records/Web 测试 | final implementation workspace | passed | 49 tests passed，覆盖多工具拆分、字段规范化、Records correlation、并行结果关联和 Web 摘要。 |
| `make verify` | final implementation workspace at 2026-09-17T22:12:00+08:00 | passed | Ruff、格式、import-linter、Mypy、Biome、TypeScript、文档检查通过；116 个非 E2E 测试与 Python/Web 构建通过。 |
| 真实 Codex/Claude/DSH 与 Docker E2E | final implementation workspace | not_run | 需要真实 provider 凭据、模型费用与固定 CLI 镜像；本任务以记录的原生格式 fixture 验证 normalizer，不宣称真实模型兼容验收。 |

## Open items and blockers

- None。

## Next steps

- None；授权范围已完成。后续升级真实 Agent CLI 时，应使用对应固定版本的原生 JSONL fixture
  和受预算控制的集成检查重新验证 adapter。

## Compatibility and rollback

- `AgentEvent` 只增加带默认值的字段，原有四参数构造保持兼容；新 Records 的 Agent payload schema
  从通用 `records.payload.v1` 改为 `agent.*.v1`，trajectory schema/builder 升级到 v2/2.0.0，消费者
  应按版本读取。现有 raw stream、native payload、旧 Records 和 v1 导出保持可读。回滚代码会停止
  生成新规范字段，但不破坏已经持久化的原始证据或事件 JSON。
