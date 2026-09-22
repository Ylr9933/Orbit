# PAST-Bench BM03 试运行

状态：BM03 任务分支；工程 profile 已实现。命令适用于 Linux 单管理员环境，固定上游 revision
`f8223517ae7491e776b69793d9f11e9d074ab42e`。它不会提交榜单。

## 无模型工程验收

准备固定 checkout，并通过环境变量告诉验收脚本其位置：

```bash
git clone https://github.com/Gen-Verse/PAST-Bench.git /private/PAST-Bench
git -C /private/PAST-Bench checkout f8223517ae7491e776b69793d9f11e9d074ab42e
PAST_BENCH_CHECKOUT=/private/PAST-Bench \
  uv run --locked python scripts/acceptance/past_bench.py
```

脚本构建核心和独立适配 wheel，在临时虚拟环境中安装，运行 SM01 family 的完整配对 fixture，检查
状态隔离、原生聚合、Records 产物和租约释放，并删除临时状态。它不调用模型、Docker 或 GPU。

## 手动工程运行

先把核心 wheel、适配 wheel 及其固定依赖安装到专用环境。不要在执行过程中升级该环境。然后复制
配置文件到私有工作目录，并将 `request.json` 中 selection 与 source family 对齐：

```bash
agent-infra benchmark inspect past-bench \
  --config adapters.toml \
  --source /private/PAST-Bench/self-evolve-tasks-v2/memory_ability/SM01_preference_adoption
agent-infra benchmark plan past-bench \
  --config adapters.toml \
  --source /private/PAST-Bench/self-evolve-tasks-v2/memory_ability/SM01_preference_adoption \
  --request request.json --output plan.json
agent-infra benchmark check plan.json --config adapters.toml --capabilities capabilities.json
agent-infra benchmark prepare plan.json --config adapters.toml --output execution.json
agent-infra benchmark run execution.json --config adapters.toml \
  --capabilities capabilities.json --allow-native-runtime \
  --operation-id past-sm01-engineering --state-dir /private/agent-infra-state
```

使用 `benchmark status`、`events` 和 `artifacts` 查询 Run。工程 capability 文件只覆盖
`protocol-fixture`，不能证明任何真实模型组合兼容。

## 真实 Agent 模式

从同一固定 checkout 安装所选上游 Agent 子包，并创建只含 API key 的私密文件：

```bash
install -m 600 /dev/null /private/secrets/past-agent.key
```

由操作者写入 key 后，在请求中使用以下参数；不要把 secret 内容写进 JSON：

```json
{
  "candidate": {
    "agent": "hermes",
    "agent_version": "past-f8223517ae74",
    "model": "provider/model"
  },
  "parameters": [
    {"key": "mode", "value": "native"},
    {"key": "agent_key_file", "value": "/private/secrets/past-agent.key"},
    {"key": "timeout_seconds", "value": "21600"}
  ]
}
```

支持的 Agent 是 `hermes`、`hermes-plus`、`nanobot`、`zeroclaw`。需要 judge 时同时给出
`judge_key_file`、受支持的 `judge_key_env` 和可选 `judge_model`；没有 judge 的结果会标为
`review_required`。凭据路径会进入冻结计划用于审计，凭据内容不会进入计划或命令行。

真实运行前应新增与实际 suite digest、runner digest、Agent、model 和 backend 完全匹配的 capability
claim，并明确模型费用、网络、时间和清理范围。当前 BM03 未做真实模型验收，也没有启用 PAST Docker
sandbox；因此不能把结果称为官方复现或安全运行不可信任务。

## 结果检查与排障

`native-result.json` 是平台摘要，`past-output/` 是权威原生证据。重点检查两条分支的 episode 顺序、
summary、comparison、session/history 字段和 `infra_blocked` 列表。任务完成后 lease 必须为
`released`；仅有平台摘要而缺少原生目录不能作为有效证据。

规划失败通常表示 checkout revision、工作树、family 路径或 runner 已漂移，应恢复固定来源后重新
生成计划。执行失败时保留 Run/Records，不要手工修改输出再解释；使用新 operation ID 运行新的 trial。
