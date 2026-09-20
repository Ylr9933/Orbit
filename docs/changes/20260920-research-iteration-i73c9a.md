---
record_version: 1
task_id: "20260920-research-iteration-i73c9a"
title: "I 批：证据分析、研究决策与有界迭代 Planner"
branch: "feat/research-iteration"
base_commit: "70fee90bd52669fee6226a828c033d87f2ed09de"
work_status: completed
updated_at: "2026-09-20T19:01:05+08:00"
pull_request: null
---

## Goal and acceptance

- 实现 I01–I04：真实 Records 引用、不可变 Analysis、明确来源的用户决策和 Plan N+1；保留旧 Task/Run。
- 持久预算及动作 ID；并发/重启不重复提交，不超授权次数/时间/CPU/内存；不能观测费用时不声称费用硬上限。
- 可替换的容器 Planner，外置状态与窄 API，独立实验容器，无 Docker socket、控制服务凭据或私有评分材料。
- 单元/集成/安装包验证；本机 Docker 两轮与容器替换测试。真实模型验收预算由用户明确批准，已完成两轮真实 Planner 验收。

## Changes

- I01：Projects AnalysisService 校验本项目终态 Run、可见 Artifact 成员，提取有限 JSON 指标、保留单位/方向/版本声明与证据摘要；解释不可变，修订使用新记录。
- I02：accept/modify/reject 决策、来源、revision/digest CAS；复用 B 的保存/采用，持久 applying 状态支持提交间隙恢复，关联前次 analysis 与新 Plan/Experiment。
- I03：冻结 Task 集合授权、次数/预扣超时/墙钟/CPU/内存限制、单实验并发、失败停止、显式停止/取消；持久动作 ID 与原 D submit 回执恢复。
- I04：独立、可替换 Codex Planner 容器，外部工作流状态；五个窄动作通过有界文件代理调用同一 Projects/Runs，用同一资源管理器共享总量；无 Docker socket、Controller token 或私有评分材料。
- CLI study/planner、HTTP 与既有 MCP 工具扩展；原始流、规范 Agent 事件、代理调用进入 Records。
- Project schema 4 增量表，文档/示例/项目概览/Skill 更新，安装包检查增加新入口和容器 helper。

## Decisions

- 基于尚未合并的 E（70fee90），不修改 main，不自动发布。
- 分离结果证据、解释、用户决策、授权策略和执行；复用 B/C/D 接口，不引入 DAG 引擎。
- 初期自动执行限定明确授权的冻结 Task 集合；超出集合的新建议暂停等待用户采用和授权。
- 用户批准真实验收：gpt-5.6-sol，最多 3 次 CLI、累计模型不超过 10 分钟；本机 Planner+实验同时最多 1 CPU/2 GiB，无 GPU，只清理本任务资源。实际 2 次 CLI，累计会话外层耗时 110.708641 秒（含启动清理，保守大于模型进程时长）。
- 真实验收的 Planner 使用真实 Codex；实验通过显式确定性 Python fixture 适配器在真实独立 Docker 中读取 CSV 并计算均值。未冒充容器内第二个 LLM；正式 D Codex 提交路径沿用既有实现，本批没有追加两次实验模型调用。
- 对未知费用明确返回不可观测，不声称精确金额上限；完整 timeout 预扣不退款，人工新增授权/Planner 启动另计，不提供全账户计费防线。
- 使用 skill-creator 对包内研究 Skill 做窄更新；未更改根治理规则或个人全局配置。
- 本机无模型 Docker 验证：最多同时 1 CPU/2 GiB，无 GPU，累计目标 15 分钟，仅清理任务所有资源。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | 最终代码子树，见下 | passed | 262 passed，22 个 E2E 未在本命令运行；Ruff、mypy（111 source files）、依赖边界、文档、Web 检查与 Python/Web build 通过；`/tmp/i-verify-final2.log` |
| `uv run --locked pytest -q tests/unit/runs/test_research_lifecycle.py tests/unit/runs/test_controller.py tests/unit/projects/test_iteration.py` | 最终隔离状态修正 | passed | 18 passed；`/tmp/i-recovery-focused.log` |
| `uv run --locked pytest -q -m e2e tests/e2e/test_iteration_planner.py tests/e2e/test_study_controller.py` | 最终接口/Planner 日志实现工作区 | passed | 3 passed，91.90 秒；真实容器两轮与替换、SIGKILL 后恢复不重放、HTTP/CLI/MCP 证据分析；`/tmp/i-docker-final.log` |
| `uv run --locked python /tmp/i04-acceptance.py` | 真实 Planner 验收工作区 | passed | 2 个真实 Codex 容器；两次实际计算 mean=2.0，分析归档，次数耗尽停止；`/tmp/i04-driver.log` |
| Records 独立核对 | I04 两个 Planner Run | passed | 30/31 规范事件，各 7 个代理动作、7 个原生工具结果、1 个 usage；原始 blob 引用存在 |
| skill-creator `quick_validate.py` | 包内更新后的研究 Skill | passed | frontmatter/结构通过；不等于独立模型 Skill 行为验收 |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 最终源码构建 wheel，仓库外安装 | passed | 新 study/planner 命令、容器 helper、原有工程/编译检查通过；`/tmp/i-wheel-final.log` |
| 任务资源清理、最终差异/文档检查 | 最终工作区 | passed | 无 agent-infra 所有权容器，认证副本清理完成，原有三个 RSI 服务保持运行；无密钥或运行产物进入版本库 |
| GPU、多节点、费用硬限额、真实模型实验执行端 | None | not_run | 范围外；实验端为明确的确定性适配器，不是占位的 Docker 后端 |

开发期失败已定位并修正：测试 image/tag 不匹配、fixture 遥测过期、Records producer/stream ID 跨会话重用、旧 schema 测试预期、H 清理恢复隔离状态回归。
Planner 同时保留原始与规范轨迹，最后终态日志页排空；后者及隔离错误收尾的最后修正用无模型测试覆盖，没有追加第三次模型调用。

最终代码子树快照：
`src=db5d82a9a5f3895eeb9d47cb0cdff7391a82923c`、
`tests=18b8f7de910a471ed2197d7174378d4c6df2ea28`、
`scripts=29e0097b434d51f2eb3e7f1eff14a076d3cc50e2`、
`examples=211d858ef1d2a4ab1635bbb432f3372f265024ec`。
全量检查中的既有 MCP/Pydantic lifespan warning 不影响测试；没有更改依赖来掩盖它。
最后增加时间额度耗尽的显式停止状态和公共 list 方法，8 项预算用例及最终 make verify 已覆盖。

### 真实验收证据

非版本化临时目录 `/tmp/agent-infra-i04-20260920-i73c9a`，不承诺永久保留。
Project `6349e395-6642-5375-9339-a825db72371a`；workflow `4f7763b03efa3c934310750a121e1e4e2b53c87a83bc3b66d1b2a4cf4b0a174a`。
Planner Run：`d2aa22b35f344ae2b04237679c62340c`、`a971868bb9b042439e46a5f124a66bc6`。
实验 Run：`997ac1cc06b347f3b4f2e06aeba8f426`、`5c135092fdd0459aaa7de23a0a88b38c`。
两个 Planner 分别约 55.50/55.21 秒；第二个新容器恢复第一轮状态且没有重复实验。

- evidence.json SHA-256：`deb06f7a38d533ef7529b082b2c2a4a3f99da0a4414988c27728e6ae78c8126c`
- budget.json SHA-256：`a2f20843a6a094cd76c2a9d7e76e08bff4cdbd101913bdb9ac22c4c1d3f31491`

## Open items and blockers

- None：I01–I04 首版范围的代码、真实 Planner 与容器恢复验收、打包验证均完成。
- 后续范围：新实验生成的更细授权策略、可核实费用接口、GPU/多节点及 Web 接入；当前仍是单用户本机 CPU。

## Next steps

- 审查任务分支并集成 H/E/I；再按实际科研需求试用或推进 W。当前未合并 main、未推送。

## Compatibility and rollback

- Projects schema 3 → 4 增量迁移，原研究/Task/Run 不重写。旧程序拒绝 schema 4；回退使用升级前备份，不能只降低 user_version。
- HTTP/MCP/CLI 为增量接口；Controller.submit 增加可选执行身份检查，旧调用保持兼容。旧手动提交路径不自动受某个 workflow 限制。
- 回退前停止本任务 Planner/Run，确认容器和认证副本清理；记录与原始证据保留。未改全局配置、依赖或远端。
- 现有项目已安装的旧 Skill 不会被自动覆盖；需要保留手工修改并显式更新。新版本 wheel 提供新 Skill。
