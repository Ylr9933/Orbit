# BM02-B：ASI-Bench 实现路径

`adapters/asi-bench` 是可独立安装的适配包，核心代码不按 benchmark 名称增加分支。
`Adapter` 把一个未修改的公开 instance 映射为单个原子 WorkUnit，并冻结 instance、
对应公开 task/scorer、原生 runner revision、prompt level 和超时。规划阶段不启动进程。

执行时，`AsiBenchBackend` 复用 BM01 的持久受管进程。`runner.py` 先复核冻结摘要，
再以 `score=False` 的 ASI-Bench CLI 运行一次 produce-only attempt。原生结果落盘后，
它根据该结果记录的 persisted output 构造 schema-v2 BenchFlow manifest，并调用
ASI-Bench 自己的 `score_manifest_file`。适配包不复制 gate、scorer 或参考答案逻辑。

归档只收集原生 result、persisted outputs、run metadata、instance identity snapshot、
BenchFlow manifest/score 和解释摘要。ASI-Bench 的临时 workspace 链接不进入 Records，
既避免悬空链接，也避免扩大可信归档范围。外层 backend 只终止和确认本次进程组，
不会按进程名或全局 Docker 状态清理其他任务。

`interpret()` 只有在原生 score 明确 `official: false` 且 `official_score` 为空时才接受
本地评分协议，并只暴露 `local_public_score`。执行状态、attempt 状态、本地评分、
submission 和官方评分保持独立。

`bundle.py` 直接调用 ASI-Bench 原生 `build_submission`。它要求每个结果都是 seed42，
并含 fail-closed OS Docker、容器验证和镜像 identity；seed31415 或缺 provenance 会被
拒绝。此模块固定 `archive=False`，不包含认证或上传逻辑，返回值始终不宣称官方分数。

当前 profile 的 `fixture` 只用于无模型工程验收。接入真实 Codex、GPU/OS sandbox、
完整套件和正式提交，需要单独兼容矩阵及相应资源验收，不能只改 agent 参数后直接宣称支持。
