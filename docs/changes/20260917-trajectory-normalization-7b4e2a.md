---
record_version: 1
task_id: "20260917-trajectory-normalization-7b4e2a"
title: "Normalize Agent traces into canonical tool and message events"
branch: "feat/trajectory-normalization"
base_commit: "8708840309fcc45f0d803f00e2095e8617a27603"
work_status: in_progress
updated_at: "2026-09-17T21:56:17+08:00"
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
- 实现尚未开始；当前阶段只修改设计与任务文档。

## Decisions

- 采用 Raw evidence、canonical event、derived trajectory 三层，而不是把所有 provider 字段
  平铺为公共字段。
- 内部 schema 由项目版本化，并参考 OpenTelemetry GenAI/OpenInference 的 tool call 核心语义；
  外部标准仍在演进，不直接作为本地持久化 schema。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `uv run --locked python scripts/ci/check_repository.py` | `feat/trajectory-normalization` documentation checkpoint workspace | passed | Policy mirror 与本地 Markdown 链接通过。 |
| `git diff --check` | `feat/trajectory-normalization` documentation checkpoint workspace | passed | 未发现空白错误。 |
| 单元与集成测试 | `feat/trajectory-normalization` workspace before implementation | not_run | 实现尚未开始。 |

## Open items and blockers

- 完成规范载荷设计、实现、回归测试和最终文档对账。

## Next steps

- 先完成 Records/Agent 权威设计文档并通过链接和格式检查，再开始代码实现。

## Compatibility and rollback

- 计划为 `AgentEvent` 增加向后兼容的规范载荷字段，并升级 trajectory builder 版本；现有 raw
  stream、native payload 和 Records event envelope 保持可读。回滚时可恢复旧 normalizer/builder，
  原始证据不受影响。
