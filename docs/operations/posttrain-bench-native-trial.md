# PostTrainBench BM04 试运行

状态：BM04 已实现。无模型工程 profile 已验收；本手册中的真实模式是待集群验收入口，不代表已在
本机或官方环境运行。固定上游 revision 为
`3ed1d32ff1ec1f41282be6f8ebbcec07b19fc3d1`。

## 无模型验收

准备固定 checkout 后运行：

```bash
git clone https://github.com/aisa-group/PostTrainBench.git /private/PostTrainBench
git -C /private/PostTrainBench checkout 3ed1d32ff1ec1f41282be6f8ebbcec07b19fc3d1
POSTTRAIN_BENCH_CHECKOUT=/private/PostTrainBench \
  uv run --locked python scripts/acceptance/posttrain_bench.py
```

脚本构建并在临时环境安装核心和独立适配 wheel，针对 `gsm8k` 验证 prompt、judge schema、小型模型
快照、Records 和租约释放。不会读取凭据或启动 GPU/scheduler。

## 真实运行前置条件

集群管理员需要确认：

- HTCondor 的 `request_gpus` 会将 job 可见 GPU 严格限制在授权集合；
- job 结束或 `condor_rm` 后，进程、Apptainer、FUSE overlay 和临时目录由 scheduler 范围清理；
- head/execute node 共享 PostTrainBench checkout、results root、模型存储、容器和 HF cache；
- H100、CPU、内存、磁盘和最长 wall time 满足冻结计划；
- `condor_submit`、`condor_q`、`condor_history`、`condor_rm` 来自同一受信任安装目录；
- 上游 `.env` 及 auth 文件已按原生说明配置，`.env` 权限为 `0600`；
- model store 已存在、权限为 `0700`，容量能容纳一次额外的 final-model 快照。

不要在共享宿主机直接运行固定版本 `src/run_task.sh`。它的最终评测会清理 job 内可见 GPU 进程；缺少
设备可见性隔离时可能影响其他任务。

## 原生请求

请求中的 Agent 名称必须对应固定 checkout 的 `agents/<name>/solve.sh`，Agent version 使用
`posttrain-3ed1d32ff1ec`。下面摘要和 revision 需要替换为实际固定基础模型证据：

```json
{
  "selection": ["gsm8k"],
  "candidate": {
    "candidate_id": "codex-gsm8k-qwen17b",
    "agent": "codex_non_api_max",
    "agent_version": "posttrain-3ed1d32ff1ec",
    "model": "gpt-5.6-sol",
    "configuration_digest": "sha256:<agent-config-digest>",
    "target_model": {
      "uri": "hf://Qwen/Qwen3-1.7B-Base",
      "revision": "<immutable-huggingface-revision>",
      "digest": "sha256:<resolved-model-digest>"
    }
  },
  "parameters": [
    {"key": "mode", "value": "native"},
    {"key": "model_to_train", "value": "Qwen/Qwen3-1.7B-Base"},
    {"key": "num_hours", "value": "10"},
    {"key": "num_gpus", "value": "1"},
    {"key": "request_cpus", "value": "16"},
    {"key": "request_memory_mb", "value": "131072"},
    {"key": "request_disk_gb", "value": "400"},
    {"key": "timeout_seconds", "value": "79200"},
    {"key": "results_root", "value": "/shared/posttrain/results"},
    {"key": "model_store", "value": "/shared/agent-infra/models"},
    {"key": "scheduler_bin_dir", "value": "/usr/bin"},
    {"key": "max_model_bytes", "value": "2199023255552"}
  ]
}
```

`results_root` 必须与私密 `.env` 中 `POST_TRAIN_BENCH_RESULTS_DIR` 解析出的绝对路径一致。计划和
Records 会保存路径引用，不保存 `.env` 或 auth 内容。

为真实组合单独建立 capabilities 文件，包含 `posttrain-htcondor-v1` 的全部 native features，以及
精确的 adapter、suite、runner、Agent、model 和 backend 组合。随包提供的 capabilities 只允许
`protocol-fixture`，不能用于真实 H100 任务。

完成 `inspect → plan → check → prepare` 后，人工检查冻结命令、资源和路径，再使用
`--allow-native-runtime` 提交。运行期间用 `benchmark status/events/queue` 查看平台状态，同时以集群
工具核对 native job ID。取消必须使用平台 `benchmark cancel`，不要按进程名或 GPU 全局清理。

如果提交响应丢失且 `condor_q`/`condor_history` 暂时查不到 job，平台会保留提交意图并报告
`unknown`，不会自动再次 `condor_submit`。管理员应按 operation 的 ClassAd、冻结 spec 摘要、
HTCondor 日志及集群历史确认该 job 是否存在，再处理对账；不要通过重复提交同一 operation 试探。

## 结果判定

一个可计分的本地结果至少需要：

- `metrics.json` 中数值型 accuracy；
- contamination/base-model、API usage 和 PTB lookup 三个必需 verdict；
- 可验证的 `final_model/config.json` 和内容寻址模型快照；
- scheduler terminal/cleanup 证据；
- 完整或明确标记截断的 Records evidence。

`raw_accuracy` 是原生评测值，`score_eligible` 表示 judge 和模型交接是否允许使用该值。两者不能合并。
general judge 只供人工检查；缺 judge、模型快照失败或 scheduler 清理未确认时保留 Run，不释放为成功
结果。平台不自动提交榜单，所有输出仍为 `official=false`。
