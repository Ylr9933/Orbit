# Benchmark 实验工作台

状态：`feat/benchmark-web-workspace` 的实现说明；集成事实以 Git 为准。面向本机单管理员，复用现有 Batch、Run、Records；不启动模型，不改变原生评分。

## 打开与登记

先按 [Web 控制台说明](web-console.md)安装并构建前端，再启动独立 Web：

```sh
pnpm build
uv run --locked agent-infra web --state-dir /absolute/path/to/console-state
```

打开服务输出的本机访问地址，进入 Benchmark。默认显示这个状态目录内的 Benchmark Run，按候选配置分组。点击「登记已有批次」，填写包含 `batch.json` 的**服务器绝对目录**。批次可以来自不同状态目录；登记会验证清单和冻结执行计划，不复制运行数据、不提交作业。最多登记 100 个目录，目录及状态路径不接受符号链接。

登记信息、名称、笔记、项目标签和默认基线保存在 Web 状态目录的 `benchmarks/console/workspace.sqlite3`。批次的 `state/benchmarks` 和原始 Records 仍是执行证据来源。移动已登记目录会显示读取错误，应登记其新位置；不要为消除错误而删除执行状态。数据库中的笔记单独备份，和原批次目录一起保存即可恢复工作台。

## 一次完整复盘

1. 登记基线和新版批次，选择基线并点击「设为基线」。给新版写清名称、改动说明和研究项目。
2. 选择指标，查看完成数、有效评分覆盖、趋势及逐题对比。支持越大/越小越好的指标方向，按退步、提升或任务名排序。
3. 搜索退步题，点击「并排查看轨迹」。两侧分别搜索、筛选和翻页；只有明确调用 ID 的工具请求与结果才配对，缺少关联时保留原始步骤。
4. 使用「定位错误」、搜索命令或输出，复制具体步骤链接。文件页可查看代码、JSON、CSV、图片与原生评分产物，下载原始记录。
5. 保存任务笔记，导出逐题 CSV、对比 CSV、Markdown 摘要和 SVG 图表。配置页可查看/复制冻结候选、参数、版本、资源与预算；Web 不会因为复制配置而创建或执行新 Run。

任务列表每页 50 条，所有冻结成员包括尚未提交的任务均可查询。任务详情有前后切换；筛选失败、未评分、排队和运行中的任务可以减少逐页查找。

## 如何解释图表

- 单批次均值是当前有效评分的**描述性统计**，不是原生套件或官方分数。未评分、失败、取消不默认补零；原生有效零分保留。
- 趋势只纳入同任务集合、材料与评分版本、且每题都具有所选有效指标的批次。横轴是批次时间顺序，不是不同题的完成顺序。重复任务的多次尝试不进入趋势。
- 两批次比较使用同任务且材料/协议一致的有效评分交集，同时显示覆盖分母。重复尝试、缺失题、评分无效和协议不同都有原因，不会偷偷选择最佳尝试。
- 模型、提示参数和预算可以作为实验变量变化，配置差异可展开检查；它们不同不表示同预算对照。不同任务集或未完成批次的单批均值不可直接当成性能提升。
- 本轮没有自动调用各 adapter 的原生套件聚合，也没有统计显著性或官方提交功能。多 seed 统计仍应遵循各 benchmark 的协议。

## 日志、轨迹和取消

页面会提示观察到的批次完成变化；可显式开启浏览器完成通知。页面关闭时不提供后台通知服务。

运行日志展示 worker 已写入 Records 的 combined stream 最后 64 KiB，可暂停显示更新。它不是容器实时 stdout 直连；worker 未推进时没有新日志。读取页面不推进队列、不恢复/重启任务。

规范轨迹在归档后可用。优先读取不超过 16 MiB 的完整 ASI 规范轨迹，否则使用已归档的有界视图；搜索范围与截断状态明确标示。Harbor 等适配器只要提供同一证据投影即可显示，不按 benchmark 名称建立另一个页面。每步展示上限 64 KiB；文件预览上限 1 MiB、下载上限 16 MiB。超过限制的原始产物仍可用 Records CLI 导出。原生实时 token 流、完整 ATIF 结构解析和跨页调用配对不是本轮能力。

「取消此任务」仅保存已有 Run 的取消意图，由对应批次的 worker 处理清理。任务结束前仍会显示待处理；不会清理其他任务或自动重试。批次停止后续提交、重新执行和创建新配置仍通过已有 CLI，见 [批量运行](asi-bench-batch.md)。

## HTTP 与维护入口

所有路径在 `/api/v1/benchmarks/workspace` 下，沿用 loopback Host 校验与 Bearer 认证：

| 路径 | 方法 | 用途 |
| --- | --- | --- |
| `/`（无尾斜杠） | GET / POST | 批次索引 / 显式登记目录 |
| `/{batch}` | GET | 全部冻结成员、当前结果与笔记 |
| `/settings` | POST | 保存默认基线，带 revision |
| `/{batch}/note?unit=...` | POST | 批次或任务笔记；乐观版本检查防覆盖 |
| `/compare?left=...&right=...&metric=...` | GET | 逐题可比性及共同有效样本统计 |
| `/{batch}/runs/{run}/detail` | GET | 配置、状态、评分与资源 |
| `/{batch}/runs/{run}/trajectory` | GET | cursor/limit/search/kind 查询归档轨迹 |
| `/{batch}/runs/{run}/files?member=...` | GET | 文件清单或有界 Base64 内容 |
| `/{batch}/runs/{run}/logs` | GET | 已提交日志尾部 |
| `/{batch}/runs/{run}/cancel` | POST | 保存取消意图 |

成员文件通过该 Run 自有 artifact manifest 与 Records blob 引用读取，不接受宿主机任意文件路径。私有评测、凭据与 secret 类 artifact/stream 不通过这些入口提供。笔记使用独立表和 revision；更新冲突需要刷新核对后保存。

源码分工：`projects/benchmark_workspace.py` 保存用户元数据；`runs/benchmark_views.py` 提供纯投影/比较，`runs/benchmark_evidence.py` 读取有界证据；`bootstrap/benchmark_workspace.py` 组装状态与 Records；`features/benchmark/` 分离结果、比较、图表、笔记和证据阅读组件。不引入图表库、第二套执行器或独立前端状态管理依赖。

## 验证范围

后端测试覆盖 60 题成员、缺失/无效/零分、协议差异、重复任务、登记完整性、Run 归属、搜索、笔记冲突、取消意图和日志提交边界。浏览器测试使用明确的合成数据，经过真实 HTTP 和 Records 读取路径，检查桌面/390px 手机布局、刷新、导出和步骤链接；不代表新模型或原生 benchmark 验收。

```sh
uv run --locked pytest tests/unit/benchmarks/test_workspace.py
node --test tests/web/benchmark.test.mjs
# 使用已有本机 Playwright/Chromium；服务和数据由脚本创建在临时目录。
PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome \
node tests/web/benchmark.smoke.cjs
```

详见 [本轮任务记录](../changes/20260926-benchmark-web-4f82c1.md)。
