---
record_version: 1
task_id: "20260918-local-run-controller-d73a91"
title: "D 批：本机持久运行控制与真实 Codex 实验"
branch: "feat/local-run-controller"
base_commit: "92d52093c32b10e4812a4240aa71e9d877daa80b"
work_status: completed
updated_at: "2026-09-18T23:15:45+08:00"
pull_request: null
---

## Goal and acceptance

- 完成 D01–D07：冻结 Task 预检、幂等提交、后台单运行控制、重启清理、HTTP/CLI、受控产物访问与真实 Codex 科研闭环。
- 复用 LocalRunService，保留旧 Python 调用；冻结材料、原有评测隔离、import-linter 方向和资源释放规则不变。
- 用户批准真实验收：gpt-5.6-sol，最多 3 次真实 Codex exec 会话、累计不超过 10 分钟；本机单容器 1 CPU / 2 GiB、不用 GPU，只清理任务资源。
- 实际使用 3 次会话；按提交接受到收尾的保守时间合计 252.48 秒。没有使用 gpt-6-astra。

## Changes

- D01：bootstrap 从 Projects 公共编译接口解析冻结引用；预检材料、资源、镜像、工具与账号。固定 image ID，执行前重核 TaskSnapshot；预检不创建容器/Lease。
- D02–D03：SQLite schema 1 保存操作 ID、预分配 Run/Attempt ID、请求、取消意图和结果；Controller 单 worker 复用 Run 内核，共享资源管理器和最新准入采样。重复请求返回原身份，同键不同参数冲突，忙/资源不足明确拒绝。
- D04：同 OS 账户跨状态目录互斥、dirty 状态归属；原子 Docker ownership 日记记录创建/删除阶段。重启清理自有容器后标记 interrupted，保留已完成的 Records 结果；未确认 create 不凭空查询解除隔离。
- D05：loopback bearer HTTP 和 CLI 提供 preflight/submit/status/cancel/list/events/trajectory/artifacts/artifact；产物按同 Run 的 manifest 成员读取，拒绝私有评测、凭据和任意宿主机路径。CLI 退出不影响实验。
- D06：Codex 固定 CPU 镜像构建脚本、最小 auth.json 副本及结束清理；补齐宿主机 loopback HTTP 代理到容器的认证模型 CONNECT 转发，不修改原代理。
- D07：小型统计研究项目经过保存/确认/编译，真实 Codex 编写并执行 Python 脚本，产出正确指标、报告和代码，8 个统一轨迹步骤可查；Project context 返回 Run 引用。
- 实际取消验收后修复了旧内核在主动取消时跳过最终日志读取的细节：确认停止、排空输出、记录 process.exited 后封存流；无法确认终态则明确 partial。
- 新增[命令参考](../reference/local-run-controller.md)、[维护说明](../implementation/local-run-controller.md)、[CPU 示例](../../examples/research/cpu-statistics/README.md)，同步 README、开发计划、文档导航和项目概览。

## Decisions

- [Controller ADR](../adr/20260918-local-run-controller.md)：持久意图与执行证据分开保存；单活跃 Run、不设隐式队列；崩溃中断并清理，不自动重复模型调用。
- 当前 HTTP 入口只接受本状态目录登记的已编译、无评测科研 Task；Provider 容器认证先支持 Codex。原同步内核继续支持隔离评测与直接 Python 组装。
- 首版只授权 CPU/内存；同账户主机锁不是跨账户/集群资源锁，不开放 GPU 准入。
- 镜像不包含凭据；代理认证值不进入普通 Run 请求/事件，只记录环境变量名称。Artifact 独立写入 Records，查询不依赖原容器。
- 本分支基于 C 批 `92d5209`；C/D 尚未合并 main，没有推送或创建 PR。项目状态文档明确这是拟合并状态。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | 最终代码快照，子树见下方 | passed | Ruff、mypy、依赖边界、Web 检查、文档检查、216 项非 E2E 测试、Python/Web 构建通过 |
| `uv run --locked pytest -q -m e2e tests/e2e/test_controller_recovery.py tests/e2e/test_run_environment.py` | 同上 | passed | 9 项真实 CPU Docker 测试；包含 SIGKILL 后重新启动、取消、隔离评测；明确使用 fixture，无模型/GPU |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 同上构建 wheel | passed | 脱离源码安装，原初始化/规划/编译/CLI 场景保持兼容 |
| `uv run --locked python scripts/dev/build_codex_research_image.py` | D06 工作区与本机官方 Codex 0.154.0 软件包 | passed | 固定 CPU 镜像可执行真实 Codex；无凭据进入构建上下文 |
| `agent-infra run preflight/submit/status/cancel/artifacts/trajectory` 与项目 context | D07 工作区，运行 ID 见下表 | passed | 真实模型成功与取消；第一次模型超时已保留，修复网络后重试成功；数值核验通过 |
| 独立 wheel 的 `run status`、原 operation ID 的 `run submit`、`run artifact --output`、`project research context` | 最终 wheel，工作目录 `/tmp`，Controller 已重启 | passed | 原 Run 身份不变、未增加模型调用、指标下载正确，三条项目运行关联持久存在 |
| 认证副本清理、Records Blob 扫描、Docker 清单核对 | 真实验收目录 | passed | 两层任务 auth 副本均删除；已知账号 token/key 字符串未出现在普通 Blob；原三个 RSI 容器仍运行；本任务 Controller 已停止 |
| GPU / 多节点 / 其他 Provider / 公网多用户 / 长期训练恢复 | None | not_run | 不属于本批验收范围，不据 CPU Codex 结果推断这些能力已完成 |

最终自动验证源码子树：`src=7eced8e40b32d3d9479e73fe8546ea27b258c554`、
`tests=7e24acfc65fa894f34a7901176aa71911f51232e`、`scripts=45c2f5b8a169c20be17bfc0ba6968189d532a503`。
依赖声明和锁文件未变。真实模型运行发生于本分支中间工作区；之后只追加取消流收尾、恢复证据与
Docker 创建窗口处理等修订，最终 9 项真实 Docker fixture 验证覆盖这些变化，没有超预算重跑模型。

### D07 真实证据

本机非版本化目录：`/tmp/agent-infra-d07-20260918-d73a91`。保留编译引用、submit/result/events、
metrics、trajectory、模型预算台账及独立 wheel 验收摘要；不保证临时目录永久保留。
项目 `902f3f3a-f685-5477-b5f4-1a6837ab60fd`，实验 `robust-statistics`，研究 revision 1。
Task `119f0418-f0fd-5e12-81d2-e2e33be175d5`，revision
`ac2d809240b388d5409362b298ec838d73a63c5ed198143a09d16ba9c131e8f4`。

| 操作 ID / Run ID | 结果 | 接受至收尾时间 | 证据 |
| --- | --- | --- | --- |
| `d07-real-1` / `95365e4143ec4fd98451f7e62575f194` | timed_out | 183.19 秒 | 容器未使用宿主机 loopback 代理，模型网络超时；轨迹、清理和释放均保留 |
| `d07-real-2` / `d44ec91b9f0a473b8108aae13de6aa8f` | completed | 59.13 秒 | 修复网络后真实执行成功；8 步统一轨迹，代码/指标/报告独立归档 |
| `d07-real-cancel` / `a72e6094c3e04f84a519a8fad4f7063d` | cancelled | 10.16 秒 | 观察到原生 turn.started 后通过 CLI 取消；清理与 Lease 释放均 true |

三次均明确指定 `--model gpt-5.6-sol --reasoning-effort low --network`；timeout 分别为 180、240、120 秒。
第三次在旧取消日志路径没有 process.exited，因此统一采用接受到收尾的保守时间核对总预算，未将其算作零耗时。
对应缺口已修复并通过后续真实 Docker 取消测试。

镜像：`agent-infra/codex-research:0.154.0`，ID
`sha256:7295f874d192133667f1c56708163be9fd36cb442a16518d23d77a3904918a7f`。
完整数据 mean=22、median=3；去掉最后一个值后 mean=2.5、median=2.5；没有隐藏 evaluator 或伪造评分。
首次镜像构建使用裸 image ID 作为 FROM 被 BuildKit 拒绝，修正为 repository digest 后构建通过。
测试开发中 HTTP 测试受宿主机代理影响、spawn 测试模块导入失败等问题均已修正，最终检查没有遗留失败。

证据 SHA-256：

- `acceptance-summary.json`: `6f3f935062d4559f11f4cee73bea7b3b902c0228e02eeed7ad93eda38bbe71b6`
- `events-2.json`: `52dd5136b3e293623c04657bda9b37e9ed252df00110b58a59d0fef6c17cb212`
- `metrics-2.json`: `1a5e004c4f7582baac98aa00f0820e3bc308731984cb5d898ad0ca27318e4562`
- `trajectory-2.json`: `6e55b1315a6d52a565e484b82abfb61a924d47cf8156370cb0b5260cdf0392d1`

## Open items and blockers

- None：本批实现与限定范围验收完成。功能范围限制见命令参考；未部署常驻服务，没有未结束的任务容器。

## Next steps

- 审查本地任务分支；获得合并授权后集成 C/D。后续按计划推进 H01 长期 Environment / Job，而非再建一套 Run 执行器。

## Compatibility and rollback

- 保留原 CLI、Python Run API 和已有项目/研究数据；新增可选 Run 参数与独立 controller schema 1，不升级 Projects schema。
- 回退前停止 Controller 并证明其容器已清理，备份状态目录。不要运行两个版本共同管理同一个资源命名空间；不要删除 dirty 标记绕过未完成清理。
- 本机留下可复用示例镜像和非版本化验收记录；未改动用户原 Codex 账号、原代理配置、现有 RSI 服务及远端分支。
