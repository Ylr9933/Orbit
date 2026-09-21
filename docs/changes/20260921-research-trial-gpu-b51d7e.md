---
record_version: 1
task_id: "20260921-research-trial-gpu-b51d7e"
title: "首次科研试用指南与 GPU 能力边界说明"
branch: "docs/research-trial-gpu-boundaries"
base_commit: "c4b4bb7ac2e8deea673096752ddd938bee8efe82"
work_status: completed
updated_at: "2026-09-21T10:41:51+08:00"
pull_request: null
---

## Goal and acceptance

- 将上一轮当前功能与首次科研试用操作整理到 operations 文档；命令与实际入口一致。
- 结合代码及官方资料解释 GPU 可见性、分配、依赖与训练代码的职责，明确已实现和待接通的边界。
- 文档导航和本地链接检查通过；本轮不修改产品代码、不执行训练、不修改宿主机 GPU 配置。

## Changes

- 新增 [首次科研试用指南](../operations/first-research-trial.md)，保留上一轮功能表、初始化、Controller、Codex MCP、两阶段提示词、Web、验收与文件同步边界。
- 同一文档附 GPU 分层解释、源码入口、Docker/PyTorch 示例和最小接通建议；明确 CPU 入口与已有底层 GPU 能力。
- 更新 docs/README.md 导航；项目能力未变，project-status.md 不变。

## Decisions

- 从 main 建文档分支，保留上一轮试用流程并附 GPU 解释；不将底层参数能力标为已验收产品功能。
- 使用 NVIDIA 与 PyTorch 官方资料校对平台之外的 GPU 条件；不需要新增模型调用或 GPU 占用。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| Git 状态与代码阅读 | c4b4bb7 | passed | 起始工作区干净；Controller 未设置授权 GPU，Docker backend 已有 --gpus 参数 |
| `uv run --locked python scripts/ci/check_repository.py`、`git diff --check` | c4b4bb7 + 本任务文档 | passed | 本地 Markdown 链接、规则镜像、空白检查通过 |
| CLI help 核对与示例语法解析 | c4b4bb7 + 本任务文档 | passed | init/research skill/controller serve/mcp/web 及 codex mcp add；Bash 使用 bash -n、Python 使用 ast.parse，不执行示例 |
| Controller/Resources/Docker/MCP 源码核对及 NVIDIA/PyTorch 官方资料 | c4b4bb7；2026-09-21 | passed | GPU 允许列表未接入，长期环境缺 GPU 参数；后端已有设备选择/映射；外部资料链接随正文 |
| GPU / Docker / 模型实际运行 | None | not_run | 本轮仅文档与解释；不声称 GPU 已实测 |

## Open items and blockers

- None；GPU 接通建议属于后续开发，未在本次实施。

## Next steps

- None（本轮文档与解释完成）；分支待审查，未合并或推送。

## Compatibility and rollback

- 仅文档，无接口、运行配置或数据变更；可回退文档提交。
