# 接入新 benchmark

适用版本：`refactor/ts-rewrite` R3。模型与判定规则见 [design §7](../design.md#7-刷榜bench)。

## 1. 先选路线

| benchmark 的形态 | 路线 | 需要写代码吗 |
| --- | --- | --- |
| 已是 Harbor 任务目录（`task.toml` + `instruction.md` + `environment/` + `tests/` + `solution/`），verifier 为 `environment_mode = "separate"` | 直接用 `harbor` 适配器 | 否 |
| 有 Harbor 适配器，或能导出为 Harbor 目录 | 导出后用 `harbor` 适配器 | 否（只写导出脚本，放在 benchmark 仓库） |
| 原生 runner 不可拆分（自己起容器、自己打分，如 ASI） | 新增一个原生包装适配器 | 是，`packages/orbit/src/bench/<name>.ts` |

能转成 Harbor 目录就不要写原生包装：Harbor 路线的 solve/verify 都是 Orbit 自己的 docker Run，
隔离、资源、产物采集和清理都已验证。

## 2. Harbor 路线

```bash
orbit bench add tbs /path/to/terminal-bench-science --adapter harbor
orbit bench tasks tbs                      # 列出任务；不支持的任务给出原因
orbit bench run tbs -t <task> -m oracle -m empty -n smoke
orbit bench show <job>
```

Orbit 读取的 `task.toml` 字段：

| 字段 | 用途 |
| --- | --- |
| 顶层 `artifacts` | solve 结束时采集，复制挂载进 verifier 的同一路径（表形式可写 `destination`） |
| `[environment] cpus / memory_mb / gpus / network_mode / env` | solve Run 的资源、网络与环境变量 |
| `[agent] timeout_sec` | solve 超时（`orbit bench run --timeout` 覆盖） |
| `[verifier] environment_mode / timeout_sec / env`，`[verifier.environment]` | verify Run（默认无网络） |
| `[solution.env]` | oracle 运行 `solution/solve.sh` 时的环境变量 |
| `[metadata] domain / field / subfield` | 任务标签 |

verifier 必须把分数写到 `/logs/verifier/reward.txt`（一个数）或 `reward.json`（`reward` 键或唯一键），满分为 1。
不支持：docker-compose 环境、`environment_mode = "shared"`、非 main service 的 artifacts。

## 3. 原生包装路线

新增 `bench/<name>.ts`，实现 `bench/adapter.ts` 的 `Adapter`，并在 `BenchService.adapter()` 与
`contracts.BenchAdapter` 中登记。适配器只生成 RunSpec、读文件，**不提交 Run、不判定 valid/invalid 以外的状态**
（取消、超时、未启动等由 `classify` 统一处理）。

| 方法 | 要做的事 |
| --- | --- |
| `tasks(b)` | 列出任务；不能运行的标 `supported: false` 并写原因（不要静默丢掉） |
| `solveSpec(ctx)` | `backend: "process"` 运行原生 runner，输出写到 `$ORBIT_OUTPUT` 下；声明资源（GPU 由租约经 `CUDA_VISIBLE_DEVICES` 与 docker shim 传入）；oracle 与 empty 必须有对应命令 |
| `verifySpec(ctx, solve, solveOutput)` | 另起一个 Run 打分（`priority: 1`）；不要写 solve Run 的输出目录，需要改动时复制到自己的 `$ORBIT_OUTPUT` |
| `score(ctx, solve, solveOutput, verifyOutput)` | 读分数，返回 `{score, maxScore, issues, invalid}`；打分器内部错误、配置导致的 0 分（如模型不可用）标 `invalid` 并写 issue |

约束：

- benchmark checkout 只读：process Run 的 cwd 是 Run 目录，用 `PYTHONPATH` 等指向 checkout；Python 设
  `PYTHONDONTWRITEBYTECODE=1`。
- 原生 runner 启动的容器必须经过 `PATH` 中的 `docker`（Orbit shim），这样才会带标签、被取消和清理，GPU 才受租约限制。
  不要在 runner 中写死 `/usr/bin/docker`。
- 密钥（评审模型 key 等）用 `orbit bench add --pass-env NAME`，不要写进 `env` 或命令行。
- 单测放在 `packages/orbit/test/bench.test.ts`：任务解析、分数解析（含缺文件、坏 JSON、内部错误）。
  需要端到端时，仿照 `bench.daemon.test.ts` 用假的 runner 走 daemon。

## 4. 接入验收

每个新 benchmark（包括 Harbor 路线的新任务集）合并前都要有这三项证据，写进任务记录：

1. **oracle 满分**：`-m oracle` 在抽样任务上全部 valid 且为满分。不满分先查参考解、产物路径和 verifier。
2. **空答案零分**：`-m empty` 全部 valid 且为 0。invalid 说明适配器把"没有产出"当成了环境错误，要修。
3. **与原版一致**：用原版工具对同一批任务跑同一方法（或对 Orbit 采集的产物运行原版打分），逐任务比较分数；
   差异要能解释（随机性、版本），不能解释的视为适配器错误。

然后再用真实 Agent 方法跑，`orbit bench compare <job...>` 或 Web `/bench/compare` 查看。
