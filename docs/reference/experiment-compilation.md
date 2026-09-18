# 从研究方案生成 Task：C01–C03

状态：Agent Infra 0.1.0，C 批本地实现。前置条件为 Linux、本地文件系统、已完成初始化和规划的项目，以及相同控制状态目录。
运行验收见[任务记录](../changes/20260918-experiment-compilation-c42d8e.md)，维护说明见[代码结构](../implementation/project-workflow-code-guide.md)。

## 1. 使用流程

先通过[研究规划命令](research-planning.md)保存方案，并记录用户采用的精确 revision/digest。
选择方案中的一个稳定 experiment ID，例如 pilot。将代码、数据和配置放在项目内，并在该实验的 inputs 中逐项声明路径与版本。
只有这些选中输入会交给求解 Agent；背景与研究问题、选定实验的方法和输出要求会生成任务说明。

准备项目内的 `configs/experiments/pilot.yaml`，其字段直接复用 Tasks manifest：

```yaml
environment:
  state: specified
  image: python:3.12-slim
tools:
  state: none
evaluation:
  state: none
```

这里明确表示使用所填镜像、无需额外工具、由用户查看科研结果而不运行自动评测。
image 必须填写，但编译阶段不联网检查镜像存在性、安装 Agent 或拉取镜像。
tools 也可以声明 `state: specified` 和现有 Task `items`，工具要求会保留到 Task/view；实际绑定由 D 批运行预检负责。
自动评测的科研任务暂不支持这个编译入口；原生 benchmark 继续使用原有适配器。
execution_policy 可省略；运行超时、预算、凭据和启动许可由后续运行入口负责，不从自由文本停止条件推断。

实验中的 resource_request 指向已有格式的 Resources YAML，例如：

```yaml
version: 1
request_id: pilot
resources:
  cpu: 1
  memory: 1GiB
  gpu:
    count: 0
```

在仓库已配置的环境中执行（已独立安装则省略 `uv run --locked`）：

```bash
uv run --locked agent-infra project compile /path/to/project \
  --experiment pilot --revision 1 \
  --execution configs/experiments/pilot.yaml \
  --state-dir /path/to/state
```

`--revision` 是研究 revision；`--execution` 相对项目目录，与当前 shell 目录无关。
命令仅编译，不启动模型、容器、训练或资源分配。原有已采用版本仍可编译，即使存在尚未采用的新草稿；
一旦用户采用新版，编译入口要求使用新的采用版本。历史 Task 仍可查询使用。

## 2. 返回值与缺项

| 结果 | 退出码 | 含义 |
| --- | --- | --- |
| `status=compiled` | 0 | 材料已复制，真实 Tasks 校验通过，返回 compiled 引用及本机 manifest 路径 |
| `status=needs_input` | 1 | 返回 issues，不登记 Task，例如未确认方案、缺数据或设置未明确 |
| JSON error | 2 | 非法项目/实验、并发材料变化、任务包被改动或不可恢复的 IO/数据库错误 |

`execution_validated=false` 明确表示尚未完成执行预检。编译成功不意味着镜像可用、工具已绑定或 GPU 已分配。
当前会阻止未解决的 Brief unknowns，以及缺少问题、方法、输出、停止条件、资源请求或输入版本的实验。
没有输入也可以是合法实验；但不能把“数据待定”从 unknowns 擦除后假装已有数据。系统检查声明结构与文件，不理解科学真实性。
未选择 metrics 允许人工检查；成功标准、假设等自由研究内容不强制套用固定模板。

## 3. 材料与版本规则

- Task ID 由 Project ID 和 Experiment ID 稳定派生；Task revision 取决于研究版本、选定材料内容和执行配置。
  TaskReference 同时带定义和材料摘要。相同输入重复编译得到同一引用，新的方案或材料产生新 revision。
- 任务包在 `<state-dir>/projects/tasks/<task-id>/<revision>/`，与项目工作区分离。
  inputs 按原项目相对路径出现在 solver workspace；outputs 也相对 solver workspace，不能覆盖输入或保留的 `.agent-infra/`。
  不会自动回写项目 artifacts；产物归档和 Project/Run 关联在 D 批完成。
- 复制文件，不使用硬链接、软链接或指向活动项目的挂载。目录递归复制，因此选择目录意味着其全部内容可见；请缩小输入范围。
  资源和执行配置作为 controller-only 材料保存，求解视图不会投影它们；不会扫描项目中的其他文件。
- 默认复制总量上限 1 GiB，可显式传 `--max-material-bytes N` 调整；文件/目录总条目最多 10,000、嵌套最多 64 层。
  大数据存储适配尚未实现；输入中只列 manifest 时仅复制该 manifest，不会自动下载其中引用的数据。
- 复制中检测普通并发编辑。任务包发布后代码不修改旧内容；本机所有者仍可手改文件，resolve 会检验并拒绝已损坏任务。
  这是可信本机控制目录的完整性检查，不是抵御同 UID 恶意进程的隔离服务。
- 研究确认针对方案本身；编译配置与数据内容单独冻结。镜像 tag 不等于镜像内容 digest，真正执行时仍需解析和验证镜像。

查询与验证历史任务：

```bash
agent-infra project compiled-tasks PROJECT --limit 20 --offset 0 --state-dir STATE
agent-infra project resolve-task TASK_ID --task-revision TASK_REVISION --state-dir STATE
agent-infra task validate /resolved/task.yaml
agent-infra task view /resolved/task.yaml
agent-infra task freeze /resolved/task.yaml
```

research context 额外返回最近 5 个 compiled_tasks；run_references 仍为空，不冒充已执行的 Run。
编译进程在发布后、数据库登记前中断时，保持原方案/材料和执行参数重试即可验证已发布包并补登记。
强制终止可能留下 `.compile-*` 临时目录或未登记包；本版不自动扫描删除，避免误清理。确认无编译进程后可按任务归属手工处理。

## 4. 项目目录移动

先停止对这个工作区的写入，自行移动整个目录，再以 Project UUID 显式重新绑定：

```bash
agent-infra project rebind PROJECT_UUID --directory /new/project/path \
  --expected-revision 1 --state-dir STATE
```

这里 expected-revision 是 Project 元数据版本，与研究 revision 不同。
旧路径必须不存在，新目录的 project.yaml 和身份标记必须与控制库一致；符号链接、复制出的另一份项目或改过身份的目录会拒绝。
成功后 Project revision 加一，Project ID、研究历史与已有 Task 引用不变。重试同一操作不会再次加一。
在数据库更新后中断可通过 `project recover PROJECT_UUID` 完成清单恢复；命令不帮用户移动文件。

## 5. 示例、验收与升级

[小型样例](../../examples/research-compilation/)提供方案、CSV、Python 输入代码、资源和执行设置。
以下命令完成真实 CLI 的保存、确认、编译、Tasks 准备、目录重绑定、方案修订与缺材料检查，不执行样例代码：

```bash
uv run --locked python scripts/acceptance/project_compilation.py \
  --output-dir /tmp/agent-infra-compilation-new
```

输出目录必须不存在，验收结果写入 acceptance.json。该脚本使用明确标注的测试方案，不代替真实研究结论或模型交互验收。
`make verify` 和 `scripts/ci/smoke_wheel.py` 分别覆盖源码检查与独立 wheel 场景。

控制库首次写入从 schema 1/2 事务升级为 3；只读旧库不升级，旧研究 JSON 与摘要不重新解释。
升级前备份状态目录和项目。旧版 A/B 程序拒绝 schema 3，回退需要恢复升级前备份，不能仅降低 user_version。
详见[编译 ADR](../adr/20260918-experiment-compilation.md)。
