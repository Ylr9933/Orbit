---
record_version: 1
task_id: "20260922-infra-six-optimizations-c83e2a"
title: "科研与榜单基础设施现状审查及六项优化实施计划"
branch: "docs/infra-six-optimizations"
base_commit: "57c8e4da0a9774cd149715424ee172aa143760ef"
work_status: completed
updated_at: "2026-09-22T15:37:26+08:00"
pull_request: null
---

## Goal and acceptance

- 将本次代码审查整理为中文详细文档，区分已实现能力、可复现问题、现有限制和拟议方案。
- 展开六项优化：执行内核、持久调度、原生 benchmark 协议、大产物、雇主 Agent、实验身份与结果比较。
- 每项说明代码落点、接口职责、实施步骤、失败处理、兼容迁移及可检验的验收要求，并给出依赖顺序与独立交付切片。
- 文档链接与政策镜像检查、空白检查通过；核对源码引用和既有证据。不实现运行时功能，不执行真实 Docker/GPU/模型/榜单任务。

## Changes

- 新增[六项优化实施计划](../development/infra-six-optimizations-plan.md)：12 个章节覆盖源码基线、现状矩阵、三项故障复现、六项优化的接口/步骤/失败行为/迁移/验收，以及依赖图和 14 个独立工作包。
- 在文档导航的“当前代码检查”加入入口；明确方案尚未实施，运行时缺陷尚未修复。
- 项目概览不变：本任务交付分析与实施计划，不改变已集成能力或阶段验收状态。

## Decisions

- 从本地 main 的 `57c8e4d` 建立独立分支和相邻工作树，保留原工作树的 benchmark v0.2 文档及 ADR；不复制、提交他人改动。交付复核时该工作已在原分支提交为 `0c8527b`，本地 main 仍为 `57c8e4d`。
- 新文档是面向开发的横向实施计划；既有 20260920 整理记录保留为历史，未合并 benchmark 专题设计在相关实现开始前对齐。
- 上一轮只读审查在 `7841d23` 上执行；当时源码、测试与 `57c8e4d` 相同。308 项测试和故障注入结果作为该次审查证据引用，不声称本次文档编辑重新完成真实环境验收。

## Validation

文档快照 SHA-256（不包含本记录自身）：

- `docs/development/infra-six-optimizations-plan.md`: `760016f5e27e814d7858c888047c4aa9b8008e8f7e77e9d519baf7ccdd4ab5b6`
- `docs/README.md`: `59a5deb8f2ca72472d3d9b37d4157bfe4b0883970ad5d9dfb19b322799375eac`

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git 状态、暂存区、近期提交与 worktree 核对 | 原工作树 `7841d23`；文档分支基线 `57c8e4d` | passed | 独立 worktree `/disk/disk_20T/wangxuehai/infra-six-optimizations-doc`，未改原工作树 |
| `uv run --locked pytest -q -m 'not integration and not e2e'` | 上一轮审查 `7841d23`，源码/测试与基线相同 | passed | 308 passed、23 deselected、1 条 Pydantic 警告；89.09 秒；本轮未重复运行 |
| 临时目录故障注入：stream 元数据更新前抛错并重试 | 同上，上一轮只读审查 | failed | 期望 abc，实际 abcabc；数据库长度 3，blob 长度 6，capture=complete；未修复 |
| 临时环境日志读取/超时产物复现 | 同上，上一轮只读审查 | failed | 真实 observe 方法读取 200000 字节仅归档 65536 且标 complete；替身超时输出存在但未归档；未使用 Docker |
| `/disk/disk_20T/wangxuehai/infra/.venv/bin/python scripts/ci/check_repository.py` | 上述文档快照 | passed | 用既有解释器执行独立工作树中的只读检查脚本；本地链接与 AGENTS/CLAUDE 镜像通过 |
| 只读 Python 结构检查 | 上述文档快照 | passed | 12 节、6 个优化及对应锚点、14 个工作包；围栏成对，无 TODO/TBD/PLACEHOLDER |
| 源码符号、专题设计和文档内容人工复核 | 源码 `57c8e4d`；专题草案 `0c8527b`；上述文档快照 | passed | 对齐模块边界、拟议接口、故障证据、随机评分验收和实施依赖；未把提议写成现有功能 |
| `git diff --check` | 上述文档快照 | passed | 无空白错误；交付前暂存检查覆盖新增文档 |
| 本轮运行时修改、完整工程重跑、真实 Docker/GPU/模型/榜单验收 | None | not_run | 文档范围，无运行时变更；旧测试结果和后续验收要求已明确区分 |

## Open items and blockers

- None（文档范围）。F1/F2/F3 和六项优化均属于后续运行时任务，仍未实施，不因文档完成而视为验收通过。

## Next steps

- None（已完成用户授权的文档交付）。建议后续先立项 WP01–03；本次仅本地提交，不推送、不合并。

## Compatibility and rollback

- 仅新增文档和导航，不改变 API、数据库、依赖、资源配置或历史记录。
- 回退本次文档提交即可；后续运行时优化各自建立任务记录和迁移/回滚方案。
