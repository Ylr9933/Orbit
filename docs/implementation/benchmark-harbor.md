# BM02-A：Harbor 与 TB-Science 的实现路径

状态：任务分支实现；使用范围与验收见[操作说明](../operations/tb-science-native-trial.md)及
[任务记录](../changes/20260922-benchmark-tb-science-bm02a-6b91e3.md)。

## 模块分工

| 位置 | 职责 |
| --- | --- |
| `adapters/tb-science/` | 固定 task/Harbor 版本，读取原生 TOML，生成 SDK Plan/Invocation，解释 reward 与失败 |
| `adapters/harbor-runtime/` | 通用 Harbor 单 trial 执行、资源实际验证、原生命名空间与清理证据；没有 TB-Science 名称分支 |
| `benchmarks/execution_api.py` | 可选 NativeRuntimeAdapter 扩展：backend factory、执行验证、证据解释 |
| `bootstrap/benchmark_execution.py` | 根据已启用、固定版本的 adapter 组装 runtime；CLI 参数不直接指定任意 Python import |
| `runs/benchmark_execution.py` | 复用原有 Run/Attempt、单活动槽、重复提交处理、Records 与完成顺序 |
| `environments/managed_process.py` | durable launch/进程监督，可扩展读取已核对 spec；不理解 benchmark |

新 bench 使用已有 runtime 时只增加适配包和启用/兼容配置。需要新的 backend 能力时，由可选适配包
提供 `execution_backend(root)`、`validate_execution(plan, invocation)` 与 `interpret(collected_root)`。
这三个方法是执行扩展，BM00 规划包不必实现。插件是显式信任的宿主机代码，不能将任务内的 import 字符串当成插件注册。

factory 不启动任务；验证必须在 submit 前完成，并对资源、阶段时钟和材料隔离负责。
核心仍检查单原生阶段、单工作单元、backend ID/能力匹配、禁止平台重试。
解释只读取已冻结的提交，不再次启动评测。解释失败保留 `collecting` 与执行槽，不能发布不完整分数。

## 原生执行与隔离

1. 在原始任务 Git revision 和文件树摘要上冻结计划；执行前重新计算并核对已安装 Harbor 文件摘要。
2. Run 持久化 intent，ManagedProcessBackend 写 durable launch，再启动独立 worker。
3. worker 使用 Harbor `Trial.create/run`。不重写原任务，不替换 Oracle、artifact transfer、scorer 或超时逻辑。
4. 每个原生环境构造时先写 ownership，再执行 Docker 操作；唯一命名空间避免 Harbor 的启动清理触碰其他任务。
5. 附加 Compose overlay 只为已支持的主容器/网络辅助容器加限额和 owner label。
   原生 task Compose 被此 profile 拒绝；启动后核对全部服务、实际 CPU/内存、无 GPU 请求后才让原生 Agent 工作。
6. Harbor 先停止求解环境、交接声明产物，再建立独立 verifier；原始私有材料不进求解容器。
   Oracle 读取参考解是其原生验收方式，不是模型 Agent 可读权限。
7. worker 原生清理并记录 receipt。后端需要同时确认进程组清理、原生正向回执、Docker 中无本命名空间容器/网络/卷。
8. Run 冻结并提交原始目录到 Records，解释原生 reward，最后释放槽。原始证据为 ADMIN。

`ExecutionSpec`/`NativeInvocation` 增加可选 `cancellation_grace_seconds`。默认 0.25 秒且默认字段不序列化，
保持 BM01 旧 prepared execution 摘要兼容；Harbor 使用 90 秒供原生清理，之后仍可强制终止进程组。
强制退出而无原生清理回执必须隔离，不能仅靠进程已死推断 Docker 已干净。

## 记录与不确定性

外层 supervisor 身份和原生 Harbor trial UUID 是两层 ID：前者用于可靠进程监督，后者保存在
`native-job.json`、原生 result 与解释结果中。重启不会猜测性再启动 Harbor。
初始化时冻结的 coverage 声明在后续轮询保持原值，避免运行时升级导致已存在 manifest 冲突。

原生的 reward=0 是有效评分；异常、缺失 result/reward 是失败或未知。原生轨迹在 agent 目录原样保存，
合并日志带原生 phase/trial ID；Oracle 没有模型对话，不得称为已验证 Codex/RL 轨迹。
原生数据规模超过现有有界收集能力时明确停下，大文件通道仍归后续阶段。

## 限制与下一阶段

本阶段验证可复用的 native runtime 接入，不自动扩展为整套任务兼容。模型 Agent、其他 task profile、
多服务资源核对、GPU、持久队列/全局租约、自动优化与榜单提交需各自验收。
TB-Science 的请求和原始 scoring 不被本平台改写；工程缺省限额、网络辅助服务开销、构建与磁盘限制均显式展示。

Harbor 自身原生 API 和少量受保护的 Docker 扩展点被限制在可选 runtime 包中，固定 commit + 文件摘要 + 真机回归
用于发现上游变化。核心项目既不依赖 Harbor，也不按 benchmark 名修改注册表或状态机。
