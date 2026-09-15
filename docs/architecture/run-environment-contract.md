# Run / Environment 最小执行契约

状态：首版 Python API 已实现；使用与限制见[执行说明](../reference/run-environment.md)，验证证据见[任务记录](../changes/20260915-run-environment-91c2ae.md)。

## 1. 范围与隔离规则

首期实现单节点、单 Attempt、顺序阶段：求解 → 停止并移除求解容器 → 冻结提交 → 可选提交程序执行 → 独立可信评分 → 清理 → 释放租约。资源不足直接返回 waiting/unsatisfiable，队列调度由后续服务负责。

日常科研支持仅求解：evaluation=none/unspecified 时，求解完成 → 收集训练模型/日志等产物 → 清理 → 释放租约，evaluation_status=not_requested，由用户人工查看结果。已声明评测但缺少实现时必须报错，不能悄悄变成未评测成功。

求解容器只收到 Tasks 的 solver 视图材料、任务私有 Agent 凭据和启动计划。完整 task.yaml、参考答案、私有评测脚本及日志不进入求解工作区。隐藏文件禁止进入求解镜像层；部署者提供可信干净镜像，运行前固定到本地 image ID。

评测绝不重用求解容器、可写层或凭据。若需要执行提交代码，先在无答案的 submission 容器生成预测，再由 scorer 容器将预测当数据比较。可信评分器不能 import/执行提交代码；第一版通过显式注册的 EvaluationRecipe 区分这两个阶段，未知评测器前置失败。

## 2. 模块职责与公共契约

Environment 不依赖 Agent/Tasks 的实现，不访问任务总目录；Run 将已批准计划翻译为通用 ProcessCommand 和 SandboxSpec。CPU、内存和 GPU UUID 全部来自已有 ResourceLease，Environment 仅执行限额，不重新分配。

| 契约 | 语义 |
| --- | --- |
| SandboxSpec | attempt/phase、可信镜像、已分配 CPU/内存/GPU、只读输入、受控可写工作区、网络策略 |
| EnvironmentHandle | 本后端创建的环境身份；不暴露 Docker client |
| ProcessCommand | 无 shell 拼接的 argv、cwd、stdin、显式环境变量、执行超时 |
| prepare | 校验输入与限额，记录环境身份；同 key 相同配置幂等，不同配置拒绝 |
| start | 创建受限 Docker 并启动命令；单环境只执行一次，失败也必须清理 |
| observe | 返回 running/退出/取消/超时/OOM 等状态与可续读、限量日志 |
| cancel | 停止整个容器，不能只杀 Agent 主进程 |
| cleanup | 检查所有权后移除容器并验证不存在；未知状态返回未完成 |
| collect | 仅在容器已移除后复制声明的普通产物；拒绝链接、特殊文件、越界及超量 |

容器采用显式 CPU/内存/pids 限制、cap-drop ALL、no-new-privileges、只读根文件系统和独立临时目录。默认无网络；真实 Agent 调用模型可由可信运行配置显式开启网络，但不开放 Docker socket、宿主机 namespace 或任意额外挂载。

## 3. Run 协调与状态

Run 复用 Tasks 的加载/摘要/可见视图及资源 YAML 校验，签发一次租约，顺序执行各阶段。生命周期日志记录 preparing、allocated、各 solver/submission/scorer 阶段的开始与结束。最终执行结果区分 completed、failed、cancelled、timed_out、oom、cleanup_failed、waiting、unsatisfiable；首版不是可恢复的持久状态机。

返回值分开表达执行状态、评测状态/允许反馈、cleanup_complete 和 lease_released。正常退出不等于判分通过；错误答案仍可以是评测执行成功。清理失败不覆盖原执行原因，且禁止释放租约。所有阶段共用同一租约并顺序执行，不并行超卖。

Run 在 finally 中尝试清理所有已注册 handle；即使 Docker create/start 部分失败也要核对。只在全部清理确认后释放资源。任务 key、环境所有权和容器 labels 防止跨任务误删。

## 4. 提交与反馈边界

先移除求解容器，再收集输出到新的 controller-owned 目录并生成内容摘要；文件只读，后续容器以只读方式挂载。提交程序产生的预测也经过相同冻结过程。评测启动前后核验摘要。

scorer 私有输出与 stderr 仅保存在 controller 记录目录；Run 通过注册的反馈投影函数返回允许字段。feedback=none 时不返回评分细节；native 策略必须由 adapter 明确提供，不能默认把任意 stdout 当公开反馈。

本地 Records 保存有权限限制的生命周期 JSONL、最终结果及各阶段原始日志。记录在求解容器外。首版不提供崩溃后自动续跑；进程/节点失联不能据此自动回收 lease，后续需持久化 allocator 和容器对账。

## 5. 验收

- 确定性测试：成功、错误答案、启动失败、取消、超时、清理失败保留租约、未注册评测器拒绝、反馈过滤。
- 真实 Docker：本机 CPU-only、小文件，无模型调用、GPU、Ray 或外部网络；最多顺序使用 1 CPU/256 MiB，单阶段最多 15 秒，整体测试预算 3 分钟。
- 使用已存在的 python:3.12-slim（固定实际 image ID），容器名称带本任务所有权前缀；仅清理本测试创建的容器。
- 验证求解不可读私有标记、提交程序不可读答案、评分容器为独立实例、只读挂载生效、CPU/内存限额、后台进程被清理、符号链接产物拒绝、取消/超时后无残留。
- 真实 Agent 的付费模型行为、GPU enforcement 和原生 benchmark 评分等价不属于这个 CPU 执行契约验收，需后续明确运行预算后验证。
