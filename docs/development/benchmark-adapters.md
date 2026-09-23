# 新 benchmark 适配包开发指南

状态：SDK 1.0、BM00 规划与 BM01 受管执行扩展 1.0 已实现；结果解释扩展尚未实现。
把本文件、[SDK 参考](../reference/benchmark-sdk.md)、benchmark 固定仓库版本交给开发者或 Agent，
即可开始独立包开发。原生规则不清楚时先调查并记录，不能为了填 schema 自行发明 benchmark 规则。

## 最小包与接口

复制 [examples/benchmark-adapter](../../examples/benchmark-adapter/) 到新的独立目录/仓库，
修改分发包名、模块名、entry point 和 AdapterDescriptor。四个正式参考包也遵守这套方式，不放进核心模块。

```text
my-bench-adapter/
  pyproject.toml           # 独立构建、核心 SDK 版本依赖、entry point
  src/my_bench_adapter/    # 原生目录解析与协议映射
  fixtures/               # 小型、可公开、固定的验收输入
  tests/                  # 包自己的 conformance / 原生对照测试
  adapters.toml           # 示例显式启用配置
  README.md               # 来源、支持范围、安装、限制和验收证据
```

工厂是无需参数的可调用对象，返回具有以下接口的 adapter：

```python
from pathlib import Path
from agent_infra.benchmarks.api import (
    AdapterDescriptor, Catalog, ExecutionPlan, Issue, PlanRequest,
)

class Adapter:
    descriptor = AdapterDescriptor(adapter_id="my-bench", description="Native protocol mapping")

    def discover(self, source: Path) -> Catalog:
        ...  # 读取小型本地 manifest / 索引；返回固定版本与完整原子单位

    def plan(self, catalog: Catalog, request: PlanRequest) -> ExecutionPlan:
        ...  # 固定的原生参数与每单位阶段；保持 selection/candidate/episode/state 不变

    def validate(self, plan: ExecutionPlan) -> tuple[Issue, ...]:
        ...  # 原生选项、预算、反馈与结果使用的协议限制
```

上面是接口示意，能安装运行的模板以示例包为准。规划仅依赖公开 `api` 与 `testing`，不导入 Run、
Docker、数据库、核心 registry 私有实现；需要新能力时声明 required_capabilities，当前 backend 不具备则预检失败。
不要在 discover/plan/validate 中安装、下载、启动任务、调用模型或上传成绩，它们须确定性且不修改输入。

## 逐步接入

1. **固定证据**：锁定 upstream commit、数据/runner/image 版本；列出原生入口、Agent 要求、评分/聚合、许可与提交方式。
2. **确定运行单位**：独立 case 或完整 family/配对序列；内部调度由原生 runner 管时，用 native owner，不另建一套 episode 调度。
3. **映射协议**：保留公开材料/私有 grader/允许自评、session 与各种持久状态、时间起算点和失败处理。
   不改变原任务内容，不为不存在的资源或 split 强制补值；多个原生配置使用不同 profile。
4. **实现规划**：定义小型 manifest 快照，生成 source/runner/data 固定引用；拒绝未知原生参数。
   非敏感原生配置通过参数或固定引用表达，凭据另行注入，不能放进 manifest 或 plan。
5. **测试独立包**：包内使用 `assert_planning_conformance(adapter, source, request)` 检查确定性与保真；
   补正常/失败 fixture，验证不可见材料没有进入公开视图、状态没有串分支、缺字段没有变成猜测值。
6. **构建/安装/启用**：核心 SDK wheel 与适配包 wheel 安装到同一专用环境，用 TOML 显式启用，执行 inspect/plan/check。
   可以先让 check 报告缺失执行能力，不能把缺失项删掉来得到通过。
7. **执行验收**：声明并连接受支持的通用 backend；再测取消、失联、清理、资源限额、轨迹覆盖与原生产物评分对照。
   完成证据前只报告 planning/indexed，不宣称 runnable/scored/protocol_validated。

conformance 只验证结构、目录保真、规划稳定性，不审查原生评分逻辑。对于原生重复/失败规则、
PAST fresh-session 和真实 state 使用、PostTrain 的模型来源/judges、ASI 正式提交资格等，必须有各自真实对照证据。

## 可选执行扩展 1.0

需要本机受管执行的包另实现 `invocation(plan) -> NativeInvocation`，从
`agent_infra.benchmarks.execution_api` 和 `agent_infra.environments.api.ProcessCommand` 导入公共对象。
该方法只返回确定的 argv、相对 cwd、超时和输出相对路径，不启动任务、不安装依赖、不修改源目录。
规划包没有此方法仍可 inspect/plan/check，只有 prepare 明确报“不支持执行扩展”。

可独立安装的实现见 [examples/benchmark-execution](../../examples/benchmark-execution/)；命令冻结、
opt-in、能力限制和验收脚本见[执行参考](../reference/benchmark-execution.md)。当前 backend 只处理
可信协作式进程，不接管 Docker/HPC 子作业；不能用包装原生 CLI 的方式绕过清理或资源要求。

## BM00 四类样例代表什么

| 样例 | 验证的表达能力 | 没有验证的内容 |
| --- | --- | --- |
| `asi-like` | produce 与外部评分/提交分离 | 没有运行 ASI scorer 或生成官方 provenance |
| `terminal-like` | 求解和独立 verifier、grader 材料角色 | 没有运行 Harbor 或官方任务 |
| `training-like` | Agent/目标模型/judge 分离、允许中间 eval、原生 GPU/时间要求 | 没有 H100 训练、HTCondor 或 judge 调用 |
| `sequence-like` | 完整配对、有序 episode、fresh session 与记忆 on/off 分离 | 没有运行 PAST 或验证真实记忆机制 |

模板里的 `demo-*` backend、模型、材料 URI 都是合成值；capabilities 文件是测试声明。
后续四个参考适配器必须是独立包，在真实固定 benchmark 输入上开发和验收，不能只改这些名字就算接入。

更换 benchmark 通常只改独立适配包。首次遇到模拟器/远程交互/HPC 等通用后端缺口时，
由独立 backend 阶段补执行能力；不得在 core 写 `if benchmark == ...` 特例。
稳定目标是已有能力范围内只改包与配置，完整调度/监控/迭代需要后续[阶段计划](benchmark-development-plan.md)全部相应链路交付。
