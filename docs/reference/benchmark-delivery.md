# BM07：Benchmark 使用、兼容矩阵与原生提交交接

状态：BM07 在任务分支实现；以 Git 集成及[任务记录](../changes/20260923-benchmark-delivery-bm07-8c6e41.md)
为准。适用范围是单机、单管理员，沿用同一 `--state-dir` 中 BM05/BM06 的持久状态。

## 页面

构建 Web 后以相同状态目录启动 `agent-infra web --state-dir STATE --web-root src/web/dist`，
进入 **Benchmark** 页面。每 5 秒读取最近 50 条 Run、等待项/租约/授权槽位、最多 50 个
Campaign 的候选比较，以及已发布的兼容矩阵。页面只读，不启动任务，不提供原始 benchmark
评测日志或私有文件。创建候选、提交试验与取消仍走 CLI。需要完整运行证据时由管理员用
`benchmark status/events/artifacts` 或 Records 命令查询；不要把管理员令牌或状态目录交给优化 Agent。

## 兼容矩阵

矩阵是针对 **adapter 版本 × suite/runner 摘要 × profile × Agent × backend** 的声明，
不是“装了某 CLI 就兼容”的推断。`indexed`、`runnable`、`scored`、`protocol_validated`
逐级表示已索引、已运行、已评分和协议验证。高于 indexed 必须给出证据引用；`run:RUN_ID`
引用会与本地冻结配置及结果核对，`doc:...` 等外部引用由管理员负责审查。
`official_submission` 单独声明 `unsupported`、`manual` 或 `native`，即使是 `native`
也不表示官方已接受成绩。矩阵模板：

```json
{
  "schema_version": 1,
  "entries": [{
    "alias": "my-bench",
    "adapter_id": "my-bench",
    "distribution": "my-bench-package",
    "adapter_version": "1.0.0",
    "suite_digest": "sha256:<64-hex>",
    "runner_digest": "sha256:<64-hex>",
    "profile": "development",
    "backend": "managed-process-v1",
    "agent": "my-agent",
    "agent_version": "1",
    "model": "none",
    "level": "runnable",
    "evidence": ["run:<RUN_ID>"],
    "official_submission": "unsupported",
    "limitations": ["one synthetic CPU trial"]
  }]
}
```

将占位符替换为真实固定值后执行：

```sh
agent-infra benchmark compatibility publish --file matrix.json \
  --config adapters.toml --state-dir "$STATE"
agent-infra benchmark compatibility show --state-dir "$STATE"
```

发布时核对显式启用且精确安装的包身份；本地 Run 引用还检查其版本元组和所声称的结果级别。
结果保存于 `STATE/benchmarks/compatibility.json`，页面从此读取。外部文档引用没有自动验证；
正式榜单认证仍需 benchmark 官方流程与单独证据。

## 原生提交交接

适配包可选择实现 `prepare_submission(plan, artifact, native_result)`，返回
`NativeSubmissionPlan`（目标、原生格式、人工步骤、是否支持直接发送）。平台只允许对已完成、
协议有效、清理确认且产物属于该 Attempt 的 Run 生成交接；清单固定候选、adapter、suite/runner
摘要及 Records 产物摘要，存在 `STATE/benchmarks/submissions/`：

```sh
agent-infra benchmark handoff prepare RUN_ID --config adapters.toml --state-dir "$STATE"
agent-infra benchmark handoff status RUN_ID --state-dir "$STATE"
```

如果适配包还实现 `send_submission(handoff, artifact, records)` 并声明 `supports_send=true`，
管理员检查目标及交接清单后，可显式执行：

```sh
agent-infra benchmark handoff send RUN_ID --config adapters.toml \
  --confirm-native-submit --state-dir "$STATE"
```

发送前先持久写下不可重试意图。若回执丢失，状态为 `unknown`，平台**不会自动重发**；
管理员须按原生 submission ID/平台日志向官方系统核对，再通过单独的协议流程处理。
`submitted` 仅表示适配器返回发送回执，**不等于官方接受或评分**。四个参考适配器目前
均未实现这一可选扩展，因此不会误触发真实上传。提交凭据只由受信任适配包按原生方式获取，
不写入矩阵、交接清单或项目文档。

## 新 benchmark 演练

`uv build && uv run --locked python scripts/acceptance/benchmark_extension.py` 在临时目录
生成一个新的独立示例包，安装到隔离 venv，并完成 plan/check/prepare、一次短时 CPU 执行、
Records 产物、矩阵发布和页面读模型检查。它没有修改核心注册表或 Run 状态机，证明**现有
backend 能覆盖的协议**可用“独立包 + 显式配置”接入。合成示例无 Agent、Docker、GPU、私有
grader 或官方提交，不能替代新 benchmark 的原生评分等价与能力矩阵验收；需新执行形态时扩展
通用 backend，再按该 benchmark 的协议补包内对照测试。
