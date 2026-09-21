---
record_version: 1
task_id: "20260921-execution-timeline-usability-f71a6c"
title: "改善 Web 科研运行时间线的浏览体验"
branch: "feat/execution-timeline-usability"
base_commit: "6bac44ab6f947d732ffb6e8742ea2f149ce2187f"
work_status: completed
updated_at: "2026-09-21T18:19:52+08:00"
pull_request: null
---

## Goal and acceptance

- 让真实科研 Run 的资源、容器、实验 Job 与重复查询更容易区分；所有已公开的事件仍可查看。
- 前端支持重点/全部筛选、请求耗时和直观状态；分页可返回上一页且切换 Run 不沿用旧页游标。
- 不扩大后端可见字段或读取私有数据；桌面与窄屏布局可用，相关检查通过。

## Changes

- 运行页增加重点/全部/工具调用/Agent 筛选、每页计数、最近刷新时间、上一页/下一页导航；切换 Run 重置游标。
- 工具请求与响应显示耗时；实验 Job、失败和采集缺口用中文状态及视觉提示，保留展开安全字段。
- Run 列表和详情翻译常见生命周期/执行状态，明确“已结束”不表示成功；增加窄屏可换行的筛选与事件布局。
- 补充无浏览器依赖的时间线逻辑测试和浏览器夹具断言，更新 Web 操作说明。

## Decisions

- first-study 当前共有 48 条事件，合并后约 26 项，其中 6 次产物读取、3 次状态查询等会掩盖实验启动与完成；优先在现有安全摘要上整理。
- 本任务只改 Web 展示，不增改 Records/Run API 或采集语义。
- 默认重点视图只收起常规 `read/list/logs/status/artifact/artifacts/events/trajectory`，失败和采集缺口不会被收起；“全部”仍可见原有公开摘要。筛选作用于当前事件页，不宣称全 Run 统计。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| first-study 原 Attempt 的事件类型只读统计 | 6bac44a + 用户状态目录 | passed | 48 条事件；22 对工具调用/结果，合并为 26 项；按本轮规则，重点视图显示 11 项，Agent 事件为 0 |
| `pnpm check`、`pnpm build` | 本分支实现快照 | passed | Biome、TypeScript 与 Vite 构建通过；最终只另做等效渲染整理并复跑 `pnpm check` |
| `node --experimental-strip-types --test tests/web/execution-trace.test.mjs` | 本分支最终工作区 | passed | 3 项通过：重点/全部/Agent、配对与耗时、常规查询失败保留 |
| `uv run --locked python scripts/ci/check_repository.py`、`git diff --check` | 本分支工作区 | passed | 文档链接与差异检查通过 |
| `node tests/web/console.smoke.cjs` | 本分支工作区 | not_run | 本机未安装可选 Playwright 包；没有浏览器视觉验收，HTTP/Records API 未修改 |

## Open items and blockers

- 本轮仅优化已持久化摘要；完整宿主机 Agent 原生轨迹仍需采集源数据，不能由前端推断。
- 更大规模 Run 的跨页全局搜索/筛选、日志与事件的安全跳转需要后端查询契约，另立任务处理。
- 本机缺少 Playwright，浏览器窄屏视觉回归未执行。

## Next steps

- 审查并合并分支；部署更新的 Web 资产后，用 first-study Run 实际查看重点与全部两种视图。

## Compatibility and rollback

- 仅前端展示；回退本分支提交即可恢复旧页面。原有记录、HTTP API 和运行环境不变。
