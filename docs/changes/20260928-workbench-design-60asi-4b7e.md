---
record_version: 1
task_id: "20260928-workbench-design-60asi-4b7e"
title: "基于 60 条 ASI 真实结果的实验工作台调研与离线原型"
branch: "docs/experiment-workbench-design-20260928"
base_commit: "bd65d72bb7dc481affa09721473d0cb47595bf6c"
work_status: completed
updated_at: "2026-09-28T19:33:27+08:00"
pull_request: null
---

## Goal and acceptance

- 调研简洁、美观、实用的实验工作台，核对现有前端与真实结果，提出页面设计和实施顺序。
- 提供可审阅的中文方案与离线交互原型。后续用户要求将两者归档到项目并合并；归档与检查已完成；Git 写入限制已解除，集成事实以 Git 历史为准。生产前端改造、真实重跑、部署不属于本轮范围。
- 原型中的结果必须与现有 60 条记录一致，不虚构比较基线、轨迹正文或执行成功。

## Changes

- [设计方案](../product/experiment-workbench-design-20260928.md)与[离线原型](../assets/experiment-workbench-20260928.html)已放入项目，更新[文档导航](../README.md)与相互引用。
- 原型包含实验列表、结果筛选与排序、分页、分布、任务详情、文件清单、CSV 导出、重跑配置预览和比较空状态；HTML 与已检查的临时原型内容一致。
- 未导入独立 data.json、临时校验脚本或浏览器缓存；原型内嵌精简结果快照，不包含运行日志、任务产物正文或认证数据。
- 未修改正式前端、运行数据、服务或项目概览。

## Decisions

- 参考 Primer、Carbon、W&B、Langfuse 和 WCAG 的官方材料；来源和具体取舍见设计报告。
- 先落地 U1 页面/视觉与 U2 单任务复盘，再做 U3 比较和 U4 持久重跑，最后 U5 真实小任务验收。
- 基于既有 React/TypeScript 组件与后端边界重组，避免平行实现。
- 0 分是有效得分；运行时限、外层预算、实测耗时分别展示。
- 原型只含结果元数据和文件清单，不含凭据、原始消息正文和模型调用。
- 初期因 `.git` 只读，先归档到非 main 工作区；用户调整会话权限后，已成功创建独立设计分支。本任务提交单独移至 main 基线，不包含 ASI 结果整理分支的其他历史。调研代码快照仍为 54165f5，与 main 的差异仅是既有 ASI 文档记录。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| 阅读项目状态、文档导航、相关任务记录及前端/服务源码 | 基线 54165f5 + 未修改工作树 | passed | 设计报告给出组件与服务证据 |
| 对照 summary.json 的任务标识、run_id、分数和状态 | data.json + 原始 60 条结果 | passed | validate.cjs 逐项匹配全部 60 条；唯一性和均分检查通过 |
| node --check /tmp/agent-infra-workbench-design-20260928/prototype.js | 最终 index.html 提取脚本 | passed | Node 24.18.0，无语法错误 |
| node /tmp/agent-infra-workbench-design-20260928/validate.cjs | 最终 index.html 提取脚本及 data.json | passed | 搜索、领域、零分/满分、排序、CSV、HTML 转义通过；Node VM 测试，不是浏览器交互测试 |
| Python 检查内嵌 JSON 与 data.json 一致及外部脚本/样式引用 | index.html | passed | 60 条记录一致；无外部脚本或样式依赖 |
| Chromium headless 截图 | 离线原型 | failed | 启动被沙箱阻止，setsockopt: Operation not permitted；没有生成有效截图 |
| 实际浏览器桌面/窄屏、键盘与视觉检查 | 离线原型 | not_run | 浏览器启动失败；响应式 CSS 不构成视觉验收证据 |
| git status --short --branch | 归档前 | passed | 非 main 分支，初始工作树干净 |
| 归档校验：HTML 字节一致、Markdown 本地链接、node --check、git diff --check | 本任务归档工作区 | passed | 原型与已检查版本字节一致；60 条内嵌记录；新增本地链接和脚本语法通过；diff 无空白错误 |

## Open items and blockers

- 归档工作无剩余阻塞；Git 权限限制已解除。
- 真实浏览器视觉与交互验证仍未完成；原型只用于设计评审，不代表可上线前端。

## Next steps

- 文档归档已完成；提交和合并状态以 Git 历史为准。本轮不推送远端。
- 后续正式开发按 U1/U2 开始，在可启动浏览器的环境进行视觉与交互验收。

## Compatibility and rollback

- 没有修改公共接口、运行数据或部署。原型的重跑按钮不会发起真实任务。
- 回滚仅需撤销本任务四个文档文件的变更；不涉及模型、容器或运行状态。
