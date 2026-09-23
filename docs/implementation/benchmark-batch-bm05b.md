# BM05-B 批量执行实现

状态：本任务分支实现；以任务记录中的测试与最终 Git 集成状态为准。

BM05-B 沿用 BM05-A 的控制库 FIFO 队列和 Resources 租约账本，没有另建调度器。
管理员用 `benchmark capacity --file capacity.json` 设置一个状态目录的授权容量；配置和所有租约
保存在同一个 SQLite 文件。重启后直接读取持久配置。调整容量要求先释放所有租约，防止在执行中
改变授权边界。`max_concurrent` 控制槽位；CPU、内存、GPU 数值只有显式配置时才参与总量准入。
FIFO 队首无法取得资源时，后续任务继续等待，不做可能饿死大任务的回填。

`benchmark worker` 周期性调用既有 reconcile/status 流程。每个状态迁移仍受控制库跨进程锁保护；
多个 worker 同时存在也不能绕过租约事务。worker 可在队列清空时退出，或运行到指定时间；中断
worker 不杀掉其已启动的受管进程。它不跨状态目录共享容量，也不替代 systemd 等进程监管。

`run --budget-group NAME --budget-wall-seconds N` 将多个冻结执行归入一个墙钟预算。提交顺序是
预算预留顺序：未完成任务占用冻结计划的上限，已完成任务优先按测得时长记账；若没有可信终态
用量则按完整预留额记账。超出预算的任务会持久记录为未启动失败。组名和限额进入幂等请求，
相同组名使用不同限额会拒绝。当前预算只有单状态目录内的墙钟时间；模型 token、费用和跨节点
预算需要新的计量来源。

运行状态和最终 Records 结果分开显示 `requested`、`authorized`、`actual_allocation`、`usage`。
普通受管进程只有租约授权，没有 cgroup/GPU 实际分配证明；它可采样本机进程组的 CPU、内存与
Linux `/proc` I/O，并在进程结束时记录子进程 rusage。Harbor 单项目容器限额可从原生 Docker
inspect 证明；父进程用量不会冒充容器内部用量。其他原生后端没有采集到的字段为 `null`，
尤其不能把 GPU 申请量当作 GPU 显存用量。取样会漏掉极短进程、进程组外进程及采样间隔内峰值。

大产物依次经过两层恢复：受管后端将声明输出复制到本次 operation 的 `collecting/`，每个文件
比较已有前缀并续传，全部校验后原子发布 `collected/`；Records 将文件流式导入按摘要命名的
私有 blob，保留未完成 `.part`，完整摘要核对后发布正式 blob 与 artifact manifest。崩溃后
重复 `status/reconcile` 只重试收集，不重新启动原生任务。未完成 `.part` 不能通过 Records 读取。
单次声明产物上限可由适配器提高至 1 TiB；实际可用空间、备份和跨节点传输仍由部署者负责。
