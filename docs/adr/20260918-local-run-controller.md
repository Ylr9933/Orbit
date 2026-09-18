# ADR：本机 Run 控制采用持久意图、单 worker 和中断清理

状态：本任务分支采纳；集成以 Git 为准。

## 背景

C 批已有冻结 Task，原 Run 内核可同步执行，但 CLI 退出、HTTP 重试、Controller 崩溃和重复资源管理
需要独立的协调职责。直接把同步调用放进 HTTP handler 无法满足实验持续运行与可恢复状态要求。

## 决定

- 用独立 SQLite 命令库保存 operation ID、预分配 Run/Attempt ID、请求、取消意图和结果关联。
  Records 继续是执行证据和产物的保存者；同一 Run 身份贯穿两者，不复制事件库。
- 单个长期 Controller 持有一个资源管理器，首版仅允许一个活跃 Run。使用进程内 worker 调用原同步内核，
  HTTP/CLI 只是客户端；资源不足或忙时明确拒绝，不建立无持久语义的队列。
- flock 与原子 dirty 标记按主机 OS 账户共享，不能通过不同 state-dir 绕开。首版只授权 CPU / 内存，不授权 GPU。
- 重启先按持久 Docker 归属信息证明清理，之后恢复准入。未完成执行标为 interrupted，不自动重放模型会话。
  未确认的 Docker create 保持隔离；不能将“暂时没有查询到容器”解释为释放证明。
- 首个公开执行入口接受已编译科研 Task、已有 Codex 镜像和无评测模式。
  benchmark 隐私边界与隔离评测仍由既有内核负责，后续在显式注册评测协议后接入控制入口。

## 备选方案与代价

- 直接同步 HTTP：实现短，但客户端生命周期与实验绑在一起，无法处理重试和重启。
- 首版即 Ray/分布式队列：扩展性更强，但节点故障与持久 Lease 尚未完成，会扩大验收范围。
- 重启恢复 Agent 对话：需要 Provider 会话持久化、后台进程接管及工具幂等，目前没有这些保证。

当前方案牺牲单机吞吐量，获得明确的身份、失败和恢复边界。命令库与 Records 间没有跨库事务，
因此恢复显式处理“Records 已完成、命令库未收尾”的窗口，保留原结果并追加清理证据。
后续增加并行度、GPU 或多用户时必须先升级资源协调和恢复契约，不能仅修改线程数。

接口及兼容性见[命令参考](../reference/local-run-controller.md)，
故障路径见[实现说明](../implementation/local-run-controller.md)，
证据见[任务记录](../changes/20260918-local-run-controller-d73a91.md)。
