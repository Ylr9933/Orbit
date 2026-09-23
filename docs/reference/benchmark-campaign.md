# BM06：有界 Benchmark Campaign

状态：BM06 在 `feat/benchmark-campaign-bm06` 分支实现，集成以 Git 为准。依赖 BM05-B
的持久队列与墙钟预算组；适用于同一状态目录、单管理员的已冻结 benchmark trial。

Campaign 是**外层**候选比较，不改原生 trial 内训练、episode 次序、评分或正式提交次数。
现有 ASI、PAST、PostTrain、TB-Science 参考适配器没有向 `optimizer` 释放所需的
`after_trial` 指标，因此不能直接宣称这些 benchmark 已支持自动优化；适配包须按原生协议
声明可用于开发迭代的反馈字段。真实模型和官方提交不属于本阶段验收。

## 操作步骤

先用现有 `benchmark plan`、`check`、`prepare` 生成并审阅基线 `baseline.json`。
计划中必须有对应的 `FeedbackRule(recipient="optimizer", release="after_trial", fields=(...))`。
例如将下列策略保存为私有的 `campaign-policy.json`：

```json
{
  "schema_version": 1,
  "campaign_id": "study-a",
  "max_trials": 2,
  "max_wall_seconds": 3600,
  "allowed_parameter_keys": ["learning_rate"],
  "allowed_candidate_fields": ["configuration_digest"],
  "feedback_metrics": ["public_score"],
  "selection_metric": "public_score",
  "direction": "maximize",
  "minimum_improvement": 0.01
}
```

```sh
STATE=/absolute/path/to/benchmark-state
agent-infra benchmark campaign create study-a --policy campaign-policy.json \
  --execution baseline.json --config adapters.toml --state-dir "$STATE"
agent-infra benchmark campaign submit study-a BASELINE_CANDIDATE_ID \
  --config adapters.toml --capabilities capabilities.json \
  --allow-native-runtime --state-dir "$STATE"
agent-infra benchmark campaign status study-a --config adapters.toml --state-dir "$STATE"
```

`status` 查询未完成的原生 Run 并持久化结果，返回的 `feedback` 仅包含策略与适配器
共同开放的有限数值指标；不包含原生评测日志、私有答案、协议审计字段或整个 `native_result`。
此 CLI 仍是单管理员入口；如交给优化 Agent，应只授予 Campaign 视图，不授予可读取完整 Run/Records
的管理员命令或文件系统权限。试验运行期间仍可
使用 `benchmark worker` 推进队列。查看 `run_id` 后，管理员可通过原有 `benchmark status/events`
审计完整运行，但不应把管理员原始结果直接交给优化 Agent。

基线完成且有合法公开分数后，依据返回的反馈修改**授权字段**，重新走 `plan/check/prepare` 生成
`revised.json`；新计划必须保留相同 source、catalog、suite、unit、phase、retry 和反馈规则，并
使用新的 `candidate_id`。随后：

```sh
agent-infra benchmark campaign propose study-a --parent BASELINE_CANDIDATE_ID \
  --execution revised.json --config adapters.toml --state-dir "$STATE"
agent-infra benchmark campaign submit study-a REVISED_CANDIDATE_ID \
  --config adapters.toml --capabilities capabilities.json \
  --allow-native-runtime --state-dir "$STATE"
agent-infra benchmark campaign status study-a --config adapters.toml --state-dir "$STATE"
```

可信本机进程示例可改用 `--allow-host-process`，但不能隔离私有评分材料。`submit` 再执行
既有适配器、来源、invocation 和能力预检。每个候选只有一个确定性 operation ID；丢失提交回执
后重复同一 `submit` 可恢复，不会另起 trial。所有候选、失败、分数缺失、父子关系、修改字段、
依据反馈及 Run/Attempt ID 都保存在 `STATE/benchmarks/campaigns/campaigns.sqlite3`；运行证据
仍在原 BM01/BM05 控制库及 Records。

`max_trials` 限候选数（包含基线），`max_wall_seconds` 复用 BM05-B 的同组预留与实测扣减；
缺测量时按完整预留额收费。最终选择只在执行完成、评分有效、协议有效且清理确认的候选之间
比较 `selection_metric`。达到次数上限、后一候选没有超过 `minimum_improvement`，或管理员
调用 `benchmark campaign stop` 时停止。这里选的是**本策略允许的开发指标**，不能称为官方榜单
分数。当前不提供模型 token/费用硬预算、自动 LLM 生成候选、自动官方上传或跨节点 Campaign。
