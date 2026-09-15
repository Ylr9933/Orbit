# 单节点 Run / Environment 使用说明

状态：首版 Python API；设计边界见[执行契约](../architecture/run-environment-contract.md)。真实 Docker 验证采用确定性命令夹具，未调用真实模型。尚无 Run CLI、HTTP 运行接口或分布式 Worker。

## 1. 两种完成方式

| 任务声明 | 实际流程 | 返回结果 |
| --- | --- | --- |
| evaluation 为 none 或未提供 | 求解 → 停止/移除容器 → 收集产物 → 释放资源 | status=completed、evaluation_status=not_requested |
| evaluation 指定已注册协议 | 求解 → 冻结提交 → 可选提交执行 → 独立 scorer → 清理 | 执行状态、评测状态与允许反馈分别返回 |
| evaluation 为 unknown，或指定协议未注册 | 前置拒绝 | 不启动求解，不静默省略评测 |

科研训练建议明确写 evaluation: {state: none}。outputs 中声明要保留的模型、日志或报告路径；仅收集这些路径，不自动打包整个工作区。没有输出约定时仍能结束求解，但不会自动收集训练产物。正常退出与必需文件存在不证明科研结论正确。

## 2. 公共入口

- runs.api.RunRequest：任务清单、资源 YAML、求解镜像、求解超时、联网选项、已安全准备的 Agent 配置目录。
- runs.service.LocalRunService：注入 Environment、ResourceManager、节点身份和可信评测注册表；run(request, agent, cancellation=event) 同步执行一次 Attempt。
- environments.api.Environment：prepare/start/observe/cancel/cleanup/collect；Docker 实现为 environments.docker.DockerEnvironment。
- tasks.execution.EvaluationRecipe：可信代码注册评分命令与反馈投影；任务清单仅引用 evaluator_ref，不直接执行任意评分命令。
- records.local.LocalRunJournal：本地 controller 事件和最终结果。

Environment 接收通用命令，不理解 Codex、任务清单或资源调度。Run 消费现有 CommandAgentAdapter 启动计划，仅允许工作区和单次运行配置目录挂载。宿主机 Agent 控制容器、交互会话及自动重试不属于本轮入口。

## 3. 组装方式

以下为真实 API 集成示例，**并非本轮执行过的模型测试**。前置条件：本机 Docker、已安装 Agent 的可信镜像、已登录的 Codex、明确的输出和资源预算。不要把私有答案或宿主机账号烘焙进镜像。

~~~python
from pathlib import Path
from agent_infra.agents.codex import CodexAdapter
from agent_infra.environments.docker import DockerEnvironment
from agent_infra.resources.api import NodeCapacity
from agent_infra.resources.local import LocalResourceManager
from agent_infra.resources.monitor import LinuxHostResourceMonitor
from agent_infra.runs.api import RunRequest
from agent_infra.runs.service import LocalRunService

# 独有、位于任务输入目录之外的状态目录。
state = Path("/absolute/private/run-state")
image = "your-built-agent-image:tag"
agent = CodexAdapter(container_image=image)
credentials = agent.stage_container_credentials(state / "staged-codex")
monitor = LinuxHostResourceMonitor()
snapshot = monitor.sample()
# 本服务获准管理的容量，不等于机器全部资源。
resources = LocalResourceManager(
    NodeCapacity(snapshot.node_id, cpu_cores=2, memory_bytes=4 * 1024**3)
)
resources.update_snapshot(snapshot)
service = LocalRunService(
    DockerEnvironment(state / "environments"),
    resources,
    state / "runs",
    node_id=snapshot.node_id,
)
result = service.run(
    RunRequest(
        task_manifest=Path("/absolute/task/task.yaml"),
        resource_file=Path("/absolute/resources.yaml"),
        solver_image=image,
        timeout_seconds=3600,
        network=True,
        credential_home=credentials,
    ),
    agent,
)
print(result.status, result.evaluation_status, result.submission_root)
~~~

每次申请前更新资源快照；并发 Run 必须共享 ResourceManager，多个 Python 进程的内存租约不会互相协调。waiting 直接返回，不在服务内排队。预算按管理员授权调整，资源 YAML 仍受到任务约束校验。

Agent 配置再次复制到单次运行目录，求解容器只能访问副本；评测不复用它。凭据和原始日志可能敏感，由 controller 管理保留/删除策略，不上传 Git 或直接作为 Agent 反馈。

## 4. 注册评测

EvaluationRecipe 指定：

- image、scorer: ProcessCommand：可信评分镜像与命令；无网络、无 Agent 凭据。
- material_ids：仅 evaluator 可见材料，分别挂到 /inputs/<id>。
- result_path：scorer 工作区的 JSON 结果，默认 result.json，限制 1 MiB。
- project_feedback：仅返回原协议允许的字段；feedback=none 时不返回细节。
- 可选 submission_command、submission_image、prediction_paths：先运行不可信提交，只挂 /submission，不提供答案；预测冻结后才传给 scorer。

两个阶段的 /workspace 都是新目录。无 submission_command 时，scorer 读取冻结提交；有该命令时，只读取冻结预测。评分程序必须把提交当数据，不得 import 提交模块、执行提交命令或反序列化不可信 pickle。需要额外公开数据的提交运行协议应扩展显式输入契约，当前不会把任务材料整包挂入。

原生 execution_policy/native environment 尚无适配器，Run 会拒绝执行，防止忽略 benchmark 预算或环境要求。任务镜像声明必须与实际 Agent 镜像一致。已有 Tasks 内存 fixture evaluator 不会自动变成容器评测器。

## 5. 记录与失败处理

Run 状态目录的 <run-id>/records/ 保存 events.jsonl 和 result.json。事件记录 handle_id；Environment 状态目录的 <handle-id>/ 保存 ownership.json、stdout 和 stderr。工具调用仅在 Agent 本身输出时保留，不补造轨迹。stdout/stderr 各默认保留前 8 MiB，超出时标记截断。

单次运行目录中的 solver-submission 保存提交，submission-submission 保存预测，scorer-submission 保存私有评分输出。默认产物上限 1 GiB；科研大模型需要显式配置 DockerEnvironment 的 artifact_limit_bytes。

cleanup_complete 表示容器移除已核实，lease_released 表示分配器确认释放。清理不明则保留租约；管理员根据 ownership.json 对账，仅处理本任务容器。产物和 controller 日志会保留；cleanup 不表示删除这些文件。首版没有持久租约、崩溃自动恢复或自动清理凭据机制。

要求 controller 和 Docker daemon 位于同一宿主机，绑定路径可访问，状态目录不向 Agent 暴露。不可把 DOCKER_HOST 指向其他节点使用此协调器。控制端文件与镜像由可信管理员维护；容器隔离不能防御拥有宿主机写权限的操作者。跨节点执行需要后续 Worker 契约。

## 6. 验证入口

~~~bash
make check
make test
uv run --locked pytest tests/e2e/test_run_environment.py -q
~~~

最后一项实际运行 Docker；需本机已有 python:3.12-slim 与 Docker 权限。串行使用 1 CPU/256 MiB，阶段上限 15 秒，无 GPU、模型或网络。覆盖仅求解、独立评分、执行提交代码、错误答案、私有材料不可见、只读输入、超时/取消、后台进程清理和非法产物路径。

CPU/内存配置在 start 中从 Docker 读取回验。GPU UUID 透传已实现，但没有 GPU 执行证据；不能据此宣称 GPU、多节点、真实 Agent 或原生 benchmark 闭环通过。
