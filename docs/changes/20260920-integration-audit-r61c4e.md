---
record_version: 1
task_id: "20260920-integration-audit-r61c4e"
title: "模块衔接检查、代码整理与后续实用性计划"
branch: "refactor/workflow-integration-audit"
base_commit: "393757b250a165382c2d510cd0ea4922b61f2a3e"
work_status: completed
updated_at: "2026-09-20T20:10:21+08:00"
pull_request: null
---

## Goal and acceptance

- 检查 Projects → Tasks → Resources/Environment → Run/Agent → Records → Web/CLI/MCP 的实际衔接，修复可复现问题。
- 收拢重复的状态配置、上下文与可见性，清理无用占位，保持公共接口、历史数据和模块边界。
- 工程回归、浏览器、限定本机 CPU 的无模型 Docker 集成通过；交付不足与下一步细分计划。
- 实现阶段不新增 GPU/分布式/模型验收、不修改治理规则；用户随后明确授权合并到 main 并推送两个远端。

## Changes

- `bootstrap/paths.py` 统一状态根与私有 Controller 目录准备；修复 Web-first 导致之后 Controller 拒绝启动；Web CLI 保留具体启动失败原因。
- config-check 默认值与 Project/Controller/Web 对齐；显式路径统一拒绝符号链接和上级跳转，用户默认目录仍允许解析迁移后的 ~/.local。
- ResearchService 注入运行查询；CLI、Web、Analysis/Planner 使用同一上下文接口。新增 Controller store 只读模式，规划读取不再执行建表/迁移或 chmod。
- Records 拆出内部 sink、序列化和 legacy writer，保留旧 LocalRunJournal 导入。抽取共享可见性，修复 ADMIN 事件进入轨迹/导出的遗漏。
- 删除 10 个已有实际文件目录内的 `.gitkeep`；保留空的未来模块占位。
- 补充跨入口、私有过滤、兼容 API 和真实 Web-first Docker 回归；更新研究/Records/运维说明。
- 新增[代码检查和后续计划](../development/20260920-integration-review.md)，压缩并更新[项目概览](../project-status.md)，清楚区分 main 与本分支拟集成能力。

## Decisions

- 实现验收后，用户授权集成并同步 origin（XuehaiWang/agent-infra）与 zjunlpgit（zjunlp/Orbit）。刷新后双方 main 均为 c15f946，支持快进，不重写历史。
- 从 W 创建独立整理分支，沿用 H/E/I/W 工作，不在 main 开发；实现验收时 main 为 `c15f9469aa10e40f76dc2b6155bdab5026336ee5`。
- 不以仓库内引用数量直接删除兼容 API；AST 比较确认拆出的两个 Records 类与原实现一致。
- 可见性规则统一，但底层 RecordsReader 继续允许可信组件读取原始证据；这不是多用户授权系统。
- 真实 Docker 仅本机串行，同时总请求最多 1 CPU/2 GiB，无 GPU/模型，目标 15 分钟内，使用已有镜像，清理只限测试资源。
- 使用已有 `python:3.12-slim`（本机镜像 ID `sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`）。
- E 环境准备本轮选择已有 Python 镜像 smoke/锁引用路径；另外 5 个 E2E 未重跑：下载包修复、安装中断恢复、已有 Codex 镜像验证和两项构建取消/超时。此次未修改构建实现，不据局部回归宣称完整环境构建重新验收。

## Validation

最终代码快照（Git subtree，可与交付 commit 的子树核对）：

- `src`: `59b12a714ec81d8536228b7cced5ed3dbbd9397c`
- `tests`: `3e502a1a455d0d79419999f3e45faa399ac78511`

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| 集成前双远端刷新、祖先关系和代码/测试子树核对 | c22fd80 | passed | 两端 main 与本地同为 c15f946；源码和测试与上方已验证快照一致；未设置保护，无已知要求检查被绕过 |
| Git、模块入口和近期验证核对 | 393757b | passed | 起始工作区干净，main 未修改 |
| Web-first 临时目录复现 | 393757b | failed | 旧顺序将父目录创建成普通权限（本机 0775），不满足 Controller 启动检查；已修复 |
| 第一轮局部回归 | 修复中的工作区 | failed | 旧默认路径/异常类型断言需同步，新增过滤测试的 JSON datetime 编码需修正；后续完整回归覆盖通过 |
| `make verify` | 上述 src/tests | passed | Ruff、mypy（118 源文件）、依赖图、前端类型/格式、文档镜像/链接、272 非 E2E、Python/Web 构建；23 E2E 排除；1 条既有 MCP/Pydantic 弃用警告 |
| `pytest -q -m e2e tests/e2e/test_web_research.py`（uv locked） | 上述 src/tests | passed | 1 项，10.79 秒；真实 Web/Controller/Docker，结果归档、分析、下载、Controller 离线历史读取 |
| 下方限定 Docker 回归命令 | 上述 src/tests | passed | 17 项，192.96 秒；真实隔离、清理、中断恢复、MCP、环境锁、两轮确定性 Planner；无模型 |
| `node tests/web/workflow.smoke.cjs` | 上述 src/tests + 本次 Web build | passed | 实际浏览器；旧绑定、新建、编译、预检失效、响应丢失重试、刷新/取消、指标下载/分析、移动宽度；执行后端为显式替身 |
| `node tests/web/console.smoke.cjs` | 上述 src/tests + 本次 Web build | passed | 实际浏览器；旧页面、项目编辑/关联、轨迹、私有过滤和本机资源采样 |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 上述 src/tests 对应构建 wheel | passed | 独立安装/目录下 CLI、Projects、编译与资源；临时证据 `/tmp/agent-infra-wheel-x4__rnm7/compilation-acceptance/acceptance.json` |
| 拆分类 AST 对比、`git diff --check`、最终文档检查 | 最终工作区 | passed | 两个拆分类与基线完全一致；链接/镜像无误，无空白错误 |
| Docker/进程清理检查 | 集成测试后本机 | passed | 原有三个 rsi-infra 容器 ID 不变，无测试 Controller/Web fixture 留存 |
| 实际模型、GPU、两节点、原生 benchmark、上述 5 个 E 用例 | None | not_run | 不在本轮资源范围；不据此宣称这些能力已验收 |

17 项 Docker 回归的实际命令：

```bash
uv run --locked pytest -q -m e2e \
  tests/e2e/test_run_environment.py \
  tests/e2e/test_host_research.py \
  tests/e2e/test_controller_recovery.py \
  tests/e2e/test_study_controller.py \
  tests/e2e/test_research_mcp.py \
  tests/e2e/test_iteration_planner.py \
  tests/e2e/test_environment_controller.py::test_cli_plan_mcp_validation_and_locked_research
```

浏览器使用本机已安装 Playwright，通过 `PLAYWRIGHT_MODULE` 与 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指定路径；未增加仓库依赖。
日志保留在本机 `/tmp/audit-verify.log`、`/tmp/audit-web-docker.log`、`/tmp/audit-docker.log`、
`/tmp/audit-browser-workflow.log`、`/tmp/audit-browser-console.log`、`/tmp/audit-wheel.log`，不作为长期存储承诺。

## Open items and blockers

- 本轮范围内 None。产品未实现项和小任务验收要求见[检查与计划](../development/20260920-integration-review.md)。
- 未配置常驻部署；本次授权集成包含 H/E/I/W 与本轮代码，实际合并和远端同步结果由 Git 历史确认。

## Next steps

- 本轮实现与检查已完成；按用户授权快进 main 并普通推送两个远端，核对三个 main 的提交一致。
- 后续优先做安装与状态诊断、长期启动/备份指南、一个实际科研项目；随后围绕 GPU/镜像/数据需求推进。

## Compatibility and rollback

- 无数据库 schema 或依赖版本改变，不删除项目/运行数据；LocalRunJournal 的旧导入仍兼容。
- config-check 无参数默认从 cwd/var 改为用户状态目录；显式 TOML 的 ./var 保持原意，运行入口仍通过参数/环境选择目录。
- 显式状态路径统一拒绝符号链接；已有 Controller 目录若权限过宽，核实归属后手动设 0700，程序不会静默修改。
- Web 不再列出 controller-only Artifact；仍可通过可信本地 Records API 维护。轨迹 builder 升为 2.0.1，schema 不变，重新派生 ID 改变，已有导出不重写。
- 可通过后续任务回退代码，无需数据迁移；回退会重新引入已修复的启动和 ADMIN 过滤问题，应保留对应修复或前移补丁。
