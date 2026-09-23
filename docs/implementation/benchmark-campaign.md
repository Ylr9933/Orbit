# BM06 实现导读

状态：本任务分支实现；具体检查见[任务记录](../changes/20260923-benchmark-campaign-bm06-7a31d9.md)。

`benchmarks/campaign_api.py` 定义版本化、严格校验的策略；`projects/benchmark_campaign.py`
管理外层候选决策。`bootstrap/benchmark_execution.py` 把 Campaign 的确定性 operation ID
交给既有 `BenchmarkExecutionService`，并在每次提交前重复适配器与能力预检。CLI 只解析参数。
Campaign 的 SQLite 文件不复制 Run 原始结果；本次试验的原生 handle、清理、日志、产物及详细
评测证据仍归原有控制库和 Records 管。

创建时保留完整冻结执行快照和摘要。提出后继候选时，比较相同的 adapter/source/catalog、
suite、unit、phase、retry、feedback 与 selection，仅接受策略列明的候选配置字段或参数键变化。
当前不允许修改 judge、目标模型、原生预算和评测材料；新增修改范围要先扩展版本化策略与验证。
父候选必须有完成且协议有效的公开分数，后继保存父 Run ID 和当时允许的反馈快照。

提交先持久化 `submitting` 和由 Campaign/Candidate ID 推导的 operation ID，再调用 BM05-B；
崩溃后重复提交沿用同一 ID，由 Run 层负责幂等与原生身份对账。每个 Campaign 使用独立墙钟预算
组；计划占用与实测收费由 BM05-B 持久账本负责。Campaign 只计入成功提交的候选，不把原生
runner 内的 episode 或训练步伪装成额外 trial。

`status` 查询对应 Run，只有 `execution=completed`、`evaluation=scored`、
`protocol=valid` 且清理已确认时，才从 `native_result.metrics` 中摘取策略与原生
`FeedbackRule` 共同允许的有限数值；未命中的私有字段和原始日志不进入 Campaign 文档，
管理员审计状态仅存在私有文档、不进入返回视图。CLI 本身没有多用户权限隔离。
选择规则是方向、最小改进和次数上限；无有效分数的候选仍保留并可触发停止。重复查询完成的
Campaign 不修改状态。合成测试验证两候选、私有字段隔离、失效评分、范围拒绝及提交响应丢失；
它不是原生 benchmark、真实 Agent 或官方分数等价性证明。
