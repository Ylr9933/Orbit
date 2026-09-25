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

## 原生 Codex + Docker OS 公开试运行

准备 Docker daemon、当前用户可读的私有 `~/.codex/auth.json`、固定 revision 的 ASI-Bench checkout、
安装了 ASI-Bench 与两个 agent-infra 包的 Python 环境。先确认本机可承担
**单个原生容器最多 4 CPU / 8 GiB、无 GPU**；上游 OS sandbox 当前没有更低的
CLI 限额参数。镜像构建与模型调用需要网络；本地代理可在 request 参数中指定
`proxy_url`，环回代理须同时指定 `docker_network=host`。
此组合只让 ASI 的任务镜像构建和 Agent 容器使用宿主机网络；容器仍由原生
`--sandbox os` 创建并受 CPU/内存限额约束。

把 `request-codex-os.json` 复制到私有临时目录，改 `tasks_dir` 为 checkout 的
`tasks/` 绝对路径，核对模型、超时和实例后执行：

```bash
agent-infra benchmark inspect asi-bench-codex-os \
  --config adapters/asi-bench/adapters.toml --source /path/to/INSTANCE__seed31415
agent-infra benchmark plan asi-bench-codex-os \
  --config adapters/asi-bench/adapters.toml --source /path/to/INSTANCE__seed31415 \
  --request /private/codex-request.json --output /private/codex-plan.json
agent-infra benchmark check /private/codex-plan.json \
  --config adapters/asi-bench/adapters.toml \
  --capabilities adapters/asi-bench/capabilities-codex-os.json
agent-infra benchmark prepare /private/codex-plan.json \
  --config adapters/asi-bench/adapters.toml --output /private/codex-execution.json
agent-infra benchmark run /private/codex-execution.json \
  --config adapters/asi-bench/adapters.toml --state-dir /private/state \
  --operation-id asi-codex-public-trial \
  --capabilities adapters/asi-bench/capabilities-codex-os.json \
  --allow-host-process --allow-native-runtime
```

`check` 只验证冻结声明，`runtime_ready=false` 是预期值。提交后用
`benchmark status/events/artifacts` 查看 Run/Attempt 和 Records；Web 的
Benchmark 页面可分页查看同一次运行的原生 instance、prompt level、Codex
session、工具步骤以及 Docker 身份、限额和最近资源样本。Records 中的
`evidence/index.json` 必须逐项核对：`raw_stdout_file`、`trajectory_file`、
`raw_stderr_file`、`model_calls_file` 的 `capture_status` 会区分 `complete`、
`derived`、`unavailable`、`missing` 和 `truncated` 等情况。上游此 revision
通常不产生独立的模型调用文件；若 JSONL 有 `turn.completed`，则索引给出
完成轮次与最后一次用量。容器未采到样本时，不要把外层进程用量当作容器用量。
