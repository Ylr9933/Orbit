# Benchmark 持久队列与租约操作

状态：BM05-A 已集成；BM05-B 在任务分支实现，集成状态以 Git 为准。适用于单机、单管理员、
同一 benchmark 状态目录中的有界并发任务。租约不替代 Docker/cgroup/GPU 限额，也不是多节点调度器。

## 查看和推进

```sh
INFRA_BENCH_STATE=/absolute/path/to/benchmark-state
agent-infra benchmark queue --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark reconcile --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark worker --state-dir "$INFRA_BENCH_STATE" --poll-seconds 2
agent-infra benchmark status RUN_ID --state-dir "$INFRA_BENCH_STATE"
```

`queue` 是只读视图，返回等待中的 Run、预算视图、容量和全部租约历史。默认最多一个未释放租约。
管理员可以在没有活动租约时设置容量：

```sh
cat >capacity.json <<'JSON'
{"max_concurrent": 2, "cpu_cores": 4, "memory_bytes": 8589934592, "gpu_count": 0}
JSON
agent-infra benchmark capacity --file capacity.json --state-dir "$INFRA_BENCH_STATE"
```

此配置仅用于同一状态目录的准入，不能限制进程或原生 runner 的子容器。数值上限只有显式配置才
校验；改配置必须先清空所有活动租约。任务严格 FIFO：队首资源不足时后续任务等待。`reconcile`
推进一次队列；`worker` 周期性推进，适合用进程监管器守护。`--until-empty` 处理完当前队列即退出，
`--max-seconds N` 限制 worker 本身运行时间。停止 worker 不会杀掉已启动任务。

批次墙钟预算可在每次 `run` 提交时指定相同组名和总上限：

```sh
agent-infra benchmark run execution.json --operation-id trial-1 \
  --allow-host-process --config adapters.toml --capabilities capabilities.json \
  --budget-group study-a --budget-wall-seconds 3600 --state-dir "$INFRA_BENCH_STATE"
```

未完成任务预留其计划时长，完成任务优先按测得时长扣减；测量缺失时仍扣完整预留额。超额任务
以 `never_launched` 失败，不会调用原生后端。同组必须使用同一限额。当前不管理 token/费用预算。

重复使用相同 `operation-id` 和相同参数会返回原 Run；参数不同会拒绝。等待项可以取消，且不会调用
执行后端：

```sh
agent-infra benchmark cancel RUN_ID --state-dir "$INFRA_BENCH_STATE"
```

## 状态与故障处理

租约的 `allocated`、`active`、`reconciling` 都占容量；`released` 保留为历史但不再占用。
`native_id` 将平台租约与原生进程或外部任务关联。出现 `quarantined`/`reconciling` 时，先查询原生
任务、日志和清理收据；不要删除 SQLite 文件或换状态目录绕过占用。提交回执丢失时，继续对同一
Run 执行 `status`/`reconcile`，系统会先查询原生身份，不会直接重新启动。

需要备份或迁移时，应停止新的提交，确认所有任务为 `finished`、所有租约为 `released`，再一起复制：

```text
STATE/benchmarks/control.sqlite3
STATE/benchmarks/leases/leases.sqlite3
STATE/benchmarks/native/
STATE/benchmarks/records/
STATE/benchmarks/workspaces/
```

SQLite 容量配置属于状态目录身份。受管进程的最终结果提供进程组 CPU、内存、I/O 最佳努力采样；
`actual_allocation_status=not_attested` 表示尚无实际分配证明。Harbor 单项目容器可记录 Docker inspect
限额证明，不能把宿主机父进程采样当作容器用量。大产物导入中断后可在同一状态目录续传；保留
`native/`、`records/`、`workspaces/` 与 SQLite 一起备份。跨状态目录/节点的全局配额、远端 Worker、
容器级 GPU 用量监控和远端大文件传输尚未实现。
