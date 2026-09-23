# BM03 PAST-Bench 适配实现

状态：BM03 已实现，固定 PAST-Bench `f8223517ae7491e776b69793d9f11e9d074ab42e`
（v1.0.0）。本文解释当前代码，不代表官方认证或榜单提交能力。

## 实现边界

独立包 [`adapters/past-bench/`](../../adapters/past-bench/) 通过 BM00 entry point 接入，核心代码
不按 benchmark 名称分支。适配器把一个 v2 family 映射为一个 `paired_sequence` WorkUnit：

- episode 顺序来自固定上游代码生成的 manifest；平台不能拆散、重排或并行这些 episode；
- `with_persistence` 与 `without_persistence` 是同一个原生任务内的两条隔离条件分支；
- 每个 episode 的 fresh session、history mode、anchor 和持久化机制由 PAST-Bench 管理；
- 平台只做来源冻结、兼容性检查、外层排队、进程监督、证据归档和结果解释，不注入总结或记忆。

适配包依赖固定 Git revision，规划时同时冻结 family、`config.yaml`、Agent registry 和已安装 runner
源码摘要。执行前重新核验这些摘要，降低规划后源码漂移导致协议变化的风险。

## 调用链

1. `Adapter.discover()` 确认 source 是固定 Git checkout 内的一个 family，调用原生
   `generate_manifest()` 获取 episode 顺序。
2. `Adapter.plan()` 生成一个原子 WorkUnit、两条 `StatePolicy` 和一个 native-owned phase。
3. `Adapter.validate()` 核对 family、状态策略、参数、候选 Agent 身份和 runner 摘要。
4. `Adapter.invocation()` 冻结 runner 请求，并选择 `past-bench-native-v1` backend。该任务把日志上限
   提高到 32 MiB、产物上限提高到 64 MiB；这是 `NativeInvocation` 的通用有界参数。
5. `runner.py` 再次验证来源，生成 `native-manifest.yaml`，运行工程 profile 或原生 PAST CLI。
6. runner 校验两条分支的 episode 顺序、fresh-session/history 声明和状态根隔离，保存
   `native-result.json`；`Adapter.interpret()` 只从已归档输出生成平台结果视图。

`PastBenchBackend` 复用受管进程生命周期和 BM05-A 持久 operation/lease。PAST 内部失败仍按原生
结果保留，例如 `infra_blocked` episode 会进入证据列表，适配器不会偷偷重跑或改写为平台成功。

## 两种运行模式

`engineering` 是默认的无模型协议 fixture。它使用固定 manifest、上游 history/state 原语与原生汇总
函数，生成可验证的配对证据，但得分是确定性的工程数据，`official=false`。

`native` 调用固定版本 PAST CLI，当前支持上游本地 runtime：`hermes`、`hermes-plus`、`nanobot`
和 `zeroclaw`。所选 Agent 包需要从同一个 checkout 安装；候选版本必须声明
`past-f8223517ae74`。凭据只从绝对路径、owner-only 的普通文件读取，内容不进入计划、argv、日志或
Records。未配置 judge 时允许完成原生运行，但结果标记为 `review_required`。

当前 native backend 与 PAST `--runtime local` 对齐，可选 `--sandbox-tools`；BM03 未验收 Docker
sandbox 等价性、真实模型质量或官方提交。真实运行前应为具体 Agent × model × family × backend
建立新的 capability claim，不能复用随包提供的工程 fixture 声明。

## 输出与扩展点

Records 归档 `native-manifest.yaml`、完整 `past-output/` 和 `native-result.json`。原始目录包含每条
分支的 episode 结果、sequence summary、comparison 及原生 trace；平台结果保留 family、Agent、
model、分支、配对 delta 和协议状态。

后续支持新 PAST Agent 时，先在适配包中验证原生 session/state 能力，再扩展支持矩阵；不应因为
Agent Infra 能启动某个 CLI 就声明其满足 PAST 持久化契约。后续 Docker 或远程 runtime 应增加新的
ExecutionBackend 能力和独立验收，不改写现有 profile 的含义。
