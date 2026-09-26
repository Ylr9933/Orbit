# ASI-Bench 批量运行

状态：批量入口复用现有单任务适配器、FIFO 队列、持久租约与 Records。每个 Run 执行一个原生实例；并发由 Infra 控制，ASI 内部保持 `--parallel 1`。目前只支持该适配器允许的公开 seed31415，不代表 seed42 官方提交。

## 准备

在同时安装主包、ASI 适配包和固定 ASI 依赖的 Python 3.12 环境中使用。Docker、Codex 认证、镜像构建网络必须可用。原生求解容器默认每个 4 CPU/8 GiB、无 GPU；6 并发对应最多 24 CPU/48 GiB 容器限额，宿主机 runner、镜像构建和评分还需要额外资源。

复制 `adapters/asi-bench/request-codex-os.json` 到本地运行目录，修改：

- `candidate.model`：本次为 `gpt-6-sol`。
- `candidate.configuration_digest`：更新为本次候选配置的摘要。
- `parameters`：`prompt_level=b3`、`timeout_seconds=10800`、`codex_version=0.157.1`，设置真实 `tasks_dir`；必要时设置代理和 `docker_network=host`。
- `selection` 将按每个 source 的原生单元替换；其余请求原样冻结。

```bash
agent-infra benchmark batch prepare \
  --directory benchmark/asibench/b3-gpt-6-sol-20260926 \
  --config adapters/asi-bench/adapters.toml --adapter asi-bench-codex-os \
  --sources /path/to/ASI-Bench/bench_runs/instances_seed31415 \
  --pattern '*__seed31415' --request /private/b3-request.json \
  --concurrency 6 --declare-compatibility
```

此步骤不调用模型或 Docker。先校验所有实例、prompt level、上游版本和原生调用，再保存批次。`--declare-compatibility` 表示操作者审核并声明这些精确的 adapter/source/runner/profile/agent/model/backend 组合；它不是通过运行证明模型可用。模型名和版本必须符合适配器规则；账号访问权限、余额、限流和模型实际可用性只能由真实请求证明，不会根据“CLI 已安装”推断成功。本机缓存模型清单仅可作为准备阶段的参考。

如果一个实例不兼容，整个准备失败，不启动其余任务。目录已存在则拒绝覆盖。提交前也会重新核验所有冻结文件；没有自动切换模型或自动重试。

## 提交、推进和查看

```bash
agent-infra benchmark batch submit \
  --directory benchmark/asibench/b3-gpt-6-sol-20260926 --allow-native-runtime
agent-infra benchmark batch worker \
  --directory benchmark/asibench/b3-gpt-6-sol-20260926
agent-infra benchmark batch status \
  --directory benchmark/asibench/b3-gpt-6-sol-20260926
```

提交使用稳定 operation ID，重复提交同一批次会复用已存在 Run。批次状态固定在该目录的 `state/` 中，不要为每个任务分配独立状态目录。worker 每 5 秒调用现有 reconcile 并更新汇总；可以在终端复用器或受管服务中运行。停止 worker 不会取消已经启动的任务，重新启动同一个命令即可继续观察和推进。

取消单个任务沿用现有命令，配置和状态目录指向该批次：

```bash
agent-infra benchmark cancel RUN_ID \
  --config benchmark/asibench/b3-gpt-6-sol-20260926/adapters.toml \
  --state-dir benchmark/asibench/b3-gpt-6-sol-20260926/state
```

ASI 适配器从原生 Codex 的终止事件识别 `model_unavailable` / `model_authentication_failed`，保留原始错误并将机器可读原因传给批次。批次在下一次派发前先收集活动结果；遇到上述错误会写 `blocked.json`、取消剩余已提交任务并停止 worker。不会把 metadata 警告当成拒绝，也不会切换模型。修正账号或模型后需重新准备一个批次，旧批次保留失败证据。

不自动重试失败任务。需要重试时应单独审阅错误、配置与预算，然后创建新的运行请求。

## 结果

- `batch.json`：不可变批次成员、模型、并发和执行摘要。
- `executions/`：每个任务的冻结执行计划，包含 prompt level、模型与预算。
- `capabilities.json`：操作者声明的精确兼容组合，不是实际验收证书。
- `summary.json` / `SUMMARY.md`：每任务状态、Run ID、评分状态、指标、产物 ID；未提交、排队、失败、无分数不会伪造为零分。
- `state/benchmarks/records/`：原始日志、Codex JSONL、轨迹、评测和产物；用既有 events/artifacts/Web 查询。

汇总只展示原生单任务指标，不自行发明 ASI 总分，也不作为官方榜单提交。所有公开本地评分的 `official_score` 仍为 null。

本次 batch 预算上限为所有单任务外层墙钟预算的总和，每任务为原生超时加 120 秒；排队时间不消耗其执行时限。这不是 token/费用硬限额。

**评分仍使用宿主机的 ASI 原生 scorer，尚未独立容器化或串行化。** 并发评分可能影响涉及运行速度的指标。容器资源限额不约束宿主机 scorer；本批次用于真实运行和记录，不能宣称严格控制硬件条件的官方复现。


## 2026-09-26 首次 b3 批次

60 项离线检查通过，6 项正式启动后，容器内 Codex 的 ChatGPT 认证均返回 gpt-6-sol 不支持。
操作者立即停止派发：6 failed / 54 cancelled，任务容器清理完成。该证据不代表 gpt-6-sol 在所有平台不可用；只证明本次原生 Codex/认证组合被服务端拒绝。
本机模型缓存曾列出该模型，但不能作为运行权限证明。没有擅自换模型或自动重试。
运行结果位于本机 `benchmark/asibench/b3-gpt-6-sol-20260926/`，该目录不进入 Git。


## 固定容器 Codex 版本

可选 request 参数 `codex_version` 必须是精确的 `major.minor.patch`。未设置时保持原 ASI 安装行为。
设置后，适配器的小型 `native_cli.py` 入口只将固定版本 ASI 的 `AGENT_INSTALL_COMMANDS["codex"]` 设为
`npm install -g @openai/codex@VERSION`，随后交给原生 CLI 执行。原生镜像缓存键包含安装命令，因此
新版本使用独立镜像，不覆盖旧镜像，不修改任务、prompt、评分文件。该接入点受固定上游 revision 和回归测试约束。
该参数作用于 ASI 默认构建路径；不代表能改写任务自行指定的预构建镜像。

本次排查确认宿主机为 0.157.1，首次失败容器为缓存的 0.153.4。使用同一认证，在 0.157.1 容器中执行 gpt-6-sol 最小请求已成功返回 OK（退出码 0、turn.completed）。因此首次拒绝不能归因为账号没有模型权限。

升级后新批次位于 `benchmark/asibench/b3-gpt-6-sol-codex01571-20260926/`，
仍为 60 项 b3、6 并发、每任务 10800 秒、无自动重试。
`benchmark/asibench/latest.txt` 指向本机最新批次；读取其 `SUMMARY.md` 查看进度。
最小模型验证保存在本机 `benchmark/asibench/codex-01571-check/`；这些运行文件不进入 Git。
