---
record_version: 1
task_id: "20260917-research-project-design-91d74e"
title: "Design research project initialization and iterative experimentation"
branch: "docs/research-project-lifecycle"
base_commit: "f8f47f3"
work_status: completed
updated_at: "2026-09-17T22:37:45+08:00"
pull_request: null
---

## Goal and acceptance

- 将从自然语言研究目标到 Project 初始化、研究规划、实验执行、证据分析和迭代的产品主线详细记录在 `docs/architecture/0917设计微调.md`。
- 明确代码工作流和 Agent Skill 的职责边界。
- 说明宿主机 Agent/MCP 和容器内托管 Agent 如何复用同一项目模型。
- 记录自动环境准备的缺口、实施顺序和端到端验收方式。

## Changes

- 新增 `docs/architecture/0917设计微调.md`，详细定义 Projects 长期研究层、工作区协议、规划交互、研究状态机、实验编译、环境准备、分析迭代和自治策略。
- 说明宿主机 Agent/MCP 与 Docker 内 Planner/Agent 的定位，两者共用 Projects/Tasks/Runs/Records 契约且不直接获得 Docker socket。
- 更新 `docs/README.md`，将新提案加入当前阅读入口。

## Decisions

- 文档作为架构提案放入 `docs/architecture/`，不将未实现命令和契约表述为当前能力。
- 建议将 Projects 升级为正式业务模块，但实施前通过 ADR 确认权威存储、工作区所有权和 Planner 生命周期。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `uv run --locked python scripts/ci/check_repository.py` | `docs/research-project-lifecycle` workspace at 2026-09-17T22:37:45+08:00 | passed | `AGENTS.md`/`CLAUDE.md` 一致性及本地 Markdown 文件链接通过。 |
| `git diff --check` | `docs/research-project-lifecycle` workspace at 2026-09-17T22:37:45+08:00 | passed | 未发现空白错误。 |
| `uv run --locked python` 文档结构脚本 | `docs/research-project-lifecycle` workspace at 2026-09-17T22:37:45+08:00 | passed | 文档 757 行，30 个代码围栏成对，关键章节存在。 |
| 手工实现状态核对 | `main@f8f47f3` 和本分支文档 | passed | 当前 Project catalog/Task draft/Docker Run 与未实现 Projects、MCP、镜像构建、Planner 均分开标记。 |

## Open items and blockers

- None。文档中列出的 ADR 决策是后续实施前的架构工作，不是本文档任务的未完成项。

## Next steps

- None；当前授权的设计文档范围已完成。

## Compatibility and rollback

- 本任务只添加架构提案和导航，不修改当前产品代码、契约、数据库或部署。回滚时移除新文档和导航链接即可。
