# I 批实现导读

状态：首版实现；用法见[参考](../reference/research-iteration.md)，证据见[任务记录](../changes/20260920-research-iteration-i73c9a.md)。

## 模块与修改入口

| 文件 | 职责 |
| --- | --- |
| `projects/iteration_api.py` | 小型 JSON/标识/数值/指标指针校验，不负责存储与运行 |
| `projects/_iteration_store.py` | 复用 ProjectDatabase 的文档读写；写入者持有已有跨进程 writer 锁 |
| `projects/analysis.py` | 通过 RunQueries 验证可见证据，提取指标，保存不可变分析与决策恢复状态 |
| `projects/iteration.py` | 精确任务授权、次数/时间预扣、停止条件、提交回执和恢复 |
| `runs/control_api.py` | preparation_identity：提交临界区再次核对镜像、lineage、资源 |
| `runs/controller.py` | 原单实验执行槽；新增有独立租约的 Planner companion，复用总资源管理 |
| `runs/planner.py` | 临时 Planner 生命周期、认证副本、日志、标准化轨迹与清理 |
| `runs/planner_bridge.py` | 有大小限制的文件消息；不跟随符号链接/特殊文件，不执行文件内容 |
| `environments/planner_client.py` | 可复制到容器的标准库 CLI helper，无宿主机地址或凭据 |
| `bootstrap/iteration.py` | 唯一组装处：把 Projects 用例注入已有 ResearchController 和受限 Planner 回调 |
| `gateways/cli/study.py`、`gateways/mcp/study.py` | 参数转换；业务规则留在用例中 |

不引入新的数据库服务、Docker 管理器或编排引擎。Project schema 4 新增 iteration_documents，
按 project/kind/id 存 analysis/decision/workflow；旧表不重写，首次写入时迁移。
只读旧库返回空集合。旧版本程序不能读取 schema 4，回退需使用事先备份，不可直接降低版本号。

## 数据与恢复

Analysis 保存原请求、已验证的 Run 结果/lineage、成员摘要和提取的数值。
解释与原始 Records 分离；同 operation-id 参数不变则幂等，修改解释使用新分析并引用 supersedes。
数据/代码版本为明确标记的调用者声明；冻结材料摘要单独保留，程序不冒充科学协议验证器。

Decision 先保存 applying，然后复用 ResearchService 的幂等 save、精确 confirm，最后标记 completed。
三个阶段由 Project writer 锁覆盖；崩溃后以同 ID 重试恢复。并发普通研究修改先完成时，CAS 拒绝过期决策。
既有投影冲突处理继续生效，旧分析/Task/Run 从不重写。

Workflow 授权解析已采用的冻结 Task，并记录实际 image ID、资源和 submission。
step 在跨进程锁内检查 scope、前一 Run、预算、墙钟期限，先持久保存动作/完整 timeout 预扣，
再通过原 Controller 的确定性 operation-id 提交。最终准入临界区再次验证 execution identity，避免检查后镜像变化。
重启读取 Controller 回执即可关联 Run；提交前崩溃的动作可显式按原 ID 恢复，启动后不重放。
本实现保守地不退还未用时间，避免崩溃/取消时预算不确定性。

## Planner 隔离与记录

Planner 不占单实验槽，独立租约计入同一 LocalResourceManager 总量；一次只允许一个 Planner。
Controller 完成实验时只忽略仍在运行、受管理的 Planner 租约；清理不确定的租约触发隔离，不能当作空闲。
Planner 的 Docker 所有权日志进入原恢复目录，认证副本使用 D 的任务目录，重启统一对账。

文件代理只允许五个绑定 project/workflow 的动作。容器可以提交消息，但没有创建授权/修改绑定的 API。
宿主机按 dirfd + O_NOFOLLOW 读取普通文件并检查大小，用新临时文件原子替换响应；不把消息当 Python/Shell。
任意错误仍由业务 scope 和预算校验处理。代理层是本地可信宿主机的协议，不是多租户网络服务。

每个 Planner 的 producer/stream ID 含 Run ID，防止跨会话冲突。
原生 stdout/stderr 先归档，规范化 Agent 事件使用单独 producer，关联原始 blob。
Planner 退出、清理和实验成功分别记录；会话停止不等于实验取消，也不代表科学任务完成。

## 扩展方式与限制

新模型 Agent 通过已有 CommandAgentAdapter 扩展，Planner 的正式组装当前使用 Codex；fixture 仅由测试显式注入。
新停止条件应加在 IterationService，新的证据格式放 AnalysisService/Records 公共查询，避免塞入 MCP 函数。
开放生成新 Task 前应先设计可代码验证的授权边界；不能仅凭提示词限制预算。
Planner 模型预算和实验预算独立，未知费用不推算成零。网络遵循既有 Docker/模型代理行为，不承诺全网络沙箱。
