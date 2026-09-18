---
record_version: 1
task_id: "20260918-research-implementation-plan-a3c7e1"
title: "Break the research workflow into bounded implementation tasks"
branch: "docs/research-implementation-plan"
base_commit: "29d45651c93a8ce4735093bba7bfe662f184a27d"
work_status: completed
updated_at: "2026-09-18T16:06:18+08:00"
pull_request: null
---

## Goal and acceptance

- 将 0917 设计提案拆为可逐项交给 Codex 的开发任务；每项包含依赖、范围、交付、验收和暂不处理的内容。
- 明确第一项工作、短期可用里程碑、既有模块复用、两种执行模式和自动环境构建的依赖顺序。
- 提供单任务提示模板与协作边界；只做规划，不实施产品能力。

## Changes

- 新增 `docs/development/research-workflow-implementation-plan.md`，拆分 38 项任务；每项有依赖、范围、交付、验收和暂缓内容。
- 明确 A00/A01 两轮起点，M1–M6 里程碑、既有代码复用、两种执行模式及自动构建的实施顺序。
- 提供单任务 Codex 提示模板、四人协作建议和真实验收边界。
- 更新 `docs/README.md` 与原开发顺序的导航；本轮只记录计划，未修改项目能力概览。

## Decisions

- 在上一轮设计分支提交上创建新的文档分支；上一轮提案仍未进入本地 main，本次交付包含对该提案的依赖。
- 先交付项目初始化和规划，再用已有镜像验证真实执行；自动镜像构建和无人值守研究循环后置。
- 不修改既有历史任务记录或将计划能力写成已实现能力。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `uv run --locked python scripts/ci/check_repository.py` | `29d4565` 加本任务四份文档变更 | passed | 规则镜像和本地 Markdown 链接通过。 |
| `git diff --check` | 同上 | passed | 无空白错误。 |
| `uv run --locked python` 任务结构/依赖检查 | 同上 | passed | 38 个唯一任务编号，引用均存在，显式依赖无环，四项任务字段和代码围栏检查通过。 |
| 人工核对里程碑、实现依据及授权范围 | 同上 | passed | M1/M2 不依赖 Docker；M3 复用已有镜像；MCP、构建、迭代分别验收；所有任务尚待实施。 |
| 产品测试、真实 Docker/模型/GPU | None | not_run | 仅规划文档变更，无产品实现或实机验收范围。 |

## Open items and blockers

- None；文档任务完成。计划中的 38 项实现任务均尚未实施。

## Next steps

- 本次授权工作已完成；后续实施从 A00 开始，先核实设计提案与本计划所在基线。

## Compatibility and rollback

- 只变更文档；无运行时、依赖或存储迁移。撤销本次文档提交即可回退。
