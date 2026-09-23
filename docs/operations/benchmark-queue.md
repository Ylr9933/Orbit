# Benchmark 持久队列与租约操作

状态：BM05-A 已实现，集成状态以 Git 为准。适用于单机、单管理员、同一 benchmark
状态目录中的低并发任务。它不替代 Docker/cgroup/GPU 限额，也不是多节点调度器。

## 查看和推进

```sh
INFRA_BENCH_STATE=/absolute/path/to/benchmark-state
agent-infra benchmark queue --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark reconcile --state-dir "$INFRA_BENCH_STATE"
agent-infra benchmark status RUN_ID --state-dir "$INFRA_BENCH_STATE"
```

`queue` 是只读视图，返回等待中的 Run 和全部租约历史。`queued` 项只由 FIFO 队首尝试准入；
默认最多一个未释放租约。`reconcile` 按提交顺序查询未完成项：前一项获得正向清理证据并完成 Records
收尾后，后一项才可取得租约并启动。当前没有常驻调度循环，因此需要定期调用 `status` 或
`reconcile` 推进。

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

SQLite 容量配置属于状态目录身份。BM05-A 的 CLI 使用默认单槽配置；不要用另一容量参数直接打开
已有账本。跨状态目录配额、公平优先级、后台自动调度、实际资源采样与远端 Worker 属于 BM05-B。
