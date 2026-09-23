# BM04 PostTrainBench 实现说明

状态：BM04 任务分支实现，固定 PostTrainBench
`3ed1d32ff1ec1f41282be6f8ebbcec07b19fc3d1`。工程 profile 已验收；真实 H100、HTCondor、
Apptainer、Agent 和 judges 尚未运行，不能视为官方兼容认证。

## 原子运行边界

独立包 [`adapters/posttrain-bench/`](../../adapters/posttrain-bench/) 将一个
`src/eval/tasks/<task>` 映射为一个 `native_job`。训练 Agent、预算内多轮公开 `evaluate.py`、四类
judge、最终 evaluation 和原生 evaluation retry 都属于这一个 job。平台不会把它们拆成可获得额外
预算的多个 Run，也不会把 judge 反馈提前交给 solver。

规划冻结以下内容：

- 固定 Git revision 下的 evaluation task 摘要；
- `run_task.sh`、prompt/templates、judges、结果汇总代码和 submission protocol 的组合摘要；
- Agent、Agent 配置、目标基础模型声明、小时/GPU/CPU/内存/磁盘和外层 job 预算；
- solver 可见的公开 evaluation 与仅供 grader/admin 使用的 runner/judge 材料边界。

真实候选还必须提供 `CandidateRef.target_model`，其 `hf://` URI、不可变 revision 和内容摘要进入冻结
计划。当前固定版本只接受上游列出的四个基础模型。该声明记录模型身份，但真实兼容性仍需在具体缓存
和运行环境中验收。

## 两条执行路径

`engineering` 使用受管本机进程。它调用固定版本 `get_prompt.py` 生成真实 prompt，创建小型
checkpoint-shaped fixture，走 judge schema、指标解释、模型冻结、Records 归档和租约释放。它不调用
Agent、模型、GPU、Apptainer 或 judge 服务，结果始终 `official=false`、`score_eligible=false`。

`native` 使用适配包内的 `PostTrainBackend`，只通过 HTCondor 启动固定 `run_task.sh`：

1. 提交前持久化 operation intent 和完整 `ExecutionSpec`。
2. submit description 写入唯一 `AgentInfraOperationId` 和 spec digest ClassAd。
3. `condor_submit -terse` 返回的 `ClusterId.ProcId` 绑定到持久资源租约。
4. 恢复时先用该 ClassAd 或 job ID 查询 `condor_q`/`condor_history`，不会因响应丢失重复提交。
5. 日志按游标有界采集；取消只对已核验的 job ID 调用 `condor_rm`。
6. job 离开活动队列且 history 显示 completed/removed 后，才确认 scheduler cleanup 并释放租约。

固定上游最终评测会终止 job 内可见的 GPU 进程。因此 native profile 要求 HTCondor 提供独占、受限的
GPU 可见性；适配器拒绝把它作为普通宿主机进程启动。ClassAd 会声明这一要求，但集群策略是否真正
满足仍需管理员验收。

## 权重交接与 Records

`final_model/` 不复制进普通 Records blob。`handoff.py` 执行以下步骤：

- 拒绝符号链接、特殊文件、空模型和缺少 `config.json` 的目录；
- 在授权的 `max_model_bytes` 内逐文件流式计算 SHA-256；
- 复制到私有模型存储的临时目录，复制后重新核对大小和摘要；
- 生成文件级 `MANIFEST.json`，以整棵模型内容摘要命名目录，并原子 rename；
- 将快照文件改为只读，生成带 URI、摘要、大小和文件数的 `model-handoff.json`。

相同内容会复用同一个快照并核对 manifest；中途失败可幂等重试。这里的“不可变”指该受控目录的只读
内容寻址约定，拥有文件系统管理权限的操作者仍可改变权限。当前只实现共享文件系统存储，没有对象
存储复制、跨节点断点续传或远程备份。

Records 保存最多 32 MiB 的白名单 evidence：metrics、时间、prompt、原始/解析轨迹、监控日志和每个
judge verdict；另保存模型 handoff manifest 和平台解释结果。污染或非法模型、禁止 API 使用会令结果
不可计分，PTB lookup 命中会令协议无效；general judge 按上游规则只保留供人工检查。原始 accuracy 与
是否可计分保持分离。

## 维护入口

- `__init__.py`：discover/plan/validate/invocation/interpret；
- `source.py`：固定 checkout、任务和 Agent protocol 校验；
- `backend.py`：engineering/HTCondor 生命周期、原生 job ID、日志、取消与收集；
- `handoff.py`：模型内容寻址快照和 judge/evidence 解释；
- `runner.py`：只负责无模型工程 profile，真实任务由 backend 提交给 scheduler；
- `tests/test_adapter.py`：协议规划、长任务、模型快照和模拟 scheduler 恢复/清理。

新增 scheduler 时应实现同一 `ExecutionBackend` 语义并单独验证 job 身份、资源隔离和 scoped cleanup，
不能在通用 Run 状态机中增加 PostTrainBench 分支。新增模型存储后端应保持同一文件级 manifest 和
内容摘要语义。
