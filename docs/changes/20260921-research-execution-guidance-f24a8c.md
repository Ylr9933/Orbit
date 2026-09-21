---
record_version: 1
task_id: "20260921-research-execution-guidance-f24a8c"
title: "修复科研 Skill 缺少平台执行引导的问题"
branch: "fix/research-execution-guidance"
base_commit: "3d1371b845f464869d24fcb9a1bcda5dcae4ba5e"
work_status: completed
updated_at: "2026-09-21T16:00:43+08:00"
pull_request: null
---

## Goal and acceptance

- 排查用户首次科研测试绕过 Docker 的原因，给出基于实际状态的结论。
- 明确 Skill 在用户要求平台执行时的路由、失败处理和证据要求；更新试用指南。
- 不把提示词视为强制隔离；保留用户原始本机结果，不自动重跑实验。
- 包内 Skill 校验、安装/冲突保护测试、文档及打包验证通过。

## Changes

- 只读核对运行中的 Controller/MCP，以及该测试项目的方案、报告和平台记录。
- 包内科研 Skill 明确沿用用户 host/Docker 选择，在现有 brief.constraints 中保存；补齐 H 的 MCP/CLI 执行步骤、失败处理和真实 Run/Job/产物证据要求。
- 首次试用指南补充选择方式、绕过平台的排障、宿主机记录边界，以及 Docker 工作区、归档、大小限制与备份说明。
- 未改项目进度：本轮没有新增执行后端或改变已集成能力。用户项目中的已安装 Skill 副本未修改。

## Decisions

- Controller health.ready=true；项目已绑定，但平台 commands/jobs/operations 均为 0，报告明确本机执行。未读取用户个人会话历史。
- 修复随包科研 Skill 的范围说明和执行指南，不改调度内核或用户研究结果；模型工具选择不能由 Skill 硬性保证。
- 本轮无模型、Docker/GPU 实验，无资源授权扩张。真实 Agent 行为修正需要后续实际重跑确认。
- 简单任务允许用户选择宿主机，但直接本机执行不能宣称为平台 Run；平台管理的宿主机后端仍未实现。
- 保留安装器的用户修改保护；本轮交付包内指导，既有项目升级需对比、备份副本并重新加载，不自动改写用户工作区。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Controller health、平台 SQLite 只读查询、项目报告核对 | 3d1371b / 用户本机状态 | passed | 服务健康、已有绑定、无执行记录；已安装 Skill 与当前包内两份文件相同 |
| quick_validate.py src/agent_infra/projects/skills/agent-infra-research | 3d1371b + 本任务工作区 | passed | 使用 skill-creator/scripts/quick_validate.py；Skill is valid |
| uv run --locked pytest -q tests/unit/projects/test_research.py | 同上 | passed | 26 passed；覆盖安装重复执行和用户修改保护 |
| uv build；检查 wheel 中两份 Skill 文件与源码逐字节一致 | 同上 | passed | wheel/sdist 构建成功；打包内容一致 |
| bash -n / ast.parse 检查两份执行参考中的示例 | 同上 | passed | 仅语法校验，不代表实际执行 |
| uv run --locked python scripts/ci/check_repository.py；git diff --check | 同上 | passed | 文档链接、规则镜像和空白检查通过 |
| 源码核对挂载、ResearchController._close、Records 存储及限额 | 同上 | passed | H 绑定工作区、归档失败保留、1 GiB/8 MiB/16 MiB 边界；未启动容器 |
| 实际 Agent 选择工具并重跑实验 | None | not_run | 本轮无模型调用或实验执行，不宣称行为已验收 |

## Open items and blockers

- None（本轮指导修订与静态/单元验证完成；未把真实 Agent 重跑纳入本轮验收）。

## Next steps

- 后续真实试用前升级/重新读取项目 Skill，显式选择执行方式；Docker 验收须取得真实 Run/Job 和产物。本轮不自动重跑。

## Compatibility and rollback

- 仅包内提示、参考说明和操作文档；不改业务接口、数据库或实验文件。
- 若更新用户项目 Skill，只更新与旧包逐字节一致的文件，并保留可恢复副本；不覆盖用户自定义内容。
