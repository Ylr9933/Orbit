---
record_version: 1
task_id: "20260918-experiment-compilation-c42d8e"
title: "Compile confirmed experiments into frozen Tasks (C01–C03)"
branch: "feat/experiment-compilation"
base_commit: "05f73e743760c451303b7b4d7070c26643b762e9"
work_status: completed
updated_at: "2026-09-18T22:21:41+08:00"
pull_request: null
---

## Goal and acceptance

- 实现 C01–C03：确认的研究版本与稳定 Experiment/Task 身份关联；材料独立复制、内容摘要、可重复编译和历史查询。
- 现有 Tasks loader/view/review/freeze 消费真实生成物；缺材料/执行配置返回缺项；科研可明确无评测，不提交 Run。
- 项目移动后显式重绑定身份，旧任务保持可用；处理发布/登记中断、并发和材料变化。
- 整理相关代码结构，分离存储、材料准备、转换与入口；保留现有公开接口。提供可复制示例、维护说明及测试。

## Changes

- C01：新增公共 TaskReference 与 CompiledExperiment，保存 Project/Experiment/研究版本/Task 摘要关联。项目移动后可以显式 rebind，并通过既有 recover 恢复中断的清单更新。
- C02：只复制选定输入及控制配置，生成求解说明和原格式 Task manifest，调用真实 Tasks loader/view/review/freeze/resource-check 验收。资源/执行配置为 controller-only，科研明确无评测。
- C03：新增 project compile/compiled-tasks/resolve-task/rebind CLI；缺项返回 needs_input 和退出码 1，损坏或冲突不覆盖。相同冻结输入重试得到同一引用，新方案或材料产生新 revision。
- 维护整理：原 LocalProjectStore 中的连接、锁和研究 SQL 分别提取为 ProjectDatabase 与 ResearchStore，保留原调用入口；新增独立的编译关联查询、材料复制、转换、准备和协调文件。一级模块依赖方向不变。
- 新增小型 CSV/代码/方案样例和可执行 CLI 验收脚本，并接入独立 wheel smoke。补充[使用说明](../reference/experiment-compilation.md)、[ADR](../adr/20260918-experiment-compilation.md)、[整体代码与调用链说明](../implementation/project-workflow-code-guide.md)，同步项目概览和开发计划。

## Decisions

- 复用 Tasks 契约和校验器，不新增执行器；编译不调用模型、Docker 或资源分配。
- 控制目录保存独立任务包，项目路径不是 Task 身份；只复制明确选中的材料，不使用硬链接或跟随符号链接。
- 执行配置沿用 Tasks 的 environment/tools/evaluation/execution_policy 节定义；必须显式声明科研不评测及工具需求，运行预算由后续 D 批预检。
- 一次编译持有同一控制库 writer 锁，防止采用版本在复制期间被切换。先发布不可覆盖包再登记；发布后登记前中断可用原输入重试。旧包损坏明确报错，未登记/临时材料不自动清扫。
- 默认复制上限 1 GiB、10,000 条目和 64 层；拒绝符号链接、硬链接、特殊文件及输入/输出重叠。大数据外部不可变存储适配保留后续工作。
- 基于[开发计划](../development/research-workflow-implementation-plan.md)和[研究规划记录](20260918-research-planning-b6f2a1.md)。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | 最终自动验收快照（下方 Git 子树） | passed | 203 项测试通过，7 项 Docker E2E 按范围排除；Ruff、mypy、依赖方向、文档、Web 检查与 Python/Web 构建通过。 |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 同上生成的 wheel | passed | 在仓库外独立安装；原 A/B 场景通过，并使用已安装 CLI 完成 C03 保存/采用/编译/Tasks 准备/迁移/新版与旧版/缺材料验收。 |
| C 批 22 项测试（包含在 make verify 内） | 同上 | passed | 真 SQLite、实际材料复制、真实 Tasks 消费者；覆盖并发重试、发布后子进程退出、重绑定提交后退出、材料变化、链接/特殊文件、损坏保留、工具声明、schema 2 升级与研究摘要不变。 |
| `uv run --locked python scripts/acceptance/project_compilation.py --output-dir /tmp/agent-infra-c03-20260918-c42d8e` | C03 编译实现工作区，最终版本另由上述 wheel 重验 | passed | 可保留的本机示例证据为 acceptance.json；随后仅整理研究 SQL 中的同事务读取及文档，不修改示例编译结果。 |
| `git diff --cached --check` | 同上及文档 | passed | 暂存差异无空白错误；源码、测试、配置和运行材料已区分。 |
| 真实模型、Docker、GPU、训练、镜像存在性 | 本分支 | not_run | C 批不执行这些操作；编译结果始终标记 execution_validated=false，运行预检属 D 批。 |

最终自动验收快照：`src=3dfc8c55c802140ed89f022aa819c53819619e46`、
`tests=457211ab5c0e8a3af82a794e6721f37fe210a44d`、`scripts=feed234ba658861377a6279598cc0243cdc3b5d8`、
`examples=c0dbdbba6ba52f7a1284d68677ee356413b722e7`。依赖声明和锁文件未变。
独立 wheel 验收的临时目录退出后自动清理；上列 /tmp 单独示例是非版本化材料，不保证永久保留。
初次测试发现 argparse 泛型注解在运行时求值导致 CLI 导入失败，已改为延迟注解；最终完整检查与 wheel 验收均通过。

## Open items and blockers

- None：C01–C03 和本次维护整理已完成。运行预检、真实执行、结果关联、大数据存储适配及 Web 接入仍属于后续批次。

## Next steps

- 提交任务分支供审查；未推送或合并。后续 D01–D02 消费冻结 TaskReference，完成执行预检与持久提交意图。

## Compatibility and rollback

- 控制库 schema 1/2 首次写入事务升级为 3；只读不升级。旧研究 JSON/digest、Project 身份和 Task manifest schema 1 保持不变。
- 新增 compiled_tasks 表；rebind 更新 Project 路径和元数据 revision，不改研究 revision。LocalProjectStore 的现有服务调用方式保留。
- 使用前备份外部控制状态与工作区；旧 A/B 程序拒绝 schema 3，回退需同时恢复升级前备份，不能只改 user_version。
- 没有改变全局 Agent 配置、现有 Web catalog 或执行环境。任务记录完成不意味着 main 已集成。
