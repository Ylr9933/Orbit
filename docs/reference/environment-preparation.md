# E 批：Python CPU 环境准备

状态：E 分支实现；验证结果见[任务记录](../changes/20260920-environment-preparation-e92b6a.md)。
基于已实现的[本机 Controller](local-run-controller.md)和[宿主机 MCP](host-research-mcp.md)。
使用同一 OS 用户、同一 `--state-dir`，需要本机 Docker、已下载的可信 Python 3 镜像和已注册的 Project。
服务不会自动拉取镜像、调用模型、读取账号或把整个项目作为构建上下文。

## 1. 从需求到可执行环境

```text
用户目标 / 已采用研究方案
  → intent：固定基础镜像、必须验证的 import、Agent 层、允许依赖、网络和预算
  → proposal v1：精确版本依赖、提出者、原因
  → build：资源准入、安装、发布固定镜像
  → 新容器 smoke：import、依赖版本、工作区读写、Agent 版本
  → 成功：lock_id + image_id → H 长期环境或 D 冻结 Task
  → 失败：保留日志 → Agent 修订 proposal → 在同一个 intent 的预算内再试
```

`intent` 不会因为构建失败被自动改写。Agent 可以修订依赖，不能删掉必需的 import、
改变基础镜像、扩大挂载、开启原本不允许的网络或追加预算来绕过失败。
达到次数或时间上限后停止；用户作出新的授权决策，才可以新建计划。
预算按每份 intent 约束，这是同一可信用户的协作工具，不是阻止宿主机所有者新建计划的计费系统。

## 2. CLI：准备、查看、取消

先按运行指南启动 Controller，例如另一个终端运行：

```bash
agent-infra controller serve --state-dir /path/to/state --cpu 1 --memory-gib 2
```

`/path/to/state` 和后文的 `PROJECT_ID`、`PLAN_ID`、`ATTEMPT_ID`、`LOCK_ID` 都需替换为自己的值。
可直接使用仓库中的[示例 intent](../../examples/environment-preparation/intent.yaml)与[示例 proposal](../../examples/environment-preparation/proposal.yaml)，或准备一份 `intent.yaml`：

```yaml
goal: 为 CPU 科研准备可以导入 six 的 Python 环境
base_image: python:3.12-slim
template: python-cpu
imports: [six]
allowed_packages: [six]
agent: none
network: true
cpu: 1
memory_bytes: 2147483648
max_attempts: 3
total_seconds: 600
attempt_seconds: 180
valid_seconds: 86400
```

- `base_image` 保存时解析为本机固定 image ID，之后 tag 移动不改变当前计划。
- `template` 为 `python-cpu` 或 `existing`。后者只复用并验证镜像，不安装依赖，不声称发生了构建。
- `allowed_packages` 是允许直接声明的公开包名；可包含其必要传递依赖，安装结果记录版本和下载包哈希。
- 仅支持精确 `name==version`，从公开 PyPI 安装 wheel；不支持 URL、私有源、源码构建、额外 pip 参数或任意 Dockerfile。
- `agent: codex` 要求基础镜像已有 Codex 0.154.0 及原 D 批 provider 标签，smoke 会实际执行版本检查。
  可使用 D 批的 `agent-infra/codex-research:0.154.0`；E 继承 Agent 层，不重新读取宿主机登录配置。
- 默认 CPU 1 核、内存 2 GiB，可指定正数 CPU 和至少 64 MiB 内存；实际受 Controller 授权总容量与宿主机可用资源约束。
  最多 5 次、累计 1800 秒、单次 600 秒。
  无可用资源时明确拒绝，不排队、不超配。只有包安装阶段按 intent 联网，smoke 不联网。

```bash
agent-infra environment plan --project-id PROJECT_ID --state-dir /path/to/state \
  --file intent.yaml --operation-id prepare-intent-1
```

保存返回的 `plan_id`。再准备 `proposal.yaml`：

```yaml
dependencies: [six==1.17.0]
source: user
reason: CPU 实验代码需要 six，固定版本以便追踪
```

```bash
agent-infra environment propose PLAN_ID --project-id PROJECT_ID --state-dir /path/to/state \
  --expected-revision 0 --file proposal.yaml --operation-id propose-1
agent-infra environment build PLAN_ID --project-id PROJECT_ID --state-dir /path/to/state \
  --revision 1 --operation-id build-1
agent-infra environment status PLAN_ID --project-id PROJECT_ID --state-dir /path/to/state
```

构建异步执行，CLI/MCP 退出不影响工作。状态中的 `attempts` 保存每次尝试，只有 `status: ready` 且
`cleanup_complete: true` 才有可用 `lock`。`image_id` 存在也可能只是构建成功、smoke 失败。
查看一次尝试的日志：

```bash
agent-infra environment status PLAN_ID --project-id PROJECT_ID --state-dir /path/to/state \
  --attempt-id ATTEMPT_ID --cursor 0
agent-infra environment cancel PLAN_ID --project-id PROJECT_ID --state-dir /path/to/state \
  --operation-id cancel-1
agent-infra environment list --project-id PROJECT_ID --state-dir /path/to/state
```

日志返回 UTF-8 文本和下一字节游标，每页最多 32 KiB。取消是请求，应继续查询终态和清理结果。
相同 `operation-id`、会话及参数用于网络重试，返回原回执；新动作使用新 ID。
失败后的新提案需要当前 `expected-revision`，新构建明确指定新 `revision`。

## 3. 使用锁定结果

H 场景直接使用返回的锁，不必手动拷贝镜像名：

```bash
agent-infra research open --project-id PROJECT_ID --state-dir /path/to/state \
  --environment-lock LOCK_ID --cpu 1 --memory-gib 2 --operation-id open-validated
```

随后用原有 Job、文件、日志和产物命令进行科研。锁只准备执行环境，不自动确认研究方案、上传数据或开始训练。

D 容器内 Agent 场景使用 `agent: codex` 得到的锁，把结果写入项目的 execution YAML，再按 C 批编译：

```yaml
environment:
  state: specified
  image: sha256:替换为锁中的完整镜像ID
  lock_id: 替换为完整LOCK_ID
tools: {state: none}
evaluation: {state: none}
execution_policy: {state: none}
```

`image` 和 `lock_id` 一起进入冻结 Task。提交时核验项目归属、镜像、最新提案 revision、验证器版本、
有效期和 Codex 层；旧 Task 不会被悄悄切换到新镜像。过期后重新 prepare 验证，再生成新的 execution YAML 并重新编译。
改变依赖提案会使旧锁无法再用于新 Run；已运行的容器仍固定原镜像，不会在线替换。

原有直接 `--image` / 不带锁的 D execution 配置保留兼容，属于手工镜像路径，不享有 E 的完整 smoke 保证。

## 4. Agent 如何参与

原 `agent-infra mcp` 增加六个工具：`environment_plan`、`environment_propose`、`environment_build`、
`environment_plan_status`、`environment_cancel`、`environment_plans`。原 `environment_open` 增加 `environment_lock`。
无需新建 MCP 服务；所有工具仍绑定同一个 Project。

实用流程是用户给出目标和预算，Agent 读取 `project_context` 与规划内容，整理所需包和 import，
确认关键未知项后保存 intent，再提出依赖、启动 build、查看状态。遇到可修复错误时读取日志，
解释修订原因并提交下一版；永久失败或预算耗尽时报告问题，等待用户作出新决策。
已经有人保存 intent 时，Agent 应直接沿用，避免重复建计划。

执行、版本检查和预算限制由代码负责，Agent 负责判断依赖和解释错误。E 不在 Controller 中另外启动隐式模型循环，
外部 Codex/其他 MCP 客户端可按上述工具流程工作。真实验收的客户端、模型和范围见任务记录。

## 5. 持久化、缓存与故障

- `controller/preparation/environments.sqlite3` 保存 intent、提案、每次尝试和锁；原 Projects 数据库不迁移。
  引用包括 `project_id`、提案来源和外部会话；每次 build 对应一个原有 Run/Attempt，Records 中有事件和日志产物。
- 原生 Agent 轨迹仍按 H 的显式导入能力记录，不自动扫描用户全部历史会话。
- 构建缓存键包含固定基础镜像、依赖、模板版本、网络和 Agent 层。缓存只复用镜像，**每次仍在新容器运行 smoke**。
  缓存镜像已被删除时重新构建；改变依赖不复用旧输入结果；已有镜像模板不标为自动构建。
- 先持久预扣一次执行预算，正常完成归还未用时间；异常退出不返还预扣部分。重启先清理自有容器，再标记 interrupted，
  不重复执行、不自动续训；清理不确定时沿用 Controller 隔离机制。新客户端可读取原状态。
- CPU/内存限制针对安装和 smoke 容器；时间用于这些进程和整次尝试检查，Docker 控制调用、镜像发布与清理有额外超时宽限。
  不承诺 Docker daemon 的镜像压缩 CPU/内存或宿主机磁盘硬配额。环境镜像和状态不自动 GC，需定期清理明确不再使用的镜像 ID。

首版限可信本机 Python CPU / wheel 依赖，无 GPU 模板、系统 apt 包、跨节点构建、任意 Dockerfile、自动基础镜像选择或拉取。
已锁定镜像是本机可用结果，不是自动远程备份；记录包版本/哈希不代表删除镜像后一定可从网络逐字节复现。
smoke 证明指定 import、版本和基本 IO/Agent 能力可用，不证明科研方法正确。
