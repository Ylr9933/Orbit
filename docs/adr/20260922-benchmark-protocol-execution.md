# Benchmark 协议、执行后端与外层优化分离

状态：Proposed。日期：2026-09-22。范围：尚未实现的 Benchmark 层；不改变现有科研 Run 行为。

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

## 拟议决定

采用方案 3，优先委托原生 runner 执行内部协议，并保留黑盒托管的有限覆盖标识。
独立任务和原生管理的序列先行，不先建设全功能 DAG 引擎。
原生学习/训练循环与平台多候选优化严格区分；反馈和状态传播由固定协议控制。
详细接口、四类映射、代码边界和阶段验收统一维护在
[Benchmark 层设计](../architecture/benchmark-integration-layer.md)。

## 后果

- 新 bench 原则上增加 adapter；新执行形态增加 backend，不在 Run 中堆条件分支。
- 需要补持久 handle、租约对账、状态/大产物引用和候选血缘，单纯包 CLI 不算完整接入。
- 任意 benchmark 的可扩展性不等于零配置兼容或官方认证，支持范围需要版本化证据。
- 现有科研命令继续运行；新依赖边界需在实现 PR 纳入 import-linter，不能提前放宽规则。

## 验证

文档设计基于固定版本官方来源与现有代码审查，尚无四个 benchmark 的真实执行证据。
采用决定及落地以用户评审和后续实施 PR 为准。
