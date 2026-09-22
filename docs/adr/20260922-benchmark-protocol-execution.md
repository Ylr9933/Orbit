# Benchmark 协议、执行后端与外层优化分离

状态：Accepted（架构边界）；BM00 SDK/规划在任务分支实现，执行与优化仍分期开发。
日期：2026-09-22。不改变现有科研 Run 行为；集成状态以 Git 为准。

## 背景

最初的 ASI-Bench / TB-Science adapter 提案以独立 Docker trial 为主。
PostTrainBench 引入长时训练、目标模型、HPC 执行与独立 judges；PAST-Bench 引入
有序 fresh-session episodes、跨会话状态和配对对照。统一为一次 `run_trial()`
无法充分表达恢复、状态隔离、资源所有权和反馈边界。

## 备选方案

1. 所有 benchmark 转为平台单 Task / Docker / scorer：入口一致，但容易改变原生协议，
   无法忠实表示 sequence、外部调度和训练期公开 evaluation。
2. 仅包装原生命令：接入快，但资源限制、取消、恢复、状态和反馈都成为不透明副作用。
3. BenchmarkAdapter 定义协议，ExecutionBackend 提供可观测生命周期，Projects 管可选外层优化。

## 决定

采用方案 3，优先委托原生 runner 执行内部协议，并保留黑盒托管的有限覆盖标识。
独立任务和原生管理的序列先行，不先建设全功能 DAG 引擎。
原生学习/训练循环与平台多候选优化严格区分；反馈和状态传播由固定协议控制。
详细接口、四类映射、代码边界和阶段验收统一维护在
[Benchmark 层设计](../architecture/benchmark-integration-layer.md)。

适配器作为独立 Python 包消费公共 SDK，管理员显式启用固定 distribution/version/entry point。
四个参考适配器与第三方包遵循同一边界；不在核心内置 bench 名称注册分支。
BM00 提供模板、元数据校验和 SDK conformance，真实 backend/协议等价另做验收。

## 后果

- 新 bench 原则上增加 adapter；新执行形态增加 backend，不在 Run 中堆条件分支。
- 需要补持久 handle、租约对账、状态/大产物引用和候选血缘，单纯包 CLI 不算完整接入。
- 任意 benchmark 的可扩展性不等于零配置兼容或官方认证，支持范围需要版本化证据。
- 现有科研命令继续运行；BM00 已把 benchmarks 层纳入 import-linter 并补反向依赖测试。

## 验证

文档设计基于固定版本官方来源与现有代码审查。BM00 的独立 wheel、四类合成协议与离线检查
验收见[任务记录](../changes/20260922-benchmark-sdk-bm00-c7e2a1.md)；尚无四个 benchmark 的真实执行证据。
用户要求每阶段完成后检查再推进，后续实施见[开发顺序](../development/benchmark-development-plan.md)。
