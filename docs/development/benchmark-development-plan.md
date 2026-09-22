# Benchmark 分阶段实现计划

状态：BM00、BM01、BM02-A、BM02-B 已进入本地 `main`；BM05-A 已在当前任务分支实现并完成
无模型 CPU 安装包验收，待用户检查。BM03 及以后未开启。2026-09-22。

目标：新 bench 使用独立适配包接入；已有执行能力足够时，不修改核心注册表、Run 状态机或通用 CLI。
第一次遇到新的执行形态时，补通用 backend，并单独验收。兼容不等于官方认证，也不保证所有 bench
都有允许优化的反馈或自动提交 API。总体协议见[架构设计](../architecture/benchmark-integration-layer.md)。

| 阶段与顺序 | 具体交付 | 本阶段检查点 |
| --- | --- | --- |
| **BM00：SDK 与接入基础** | 公共版本契约、独立适配包模板、显式启用、包/协议/能力检查、inspect/plan/check、四类合成样例 | 独立 wheel 在干净环境安装后无需改核心；未启用/版本不符拒绝；有序状态、可见性、资源缺省保留；不调用模型 |
| **BM01：受管执行与恢复** | 环境层通用 ExecutionSpec/Handle；Run 持久 operation ID 与 native ID；observe/cancel/reconcile/collect；冻结计划转执行规格 | 丢响应不重复启动；重启先查询；失联隔离；收到清理证据再释放；轨迹复用 Records。先替身及无模型本机进程验收 |
| **BM02-A：TB-Science 独立包** | 固定 Harbor/task 版本；单 CPU 原生 trial；原生 Agent、独立 verifier、reward/轨迹解释 | 原生与平台托管同产物评分对照、取消及无残留；不得在核心按 bench 名分支 |
| **BM02-B：ASI-Bench 独立包** | 固定原生 runner；CPU produce + seed31415 本地 scorer；seed42 bundle/provenance 描述与外部评分边界 | 原生 seed/level/ID 不变；本地分数、正式分数和提交分开；清理不影响其他任务 |
| **BM05-A：长任务前置可靠性** | 最小持久等待队列、资源租约对账与原生 job ID；维持低并发 | 崩溃后不丢等待任务、不超卖；重复提交不重复启动。这部分提前，不能等长任务接入后补 |
| **BM03：PAST-Bench 独立包** | 完整原生 family/配对序列；先接原生支持的 Agent；session/state/机制证据和聚合 | 顺序、fresh session、持久状态 on/off、分支隔离与原生失败语义；外层不额外注入记忆 |
| **BM04：PostTrainBench 独立包** | 隔离 HPC/backend、GPU 实际限制、训练与公开自评、模型冻结交接、judges/汇总 | 先有限预算工程 smoke，再单独申请原生配置验收；大权重可靠交接及 scoped cleanup 必须先完成 |
| **BM05-B：扩大批量** | 公平队列、受控并发、任务资源监测、预算累计与大文件恢复 | 请求/授权/实际分配/使用量分别可查；故障下不漏计预算、不污染任务 |
| **BM06：有界外层优化** | 不可变 Candidate、允许修改范围、反馈权限、累计预算、比较/停止规则 | 两候选基于允许反馈迭代；所有规定尝试保留；协议内学习和平台优化分开 |
| **BM07：使用与扩展验收** | 通用 Batch/Campaign 页面、原生提交桥、维护兼容矩阵；第三方新 bench 接入演练 | 只提交独立包和配置即可复用已有后端、调度、监控、记录；需新能力时明确说明扩展点 |

四个正式参考包按同一 SDK 和启用配置开发；放在 `adapters/<distribution>/` 的独立 Python 项目，
以后可独立迁仓和发布。BM00 的 `examples/benchmark-adapter/` 仅是合成模板，没有导入四个官方仓库。

每阶段创建自己的任务记录，完成所需测试后汇报分支/提交、功能、限制和证据；用户检查后再开启下一阶段。
真实模型/硬件验收在对应阶段明确目标节点、时间/资源/费用预算，不沿用别的任务的运行授权。
当前交付入口：[SDK 使用说明](../reference/benchmark-sdk.md)、[适配包开发指南](benchmark-adapters.md)。

BM01 交付范围见[受管执行参考](../reference/benchmark-execution.md)和
[实现说明](../implementation/benchmark-execution.md)：一个原子单位、一个 native 阶段、可信本机进程，
复用控制 store 与 Records，支持持久 operation/handle、重启续查和有界日志/产物归档。
进程组清理和状态目录单槽不等于容器隔离或持久资源租约；GPU/子容器控制、官方协议评分、多单位队列
仍按后续阶段实施。BM02-A 已通过可选 Harbor runtime 补充原生 job/子容器清理和 CPU/内存实际核验；
[验收范围](../operations/tb-science-native-trial.md)限单 CPU Oracle/Nop profile，不等于整套任务或模型 Agent 兼容。
BM02-B 的[验收范围](../operations/asi-bench-native-trial.md)限公开 seed31415 单任务 fixture；
本地分数、seed42 bundle、认证提交和官方分数保持分离。
BM05-A 增加同一 benchmark 状态目录内的 FIFO 等待队列和持久租约账本：请求/Run、owner epoch、
原生 job ID、对账与清理后释放均可恢复；默认仍为单活动租约。它不提供 cgroup/GPU 硬限额、后台
自动调度、公平并发、跨状态目录配额或多节点能力。操作入口见[队列说明](../operations/benchmark-queue.md)。
