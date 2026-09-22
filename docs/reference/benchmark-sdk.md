# Benchmark SDK 与离线规划命令

状态：BM00 已在本任务分支实现，SDK **1.0**，JSON schema **1**，Python 3.12。
是否已集成以 Git 为准。只有规划与检查，**没有 benchmark run、调度、评分或循环优化入口**。

## 安装和启用

SDK 随 `agent-infra` 核心 wheel 提供；适配器是独立发行包，依赖公共 SDK。
安装包不等于启用，不自动 import 所有已安装插件。采用 Python entry points：

```toml
# 适配包自己的 pyproject.toml
[project.entry-points."agent_infra.benchmarks.v1"]
my-bench = "my_bench_adapter:Adapter"
```

管理员传入独立 TOML 配置，不改变现有研究工作流的 `--config` 语义：

```toml
schema_version = 1

[[adapters]]
alias = "my-bench"
distribution = "my-bench-adapter"
version = "0.1.0"
entry_point = "my-bench"
sdk_version = "1.0"
```

未提供 `--config` 时无适配器启用。分发包名按 Python 规则规范化；版本必须与安装元数据一致。
重复分发包、重复 entry point、未知 alias、SDK/config 版本不匹配均拒绝。先检查元数据，再加载工厂，
再检查工厂返回的 SDK descriptor 和 discover/plan/validate 接口。没有从 Task/manifest 导入任意模块的入口。

**适配包是受信任 Python 代码**，拥有当前用户权限。显式启用不是沙箱，也不能阻止恶意包在 import 时
执行操作。只安装审核过的 wheel，并在部署锁文件中固定 wheel/hash；同版本的可编辑安装不构成可复现证明。
SDK 1.0 当前要求精确匹配；不承诺任意未来 minor 自动兼容。未来执行/结果接口通过单独扩展引入，
不要求规划包实现假的 submit/score。

## 已实现命令

```sh
agent-infra benchmark adapters --config adapters.toml
agent-infra benchmark inspect my-bench --source /path/to/manifest-snapshot --config adapters.toml
agent-infra benchmark plan my-bench \
  --source /path/to/manifest-snapshot --request request.json \
  --output /path/to/new-plan.json --config adapters.toml
agent-infra benchmark check /path/to/new-plan.json --config adapters.toml
agent-infra benchmark check /path/to/new-plan.json \
  --config adapters.toml --capabilities capabilities.json
```

- `adapters`：只读安装元数据，列出配置和已安装 entry point，不执行适配器代码。
- `inspect`：调用适配器发现目录，输出可公开的单位 ID/形态/episode 数，不输出私有材料位置和完整配置。
- `plan`：验证请求与 catalog 一致，检查适配器规则，冻结源目录、runner、参数、候选和 adapter 身份。
  文件权限 0600；输出必须位于输入快照外，且不可覆盖已有文件。返回 `planning_valid` 与 digest。
- `check`：校验文件摘要、精确包版本、源目录/catalog 和重新生成的计划；比较能力及精确版本组合。
  它调用可信适配器，不启动原生 runner，不探测/分配实际 GPU，不连接官方提交服务。

退出码：`0` 命令或声明检查成功；`1` 检查报告存在不兼容；`2` 配置、包、源文件或契约错误。
`plan` 成功不代表可执行；所有规划/检查结果均标明 `runtime_ready: false`。
没有能力文件时，backend、Agent 和组合默认未知，`check` 返回非零；不能用“已装 CLI”推断兼容。

计划是**管理员材料**，可能包含私有引用，不能直接作为 solver/optimizer 的输入。
基于角色/阶段的实际挂载与反馈过滤要在 BM01 后端和后续 adapter 中执行，BM00 只校验/保存声明。

## 公共对象和文件格式

从 `agent_infra.benchmarks.api` 导入；对象不可变、禁止未知字段，数值拒绝布尔冒充、字符串和非有限值。
JSON 用 `Type.model_validate_json(...)` 读取、`model_dump_json()` 写出；Python 构造时序列使用 tuple。
`Type.model_json_schema()` 可导出准确 schema，避免手工维护另一份字段清单。

| 契约 | 语义 |
| --- | --- |
| `SuiteRef / PinnedSource` | source、runner、可选 dataset 的 revision/digest；不能用 main/latest 作为固定版本。synthetic 明示样例 |
| `WorkUnit / Catalog` | single、sequence、paired_sequence、native_job；保留有序 episode 与条件，不展平 family |
| `PlanRequest / CandidateRef` | 精确选取的单位和次序、候选 Agent/模型/config 摘要；target model 与 judge 独立 |
| `ExecutionPlan / Phase` | 每个 WorkUnit 的阶段模板、拓扑次序、原生或平台执行权、backend、能力要求及配置引用 |
| `ResourceRequirements / Budget` | 部分原生资源需求与预算起算点，缺省为 unspecified/None；不是已有 `ResourceRequest` 的替代分配器 |
| `StatePolicy` | 对话、workspace、记忆、checkpoint、session 与 scope 分开；原生策略可另给固定引用 |
| `Material / FeedbackRule` | 阶段材料的角色读权限；允许的反馈字段、接收者、释放时机与查询次数 |
| `RetryPolicy` | 原生/平台/禁止/未规定的重试所有权和次数；不悄悄重置原生预算 |
| `BenchmarkOutcome / Metric` | execution、evaluation、protocol、cleanup、capture、submission 独立；指标方向/单位/范围和现有 Records artifact ID |

反馈字段是**明确字段名**，不是隐式全日志权限；没有规则表示没有授权。缺少资源字段不擅自补 CPU/GPU，
后续 Run 须把已确定数值转成现有资源请求；外部调度使用其分配权，不在本机重复占卡。
Outcomes 当前只定义 schema，不产生分数、不接管 Records 存储或官方聚合。

`CapabilityProfile` 包含 backend/features、可用 Agent，以及精确的 `CompatibilityClaim`：
adapter ID/version × suite/runner digest × profile × Agent/version/model × backend。
只在这组声明和阶段必需能力都存在时返回 `compatible: true`。文件是离线声明，不能拿合成样例的
profile 当实际环境验收证明；资源 enforcement、工具、memory、恢复和轨迹仍需逐版本实测。

BM00 对 `--source` 做递归内容摘要并拒绝符号链接，适合**小型不可变 manifest 快照**。
不要把整个大数据/权重目录或实时工作目录直接作为输入；大数据用固定外部引用表示。
当前只核验本地快照和适配器输出，远端数据/镜像/runner 摘要真实性必须由后续适配器预检验证，
不因字段叫 digest 就当作下载验证过。摘要用于发现修改，不是签名；移动目录、改变包或配置需重新规划。

## 代码入口与验证范围

- [api.py](../../src/agent_infra/benchmarks/api.py)：公共契约；[testing.py](../../src/agent_infra/benchmarks/testing.py)：公开 conformance helper。
- [registry.py](../../src/agent_infra/benchmarks/registry.py)：元数据、启用与身份校验。
- [planning.py](../../src/agent_infra/benchmarks/planning.py)：内容快照、冻结、校验。
- [bootstrap](../../src/agent_infra/bootstrap/benchmarks.py) 与 [CLI](../../src/agent_infra/gateways/cli/benchmarks.py)：组装/参数解析。

独立包验收：`uv build` 后运行 `uv run --locked python scripts/ci/smoke_benchmark_adapter.py`。
脚本创建临时 venv、安装核心/适配器两个 wheel，在源码树外完成四组 inspect/plan/check 和包内测试，
随后清理本次临时目录。不改变共享 venv 的适配包，不调用真实模型或容器。
该检查也由既有 `scripts/ci/smoke_wheel.py` 调用。完整范围见[任务记录](../changes/20260922-benchmark-sdk-bm00-c7e2a1.md)。
