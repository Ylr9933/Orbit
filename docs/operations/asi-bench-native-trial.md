# BM02-B：ASI-Bench 本地公开集试运行

状态：BM02-B 任务分支的 CPU 工程验收入口。它验证接入边界，不代表真实 Agent、GPU、
完整套件或排行榜成绩。

## 前置条件

- Python 3.12 隔离环境中安装仓库根包、`adapters/asi-bench` 和该包锁定的 ASI-Bench。
- 本地有 commit `38ab4b5364f1fde5515fef7e9210ff3c9db6a2ba` 的 ASI-Bench checkout，
  选定的 `seed31415` instance 和对应 `tasks/` 内容未修改。
- 本轮只使用 `fixture`、CPU 和宿主机进程；不调用模型、不使用 GPU、不上传结果。

将 `adapters/asi-bench/request.json` 复制到私有临时目录，把 `tasks_dir` 改为 checkout
中的 `tasks/` 绝对路径，然后依次执行：

```bash
agent-infra benchmark adapters --config adapters/asi-bench/adapters.toml
agent-infra benchmark inspect --config adapters/asi-bench/adapters.toml \
  --source /path/to/instances/math.sigma_linear_diophantine__seed31415 asi-bench
agent-infra benchmark plan --config adapters/asi-bench/adapters.toml \
  --source /path/to/instances/math.sigma_linear_diophantine__seed31415 \
  --request /private/request.json --output /private/plan.json asi-bench
agent-infra benchmark check --config adapters/asi-bench/adapters.toml \
  --capabilities adapters/asi-bench/capabilities.json /private/plan.json
agent-infra benchmark prepare --config adapters/asi-bench/adapters.toml \
  --output /private/execution.json /private/plan.json
agent-infra benchmark run --config adapters/asi-bench/adapters.toml \
  --state-dir /private/state --operation-id asi-public-smoke \
  --capabilities adapters/asi-bench/capabilities.json \
  --allow-host-process --allow-native-runtime /private/execution.json
```

轮询 `benchmark status --config ... --state-dir ... RUN_ID`。成功结果应明确包含：

- 原生 task、instance 和 prompt level 与计划相同；
- `evaluation=scored`、`protocol=valid`；
- 指标名为 `local_public_score`，原生证据中 `official=false`；
- `official_score=null`、`submission=not_requested`；
- `cleanup_complete=true`、`cleanup_scope=owned_process_group`。

`fixture` 只生成结构正确的空结果，低分或零分是预期现象。正式 seed42 路径必须由
ASI-Bench `--sandbox os` 产生 Docker provenance。以下命令只做原生校验并生成本地目录，
不会认证、打开浏览器或上传：

```bash
python -m agent_infra_asi_bench.bundle \
  --results-dir /private/seed42-results --output-dir /private/submission-bundle
```

之后的认证提交与官方评分仍由 ASI-Bench 服务负责。不要把公开集本地分数或 bundle
创建成功解释成官方成绩。
