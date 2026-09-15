# Tasks 建模：任务材料、可见性与原生 benchmark 转换

状态：设计已开始落地。任务契约、相对路径 manifest、可见视图、草稿修订、资源校验、工作区索引导入和评测准备已实现；自动编写工作流、工具注入、原生评分等价和真实隔离仍待完成。具体支持字段与命令见 [Tasks API 参考](../reference/tasks.md)。下文保留完整目标，示意格式不等于全部已实现。

## 1. 核心结论

用户提出的工具、资源、任务说明、数据、用户提示和评测六部分，已经覆盖任务的主体。建议围绕它们建立一个**保留原始材料、可生成不同读取视图的任务描述**，补充任务身份与版本、来源证据、执行约束和输出约定。

meta-file 是这套描述的正式入口：记录材料是什么、来自哪里、如何使用、谁能看。它不要求每个任务都搬进固定目录，也不要求每个任务都有数据、额外工具或自动评测。

明确区分三个对象：

| 对象 | 表达什么 | 是否包含隐藏信息 |
| --- | --- | --- |
| `TaskDefinition` | 固定版本的完整任务定义与原始材料索引 | 可以，仅可信控制面读取 |
| `AgentTaskView` | 本次运行允许求解 Agent 读取的任务视图 | 不包含隐藏材料、地址及由其推导出的提示 |
| `TaskExecutionPlan` | 本次运行采用的资源请求、环境、工具绑定和输出收集安排 | 按接收模块拆分，不能整体透传给 Agent |

同一份 TaskDefinition 可以被多个 Agent、多次 Attempt 使用。一次运行选了 3 CPU、Codex 或某个节点，属于运行计划，不必改写任务本身。

## 2. 任务包含哪些部分

| 部分 | 内容 | 没有时如何表达 |
| --- | --- | --- |
| identity / source | task ID、任务版本、原生 benchmark ID、原始版本或内容摘要、转换器版本 | 本地科研任务由平台生成身份，标明本地来源 |
| instructions | 原始 Markdown、文件夹或原生提示生成器的输出引用 | 科研任务可由用户要求起草；benchmark 缺关键指令则报告缺失 |
| materials | 数据、参考论文、related work、代码模板及其他材料的统一索引 | 合法无材料可为空；缺失必需文件要报错 |
| user_context | 用户附加要求、背景和澄清记录，保持与原生说明分离 | 未提供时为空 |
| tools | 必需或可选工具能力、版本、使用范围和接入方式 | 区分未指定、明确无额外工具、禁止某工具 |
| resource_intent | 原文资源约束、硬性上下限、建议、未决项 | 未指定时保留未指定，执行计划可以另外提出资源建议 |
| environment | 现成镜像、原生构建流程、依赖、网络和可写目录要求 | 记录未指定；科研模式可形成独立环境建议 |
| outputs | 要交付什么、路径/格式，以及哪些是必需项 | 无结构化定义时保留原文约定，不能发明 benchmark 交付项 |
| evaluation | 原生 evaluator 引用、私有材料、输入映射、评分/汇总及反馈策略 | 可为无自动评测、人工评阅、未提供或外部服务不可用 |
| execution_policy | 时间/费用/次数预算、交互、重试、提交和停止规则 | 源协议未指定就保持未指定；平台上限单独记录 |

**字段可选不等于忽略差异。** `unspecified` 表示来源没有说，`none` 表示明确没有，`unknown` 表示暂时无法确认，`specified` 表示有已知要求。不要用 `[]` 同时代表“没有限制”和“禁止所有工具”。

核心结构尽量小；例如 related work 是 `materials` 中的一种 role，不需要为每一个 benchmark 的特殊文件新增顶层字段。无法归入公共字段的原生元数据放入带命名空间的 `extensions`，原文仍是权威来源。

## 3. meta-file 如何设计

建议使用 `task.yaml`，作为平台内部完整任务索引。文件格式名称与 schema 版本独立于任务版本。每个 material 至少描述：

| 字段 | 解释 |
| --- | --- |
| `id` | 任务内稳定标识，其他字段按 ID 引用 |
| `role` | instruction、data、reference、starter_code、evaluation_asset 或扩展角色 |
| `kind` / `media_type` | file、directory、生成材料或服务引用；文件可附 MIME 类型 |
| `source` | 原始位置：相对路径或受控存储引用，不是任意可执行命令 |
| `description` | 材料的作用；生成给求解 Agent 的描述只能依据公开内容 |
| `audiences` | solver、evaluator、controller 中哪些主体允许访问 |
| `target` / `access` | 投影到工作区的相对路径及 read_only / writable_copy |
| `availability` | 存在、缺失、按原生流程生成或需用户提供 |
| `provenance` | 原生声明、用户输入、转换器提取或 Agent 建议，以及证据引用 |
| `digest` | 文件内容摘要或目录清单摘要，用于冻结与验证 |

路径和说明本身也可能泄漏答案，因此完整 meta-file 不直接交给求解 Agent。平台生成一个仅含允许条目的 `task-view.json`，并把 source 地址改为 Agent 实际能访问的工作区路径。完整索引中一个隐藏文件的文件名、数量、描述都不必出现在这个视图中。

目录条目不能默认意味着“整个源目录都允许访问”。导入时要展开或固定具体清单，检查子目录中的隐藏材料、符号链接和路径越界；目标路径冲突也应拒绝。远程资源通过受控 resolver 获取，记录最终版本/摘要，不能把下载凭据放进 manifest。

### 一个简化示例

以下是**提案格式示意，不是当前 loader 能读取的配置**，也不是官方 benchmark schema。`source` 中的 `registry:` 由未来受控 resolver 解析。

```yaml
schema_version: 1
task_id: research-example
revision: draft-1
mode: research
source:
  kind: user
instructions: [instruction]
materials:
  - id: instruction
    role: instruction
    kind: file
    media_type: text/markdown
    source: ./instruction.md
    description: 用户提供的研究目标与交付要求
    audiences: [solver, evaluator, controller]
    target: instruction.md
    access: read_only
    availability: present
    provenance: {origin: user}
  - id: data
    role: data
    kind: directory
    source: ./data
    description: 用户提供的实验数据
    audiences: [solver, evaluator, controller]
    target: data
    access: read_only
    availability: present
    provenance: {origin: user}
  - id: references
    role: reference
    kind: directory
    source: ./related_work
    description: 用户允许阅读的参考资料
    audiences: [solver, evaluator, controller]
    target: related_work
    access: read_only
    availability: present
    provenance: {origin: user}
user_context: []
tools: {state: unspecified}
resource_intent: {state: unspecified}
environment: {state: unspecified}
outputs:
  state: specified
  items:
    - path: report/report.md
      required: true
      provenance: {origin: user, evidence: instruction}
evaluation:
  state: specified
  evaluator_ref: registry:evaluators/research-example-v1
  audiences: [evaluator, controller]
  feedback: after_submission
execution_policy: {state: unspecified}
extensions: {}
```

此例省略尚未冻结的 digest；任务从 draft 进入 ready 前，需要生成摘要或等价的不可变版本引用。文件夹和数据仍在原位置，manifest 引用它们；真正运行时由 Environment 物化本次工作区。

## 4. 工具怎么进入 Codex、Claude Code 和自研 Agent

Tasks 声明“需要什么能力”，例如一个只能查询本任务数据的数据库工具，而不是直接写 Codex 配置文件。建议工具项包含 `tool_id`、版本、必需/可选、参数 schema 引用、授权范围和原生协议依据。工具实现归 Environment，协议入口归 gateways，provider 配置翻译归 Agent adapter。

```mermaid
flowchart LR
    Task[Task 工具需求] --> Run[Run 核对策略与能力]
    Run --> Env[Environment 启动工具或连接服务]
    Env --> Binding[本次 Attempt 的 ToolBinding]
    Binding --> Adapter[Agent adapter 生成私有配置]
    Adapter --> Agent[Codex / Claude Code / 自研 Agent]
    Agent --> Gateway[受权限限制的工具入口]
    Gateway --> Env
```

建议首批接入分三类：

1. **MCP 工具**：Environment 或 MCP gateway 提供端点，adapter 将本次绑定写入 provider 支持的私有配置并加载。具体 CLI 参数在实现时对固定版本验证。
2. **CLI/本地库工具**：由 Environment 在任务环境安装原生指定版本，提供使用说明和访问路径；这不自动等同于 provider 的结构化工具调用。
3. **自研函数工具**：自研 Agent 通过自己的执行端口注册相同能力；接口不要求所有 Agent 都转换成 MCP。

`ToolBinding` 只表达连接方式、允许工具及权限引用；实际秘密由 Environment 注入。容器内的 stdio 工具要确实存在于该容器；远端工具地址必须从 Agent 所在位置可达，宿主机的 localhost 不能直接当作另一个容器的 localhost。

注入后必须实际检查工具发现与允许/禁止调用。必需工具不受 provider 支持时，运行应前置失败；可选工具缺失只有协议允许时才能继续。不能用一句“你可以调用 X”代替真实工具注册。

**现有代码需要扩展：** `AgentRunRequest` 尚无工具绑定字段；Codex 容器计划忽略用户配置，Claude Code 使用 safe mode 和严格 MCP 配置。不能直接复用用户全局配置来接入任务工具，也不能假定这些参数允许新配置生效。后续需增加公共 ToolBinding、provider 能力声明和固定版本集成测试，保留任务隔离。

## 5. 资源：任务要求与实际申请分开

`resource_intent` 保存源任务的事实；本次 `ResourceRequest` 保存打算申请的数值。Resources 继续使用现有 version 1 YAML，不另造分配格式。

| 情况 | 处理 |
| --- | --- |
| 明确写了 CPU/内存/GPU 数值及上下限 | 确定性提取或由 Agent 提取并附原文证据；校验单位及“至少/至多/恰好”的含义 |
| 只说“需要 GPU”“显存较大”等 | 保存定性要求，资源规划 Agent 建议具体值，标明尚待核实 |
| 没有说明 | 保持 `unspecified`；根据公开任务和数据规模提出运行建议 |
| 与平台容量、预算或协议冲突 | 返回冲突；不能偷偷减少硬性资源要求或增加 benchmark 预算 |

例如用户明确允许 2–4 CPU，Agent 建议 2 CPU，用户改成 3 CPU，只改变运行计划；如果原协议规定“恰好 2 CPU”，改成 3 CPU 就改变了实验条件，需要作为独立实验配置记录。

资源规划先使用公开说明、数据元信息和可用资源池。需要试运行估算时，由 Run 安排独立、有上限的准备环境；不能先申请未知的大环境再解决资源估计。正式提交前，计划校验器将建议生成的 YAML 交给现有 `load_resource_request()`，再验证其满足任务约束和平台预算。

资源不足仍使用已有 `waiting` / `unsatisfiable` 语义。资源建议不是成功分配，也不保证任务能在该资源下完成。benchmark 原文没有资源字段时，不能把平台选出的 3 CPU 回填为“benchmark 要求 3 CPU”。

## 6. 输入、用户提示和输出如何组织

任务说明保留原文引用。结构化 inputs/outputs 用于导航与运行检查，可以由 Agent 提取，但必须带来源证据；不确定的格式保留自然语言，不能编出评测要求。

任务提供的数据属于原始输入，不允许 Agent 捏造缺失数据。确实无数据的理论任务可以没有 data；缺失必需数据的任务只能请求用户补齐、调用原生数据生成器或按协议取得指定数据。原生生成器产生输入时需固定版本、参数和 seed，且把参考答案留在私有侧。

用户额外提示独立保存在 `user_context`。科研模式下可以据此形成新 revision；benchmark 模式下若提示改变目标、提供额外方法提示或违反无人干预规则，应拒绝正式模式，或明确标为修改条件的实验。不能将新增提示伪装成原始 benchmark instruction。

公开输出约定与隐藏判分细则分开。Agent 应知道必须提交什么，但不因此得到参考答案、隐藏测试或私有权重。是否要求固定输出文件、允许修改输入副本，都沿用原生协议；平台不能为了统一目录而破坏相对路径或写入行为。

## 7. eval 的隔离与原生可见性

默认不给求解 Agent 暴露私有 evaluator、参考答案、隐藏测试及其访问地址。科研任务若需要由 Agent 辅助编写私有评测，应由独立评测编写会话完成；看过隐藏答案的会话不能随后充当该任务的求解 Agent。

对于 benchmark，必须进一步区分：**公开评分规则/公开自检**与**隐藏评测材料/私有服务**。源协议允许公开的评分说明可以保留可见；隐藏部分保持隐藏。无评测器时不能自动创造一个评分并称为 benchmark 原生分数。

隔离需要落实到运行环境：

- Agent 可见视图和工具目录均不能携带私有引用。
- 私有文件不进入求解容器挂载、镜像层、环境变量或工具可访问存储范围。
- 评测在独立上下文中读冻结的提交产物，Agent 不能边评分边修改提交。
- evaluator 日志只给可信控制面；评分反馈按源协议决定何时、以什么粒度返回。
- 求解 Agent 的错误信息、检索服务、web 下载等也要遵守协议访问范围。

日常科研中若 Agent 与私有评测文件使用同一宿主机用户，单靠 workspace 约定无法形成强隔离。需要独立 OS 权限或容器/服务边界；未建立时应明确标为协作模式，不宣称隐藏评测隔离成立。

评测结果分别保存执行状态、原生分数、原生明细和聚合结果。评测运行失败不能当成零分；多次采样、重复运行、预算及聚合规则由 benchmark adapter 保留。公开反馈也不能被平台默认拿来无限次优化再提交。

## 8. 场景一：把科研要求补全成任务

任务编写 Agent 与求解 Agent 是两个角色。编写 Agent 可以调用平台的任务草稿接口；Tasks 的确定性 loader 不依赖模型或某个 provider。

建议流程：

1. 接收用户原始要求和真实附件，保留原文。
2. 枚举材料并产生草稿 meta-file，提取目标、输入、输出、工具和资源事实。
3. 对未指定内容生成建议，附 `agent_proposed` 来源，绝不改写用户已给定的事实。
4. 只询问阻止正确执行的问题，例如数据在哪里、预测目标是哪一列、可用费用上限。可逆的文件组织选择可以自动完成。
5. 校验路径、材料可见性、必需字段和约束冲突；把问题列表返回用户或编写 Agent。
6. 在用户已授权范围内冻结 ready revision，生成 AgentTaskView，交给 Run 制定执行计划。

草稿状态建议为 `draft → needs_input → ready`，修订产生新 revision。`ready` 表示任务描述足够进入运行准备，不表示资源已获批、环境已启动或模型已登录。科研任务可以没有自动 eval，只要如实标明人工验收方式。

例：用户说“分析这份实验数据，比较两种模型并写报告”。系统可以自动索引已提供的数据，建议输出目录、CPU 和内存；如果没有两种模型的名称或比较目标，必须明确询问或提供可审核建议，不能默认为某个科学问题。没有隐藏评测时保持未提供。

## 9. 场景二：anybench2ourtask

这个目标应理解为“用统一索引和一组原生 adapter 表达不同 benchmark”。任意目录可以先索引；能够正式运行、评分、比较，需要适配原生执行与评测协议。一个通用 LLM 扫目录不能自动证明这些协议等价。

转换过程：

1. 固定原始源码、任务版本、材料清单及运行变体。
2. 优先调用原生 loader / workspace builder，识别真正给求解 Agent 的内容。
3. Agent 可辅助生成 meta-file 草稿，但隐藏材料只能交给可信导入上下文；求解会话不能继承导入时的上下文。
4. 为提取字段记录 source、source revision、证据位置和转换器版本；无法映射的字段原样保留或返回 unsupported。
5. 生成 AgentTaskView，并对照原生视图检查：指令、数据、相对路径、工具、输出、预算与反馈均一致。
6. evaluator adapter 调用原生评测与聚合逻辑，保存原生结果和必要的统一索引，不改评分算法。
7. 对同一份固定提交分别跑原生入口和 adapter，比较结果；未验证前只能标为导入草稿，不能声称官方兼容。

缺失的源字段保持未指定。平台运行必须选择的镜像或资源放在 ExecutionPlan，并标明平台来源。原生运行条件冲突或无法保留时，停止正式兼容声明；研究性变体单独标识。

## 10. ResearchClawBench 的具体映射

本节依据本机 ResearchClawBench checkout `b76fdeca0164148d5be5283665ba31a67f021061` 的 `evaluation/run_task.py` 和 README；只检查了源码，没有执行任务或评分。

`TaskRunner.setup_workspace()` 的实际流程是复制存在的 `data/` 和 `related_work/`，创建 `code/`、`outputs/`、`report/`、`report/images/`，再调用 `_build_instructions()`，根据 `task_info` 和原生模板生成 `INSTRUCTIONS.md`。因此不能假定每个源任务都有一份静态 `instruction.md`。

| 原生内容 | 我们的映射 | 注意事项 |
| --- | --- | --- |
| task ID、task_info 中的 task | 原生身份与 instructions 来源 | 保留任务文本；调用原生模板生成最终指令 |
| `data/` | role=data 的 directory material | 保留原生路径与内容；没有则不创造 |
| `related_work/` | role=reference 的 directory material | 仅存在时登记，其他 benchmark 不必有此条目 |
| 原生生成的 `INSTRUCTIONS.md` | generated instruction material | 来源记录模板版本、输入与最终内容摘要 |
| `code/`、`outputs/`、`report/` | 原生工作区与产物路径约定 | 工作目录存在不等同于每个文件都是强制提交项 |
| `report/report.md` | 原生要求的报告交付路径 | 由原生评测流程使用报告与图片 |
| checklist、目标论文及 judge 配置 | evaluator/controller 侧材料与评测器引用 | 不因自动索引而加入求解视图 |

Agent 生成的 meta-file 应当解释“related_work 是可见参考资料”，不能从隐藏 checklist 生成“这些论文中的某个结论是得分关键”再传给求解 Agent。related_work 中的公开论文与 evaluator 的目标论文必须按原生暴露规则区分，不能仅凭 PDF 文件类型分类。

对于该 checkout，转换器还需对原生 prompt 模板、真实任务样例、评分参数和聚合入口进一步做兼容测试。本次建模不声称已完成 ResearchClawBench adapter。

## 11. ASI-Bench 的映射差异

依据本机 ASI-Bench checkout `38ab4b5364f1fde5515fef7e9210ff3c9db6a2ba` 的 `ai4sci_bench/core/task.py`、`tasks/_template/task_meta.yaml` 和 `docs/guide/authoring-a-task.md`：

- 原生 loader 支持 legacy `task.yaml`，以及 `task_meta.yaml` + 可选 `task_eval.yaml`；两种布局并存时原生优先 legacy，adapter 应复用这一行为。
- 一次运行选定 B1/B2/B3/B4 提示等级。任务目录包含其他等级文件，不表示全部允许加入该次求解视图；B3 不能顺便得到 B1 的提示。
- 输入可由原生 generator 根据参数和 seed 生成；生成器与参考答案不能一起挂给求解 Agent。
- 原生说明区分发布的 scoring-only 配置/评分实现与私有生成设置、答案及 reference specs。loader 合并后的完整对象不能直接作为 AgentTaskView。
- 已有 Docker 或依赖构建流程应通过 Environment 调用原生适配方案，不能用统一基础镜像覆盖任务真实依赖。

这一差异说明，`audiences` 应表达具体运行变体下的权限；“公开仓库文件”不能直接等于“本次求解 Agent 可见文件”。

## 12. 模块边界和待实现接口

以下接口名称是提案，先通过最小样例验证后定稿：

| 所属模块 | 接口/对象 | 责任 |
| --- | --- | --- |
| Tasks | `load_task(ref) -> TaskDefinition` | 确定性解析、验证来源和版本 |
| Tasks | `validate_task(draft) -> issues` | 返回缺项、冲突、可见性和证据问题；不自动编造字段 |
| Tasks | `build_agent_view(task, variant) -> AgentTaskView` | 仅返回协议允许的说明与材料 |
| Tasks | `build_evaluation_plan(task, submission) -> EvaluationPlan` | 绑定私有评测和冻结提交；保留原生语义 |
| Tasks | benchmark adapter 的结果解释与聚合接口 | 统一索引原生结果，原生规则在 adapter 内 |
| Run / 编写工作流 | 草稿补全与资源规划 | 调用编写 Agent，处理澄清，形成有来源的运行建议 |
| Resources | 已有 `ResourceRequest` / `try_allocate` | 对具体申请执行准入；不理解科学任务难度 |
| Environment | 工作区物化、工具连接、执行、隔离 | 仅挂载允许的文件并落实资源与工具权限 |
| Agent | 待扩展 ToolBinding 接口 | 将已批准绑定翻译成 provider 私有配置 |
| Records | revision、来源、计划、提交与评测记录 | 支持追溯与复现，不把隐藏内容返回求解端 |

建议 Tasks 内先分 `api.py`、manifest 解析/校验、可见视图和 `benchmarks/` 原生适配器。工具服务器、Docker client 和模型调用不塞进 Tasks loader；不用先拆更多服务。

## 13. 建议落地顺序与验收

1. **任务契约和两种小样例**：实现 manifest、来源、缺失状态、目录清单和可见视图。覆盖有/无数据、有/无评测、特殊 reference 材料；验证隐藏路径和描述不出现在视图。
2. **科研草稿流程**：Agent 起草、用户澄清、确定性验证、冻结 revision。验收必需数据不会被捏造，建议不会冒充用户约束，协议冲突能够阻止运行。
3. **工具和资源连接**：复用现有 resource YAML，加公共 ToolBinding 和 provider 集成；真实验证 Codex/Claude 的工具发现与越权拒绝，不能只验证配置文件存在。
4. **一个 benchmark adapter**：先挑一个固定版本与样例，比较原生和平台的可见工作区、参数与同一提交的评分；再按相同契约接入第二种目录结构。
5. **真实隔离和闭环**：连接 Environment、Run、Records，验证隐藏评测不可读、提交冻结、失败状态、原生预算和反馈次数，以及清理后资源释放。

实现按以上顺序推进，具体已完成范围见 [Tasks API 参考](../reference/tasks.md)。现有模块边界见 [Agent / Environment 模块设计](agent-environment-modules.md)，资源分配语义见 [资源管理设计](resource-management.md)。
