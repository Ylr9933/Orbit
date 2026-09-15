# Tasks API 与命令参考

状态：首批实现，schema_version=1。任务解析和准备可以运行；自动模型补全、真实工具注入、原生 benchmark 评分等价与 Environment 隔离闭环尚未完成。

## 1. 当前支持范围

- `TaskDefinition` 保留来源、版本、原始材料与各部分的缺失状态。
- 严格 YAML loader 拒绝重复字段、别名、路径越界、非法 section 和错误资源上下限。
- 材料支持相对路径的 file/directory；尚不解析 registry/远程 URL、自动生成材料或运行任意源码。
- `AgentTaskView` 白名单投影公开材料、输出要求和工具需求，去掉 source、provenance、私有评测与 controller 扩展。
- 快照对定义和材料做 SHA-256；目录摘要包括文件名、内容和空目录。大文件流式读取，但验证需要扫描全部材料。
- 工作区准备只复制 solver 材料，拒绝已有目标目录、链接、目标路径重叠及公开/私有源目录重叠。
- 科研草稿可生成、审查、修订；提案只能填未指定/未知 section，记录来源及证据，不能替换 instruction 或捏造 data。
- 资源申请复用现有资源 YAML，并验证 CPU/内存/GPU 数量上下限；不会创建 lease。
- evaluator 显式注册，保留原生 JSON 结果；执行失败与正常的错误答案分开。自带精确文本比较仅是平台样例。

`read_only` 是传给 Environment 的访问要求，当前复制函数不提供操作系统隔离。准备期间源文件应由可信控制面管理，不允许求解进程并发改写。未声明的私有文件不会被自动识别；目录白名单必须由来源协议和可信导入器确定。

## 2. 命令

前置条件：按贡献指南安装项目，在仓库根目录执行，或将参数换成绝对路径。以下命令已实现。

```bash
uv run --locked agent-infra task validate examples/task-packages/file-result/task.yaml
uv run --locked agent-infra task view examples/task-packages/file-result/task.yaml
uv run --locked agent-infra task freeze examples/task-packages/file-result/task.yaml
```

- `validate` 返回 `ready` 或 `needs_input` 与结构化问题，后者退出码为 1；非法配置退出码为 2。
- `view` 仅返回 solver 视图。原始 instruction 文件按视图路径读取，不会把数据文件全部展开到提示词。
- `freeze` 输出定义及材料摘要快照；不自动覆盖 manifest，不意味着取得资源或已建立隔离。

准备工作区：目标必须不存在，且位于源任务根目录之外。

```bash
uv run --locked agent-infra task prepare examples/task-packages/file-result/task.yaml /tmp/my-task-workspace
```

创建科研草稿：instruction 和可选 data 必须位于同一个受控源根下，output manifest 放在 instruction 所在目录。未指定输出时会生成草稿并返回 `needs_input`，这是预期行为。

```bash
agent-infra task draft /path/to/task/instruction.md \
  --task-id my-research --data /path/to/task/data \
  --output /path/to/task/task.yaml
```

检查现有资源 YAML 是否符合任务约束：

```bash
agent-infra task resource-check /path/to/task/task.yaml /path/to/resources.yaml
```

索引原生 ResearchClawBench runner 已生成的工作区：

```bash
agent-infra task import-researchclaw /path/to/native-workspace \
  --native-id task-id --source-revision native-commit-or-content-version \
  --output /path/to/native-workspace/task.yaml
```

这个入口要求已有 `INSTRUCTIONS.md`，索引存在的 `data/`、`related_work/`。不会调用原生 runner 或 judge，也不会索引目录中的 checklist。输出 `indexed_only`，不声称官方兼容。

原生生成的指令可能包含工作区绝对路径。索引器不会擅自改写它们；若要在另一个容器路径运行，应让原生 builder 按最终路径重新准备并验证等价性，不能假定复制后所有引用仍可用。

## 3. Python 公共入口

从 `agent_infra.tasks` 导入 `load_task`、`validate_task`、`freeze_task`、`build_agent_view`、`materialize_agent_view`、`create_research_draft`、`apply_research_proposal`、`review_draft`、`write_manifest`、`validate_resource_plan`、`build_evaluation_plan` 和 `verify_evaluation_inputs`。

`TaskSection` 用 `FieldState` 与不可变的 `value_json` 保存内容；`task_document()` 可以序列化完整 controller 定义，不能交给求解 Agent。AgentTaskView 的 outputs 也使用 TaskSection，消费者应解析 `value_json`，不要把它作为 Markdown 提示词直接拼接。

草稿修订示例（调用方可由任意 Agent 产生结构化建议）：

```python
from agent_infra.tasks import apply_research_proposal

updated = apply_research_proposal(
    draft,
    {"outputs": {"state": "specified", "items": [
        {"path": "report.md", "required": True},
    ]}},
    revision="draft-2",
    explanation="建议将报告放在 report.md",
    evidence_ids=("instruction",),
)
```

此方法不调用模型，也不把建议标成用户确认。`origin="user"` 只能由调用方真实的用户输入流程使用。模型如何收集用户回答、调用这些入口并持续推进，属于尚未完成的编写工作流。

`agent_infra.tasks.importers` 提供 `import_native_workspace` 通用显式白名单入口、`import_researchclaw_workspace` 和 `import_asibench_workspace`。ASI 入口要求选定 b1–b4、对应 `prompt_bN.md` 和已由原生流程生成的 input_paths；不扫描整个任务目录，也不重写 generator、评分或预算。

`agent_infra.tasks.evaluation.EvaluatorRegistry` 接收程序组装层明确提供的 evaluator 映射；manifest 不能指定 Python 模块让 loader 自动执行。`build_evaluation_plan` 绑定当前任务摘要及提交摘要；`verify_evaluation_inputs` 检测变化。摘要检测不能替代不可变提交存储或运行时权限隔离。

## 4. schema 的具体限制

六个 section 支持 `unspecified`、`none`、`unknown`、`specified`。非 specified 状态不能夹带默认值。未知顶层字段被拒绝；benchmark 特殊元数据应放 `extensions`，并保留 source revision/native_id。

| section | specified 时支持的字段 |
| --- | --- |
| tools | 非空 items；每项 tool_id、version、required、transport（mcp/cli/function）、scope，可选 provenance |
| resource_intent | constraints：cpu_min/max、memory_min/max（显式单位）、gpu_min/max；可选 provenance |
| environment | image 或 native_ref，可选 provenance；当前只是声明 |
| outputs | 非空 items；每项 path、required，可选 provenance；只放公开交付约定 |
| evaluation | evaluator_ref、audiences=[evaluator, controller]、feedback=none/after_submission/native |
| execution_policy | native_ref，可选 provenance；实际预算执行待 Run 接入 |

尚不支持的原生字段不能塞进已知 section 然后静默忽略。保留在 extensions/native_ref 后，由原生 adapter 解释；没有相应 runtime 时不能据此声称可运行。

样例见 [file-result](../../examples/task-packages/file-result/task.yaml) 和 [nested-research](../../examples/task-packages/nested-research/task.yaml)。它们是小型平台测试数据，不是官方 benchmark。

## 5. 剩余工作

1. 编写工作流接入真实 Agent，使自然语言补全、澄清和资源建议自动执行。
2. Environment/Agent 增加 ToolBinding 和真实 MCP/CLI 工具注入，验证工具调用与拒绝越权。
3. 为固定版本的 ASI-Bench、ResearchClawBench 连接原生 loader、生成器、评测和聚合入口，验证相同提交的评分等价。
4. Run/Records 持久化 revision、计划、提交与反馈预算；Environment 实现真正的可见性隔离和生命周期。

完整目标见 [Tasks 建模设计](../architecture/task-model.md)。以上剩余项属于原设计，不能把当前基础能力视为整个设计已经完成。
