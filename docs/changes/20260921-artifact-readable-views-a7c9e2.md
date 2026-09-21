---
record_version: 1
task_id: "20260921-artifact-readable-views-a7c9e2"
title: "为 Agent 提供可读、可分页的实验产物接口"
branch: "fix/artifact-readable-views"
base_commit: "f3f11068873007ac72d01338e560570842e8cb48"
work_status: completed
updated_at: "2026-09-21T16:54:31+08:00"
pull_request: null
---

## Goal and acceptance

- MCP artifact_read 默认读取文本而非 Base64；支持有界分页、中文边界、明确 EOF/续读位置。
- 图片使用 MCP 标准图片内容或可读取资源链接；二进制默认仅元信息与下载引用，显式 Base64 仍可用。
- 不改 Records 原始数据；保留现有 HTTP/Web/CLI 文件下载兼容性和 Run/产物/项目访问边界。
- 覆盖文本分页、非法参数、二进制、图片、MCP 协议、旧下载和访问隔离的测试；相关静态检查和构建通过。

## Changes

- RunQueries 共用成员授权与定位；runs/_artifact_view.py 提供有界 UTF-8/原始字节分页、类型识别、摘要及下载引用。
- MCP artifact_read 默认 auto：文本直读；不超过 1 MiB 的 PNG/JPEG/WebP 使用 ImageContent；其他二进制和大图片提供元信息与可解析资源链接。
- 科研 CLI 新增 --format/--offset/--limit；Web、HTTP 与 run artifact --output 保持整文件下载行为。旧 Controller 版本给出明确重启提示。
- 新增 25 项读取/协议测试，更新宿主机科研接口参考和实现导读。项目进度未改：这是现有读取能力修复，无新增执行后端或阶段变更。

## Decisions

- 延续上轮 [执行引导修复](20260921-research-execution-guidance-f24a8c.md) 的分支基线，不包含合并或推送。
- 按 MCP 标准内容类型实现；新 Agent 阅读接口与旧整文件下载兼容，不迁移数据或启动实验。
- 本轮不改容器实时工作区和 Job 日志接口，不实现大文件流式下载服务。
- 文本默认 16 KiB，最大页 64 KiB，按实际 UTF-8 字节数续读；不伪造无效编码。显式 Base64 同样分页。
- 原文件仍按 Records 保存；资源和整文件下载仍限 16 MiB。图片使用签名识别，文件后缀本身不足以触发原生图片响应。
- 采用 MCP 2025-11-25 标准 TextContent/ImageContent/ResourceLink 与资源读取，使用仓库锁定的 SDK 1.26.0；没有依赖升级或自定义会话解码脚本。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| uv run --locked pytest -q tests/unit/runs/test_artifact_views.py tests/unit/runs/test_artifact_mcp.py | f3f1106 + 本任务工作区 | passed | 25 项；中文/emoji 分页、空文件、错误编码、二进制、超 16 MiB 分页、可见性、真实协议和下载兼容 |
| make verify | 同上，最终图片类型条件修订前 | passed | 297 passed / 23 deselected；Python/TS 静态检查、依赖边界、文档、wheel/sdist 与 Web 构建通过 |
| uv run --locked pytest -q tests/unit/runs/test_artifact_mcp.py | 本任务最终代码工作区 | passed | 4 项；追加伪装图片后缀场景；MCP → 真实 HTTP/绑定 Controller → Records，执行后端未调用 |
| make check；uv build；git diff --check | 本任务最终代码工作区 | passed | 最终代码静态检查、文档链接、格式及打包通过；SDK 有一条非失败的 lifespan forward-reference warning |
| 只读获取用户给出的归档 summary.json，再通过新视图解析 | 本任务最终代码 + 已运行的旧 Controller 下载接口 | passed | 1773 字节；text 与原始字节一致、JSON 可解析、eof=true、无 content_base64；未输出实验详情或改写记录 |
| 新版本常驻服务部署、真实 Codex 视觉/工具调用、Docker/GPU 实验 | None | not_run | 本轮不重启用户服务、不调用模型、不运行实验；不能把协议测试称为真实模型验收 |

## Open items and blockers

- None（实现与约定验证完成）。大文件整份下载、非 UTF-8 自动转码不在本轮范围。

## Next steps

- 用户结束并归档当前实验后，用新版本重启 Controller 并重新连接 MCP；旧会话和进程不会自动更新。本轮不合并或推送。

## Compatibility and rollback

- MCP/科研 CLI 默认内容变化；显式 format=base64 保留编码读取但按页返回，旧整文件下载接口不变。Controller/MCP 须一起更新。
- 无数据迁移；回退代码可恢复原接口行为。
