---
record_version: 1
task_id: "20260918-project-init-72a94b"
title: "Implement practical local project initialization (A00–A07)"
branch: "feat/project-init"
base_commit: "f64d904a0595f52f8cca868f0c829cfa5c42dd91"
work_status: completed
updated_at: "2026-09-18T19:12:41+08:00"
pull_request: null
---

## Goal and acceptance

- 实现 A00–A07：ADR、最小 Project、持久存储、模板、预览、目录创建、幂等恢复、CLI 和安装验收。
- `agent-infra init` 支持指定目录、名称或自动生成目录；保存原始目标，不调用模型。
- 不覆盖已有目录或用户编辑；支持跨进程查询、重复请求和初始化中断恢复。
- 定向测试、`make verify`、独立 wheel 安装 smoke 均通过；更新使用说明和项目概览。

## Changes

- 新增 `projects/`：独立 ID、schema/revision 校验、SQLite 元数据、包资源模板、本机初始化与恢复。
- 新增 `init` 与 `project init/preview/show/list/recover`，参数解析和 bootstrap 组装各自保留原有边界。
- 创建 docs/code/configs/data/runs/artifacts，保存用户原话和待讨论内容，不生成虚构研究结论。
- 自动解析用户默认状态路径的已有链接，兼容本服务器将 ~/.local 迁至数据盘；显式路径仍执行严格检查。
- 覆盖进程退出、跨进程初始化和 revision 竞争、不同 store 的目录竞争、符号链接与编辑冲突。
- wheel smoke 在仓库外验证预览、创建、重试与重新读取；README、命令参考、计划、导航和项目概览同步更新。
- 将过长且已过时的项目概览收敛为能力、缺口和三项优先级，保留原有未完成事项和验收限制。

## Decisions

- 以实用为先：本地 SQLite、包内模板、同步初始化，不引入服务、模型或工作流引擎。
- 采用[初始化 ADR](../adr/20260918-project-initialization.md)；状态根与科研目录分离，默认固定用户级状态路径。
- 先保存请求和完整生成快照，再写暂存目录，最后原子发布；不接管已存在的空目录，不提供 force。
- ready 项目重试不重写科研文件；pending 存在编辑冲突时停止恢复并保留现场。
- 一次交付 A00–A07，以现有计划分支为基线；旧 Web catalog 不迁移，后续 W01 适配。

## Validation

验证快照为本次提交的代码与测试，Git 子树 ID：
`src=271ad275cd0575f8f162b41afbd116bb2cb4ffe2`、
`tests=320850b2d280356f6e798ff30c444ad20260676d`、
`scripts=c246fdfe4d17fc850bfc9e2cc7688f8f1c22a505`。

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `uv run --locked pytest tests/unit/projects -q` | 初版 35 用例工作区 | passed | 初始化、原话保存、重开、路径保护、进程退出与并发 CAS；后续补充用例由全量检查覆盖。 |
| 同一定向命令，增加 3 项测试后 | 中间工作区 | failed | 37 passed / 1 failed；新增测试错误导入不存在的 gateway main，已改为执行真实 CLI。 |
| `make verify` | 上述最终代码快照 | passed | Ruff、Mypy、依赖方向、TypeScript/Biome、文档检查通过；155 passed（含 39 项 Project 测试），7 E2E deselected；Python/Web 构建通过。 |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 同一快照构建的 0.1.0 wheel | passed | 临时 venv、仓库外预览无写入、创建、保留用户编辑的重试、切换目录后查询；模板随安装包可用。 |
| `git diff --exit-code -- uv.lock pnpm-lock.yaml` | 本次工作区 | passed | 无新增第三方依赖，锁文件不变。 |
| `git diff --cached --check`、暂存差异审查 | 本次工作区 | passed | 仅任务相关代码、测试、文档及构建验收脚本，无运行数据、凭据或用户项目。 |
| `uv run --locked agent-infra project list` | 最终代码，本服务器真实用户默认路径 | passed | 返回空项目列表和数据盘上的状态路径；只读检查未创建状态。 |
| 真实 Agent / Docker / GPU / 多节点 | None | not_run | A00–A07 无这些依赖，不属于本轮验收；没有消耗模型预算或占用实验资源。 |

## Open items and blockers

- None：本轮初始化范围和验收已完成，无实施阻塞。
- 研究规划、Task 编译、实验运行、MCP 和 Web catalog 适配不在本轮范围，仍按后续任务推进。

## Next steps

- 本轮授权实现已完成，尚未发布 PR 或合并；下一开发项建议 B01：带来源和 revision 的 Research Brief。

## Compatibility and rollback

- 新增命令和 Projects 存储；已有 Agent/Task/Resources/Records/Web 行为及旧 Project catalog 保持兼容。
- Linux 本地文件系统、单管理员；显式路径拒绝链接和父目录跳转。不支持 NFS 多机控制库、工作区移动或已有项目导入。
- Project 命令默认用户级状态根，与旧 config-check 的 ./var 默认不同；显式 --state-dir 或环境变量可统一。
- 回退代码不会删除用户工作区或外部 SQLite 状态；保留两者备份。后续版本升级须显式处理 schema 兼容。
