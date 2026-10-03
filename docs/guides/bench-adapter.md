# 接入新 benchmark

适用版本：`feat/bench-adapter-protocol`。模型、判定规则与协议定义见 [design §7](../design.md#7-刷榜bench)。

## 1. 先选路线

| benchmark 的形态 | 路线 | 要改 Orbit 吗 |
| --- | --- | --- |
| Harbor 任务目录（`task.toml` + `instruction.md` + `environment/` + `tests/` + `solution/`），verifier 为 `environment_mode = "separate"` | 内置 `harbor` 适配器 | 否 |
| ASI-Bench seed31415 | 内置 `asi` 适配器 | 否 |
| 其他任何形态 | 写一个外部适配器（任意语言的可执行文件），登记时 `--adapter /path/to/adapter` | 否 |

外部适配器和内置适配器走同一套协议，Orbit 不需要重新构建或重启。适配器文件放在 benchmark 仓库或任意目录。
示例：[examples/bench-adapters/researchclawbench](../../examples/bench-adapters/researchclawbench/)。

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

## 3. 写一个外部适配器

适配器是一个可执行文件（带 shebang，`chmod +x`）。Orbit 以 `<adapter> <op>` 调用它，cwd 为 benchmark 目录，
stdin 是一个 JSON 请求，stdout 必须是一个 JSON 回复；出错时写 stderr 并以非 0 退出。每次调用 120 s 内结束，
不要在适配器里跑实验或打分——那是 solve / verify Run 的事。

| op | 请求中有 | 回复 |
| --- | --- | --- |
| `tasks` | `benchmark: {name, path, config}` | `{"tasks": [{"id", "title", "supported", "reason", "tags"}]}`；不能跑的任务 `supported: false` 并写原因 |
| `solve` | + `trial: {id, task, method, seed, options, timeoutMin?, staging, hostNetwork}` | `{"spec": <Run 描述>, "issues"?: []}` |
| `verify` | + `solve: {run, output}`（`output` 是 solve 的 `$ORBIT_OUTPUT` 宿主路径） | `{"spec": <Run 描述>, "issues"?: []}` |
| `score` | + `verify: {run, output}` | `{"score": 数或 null, "maxScore": 1, "invalid": false, "issues": []}` |

Run 描述就是 `orbit run` 的 RunSpec 字段（`image` 或 `dockerfile`、`resources`、`mounts`、`env`、`network`、`workdir`、
`collect`、`timeoutMin`、`backend: "process"`、`cwd`……），另有两条规则：

- **Agent 交给 Orbit**：`trial.method.agent` 是 `codex` / `claude-code` 时，solve 给 `"agentTask": {"instruction": "..."}`
  而不是 `command`。Orbit 生成对应 CLI 命令并注入 auth、方法 bundle 和网络；适配器不要拼 `codex exec` 之类的参数。
  `oracle` / `empty` 给 `command`（没有参考解时对 oracle 报错即可，trial 会记为 invalid 并写明原因）。
- **不要写 Orbit 管的字段**：`name group params project snapshot auth agentBundle agent parentId priority passEnv`。
  benchmark 的 `env` 会加到两个 Run，`--pass-env` 的密钥只给 verify Run。

约定：

- `trial.staging` 是 trial 私有目录，放要挂进 Run 的副本或可写工作区；trial 结束时删除，需要留下的文件用 `collect`
  采集到 solve 输出（`output/collected/<容器路径>`）。挂载点在宿主目录内的，先建好目录，避免 Docker 以 root 创建。
- benchmark checkout 只读：不要在里面写结果；Python 设 `PYTHONDONTWRITEBYTECODE=1`。
- 分数可信才算 `invalid: false`：评审 / scorer 内部出错、模型不可用导致的 0 分要标 `invalid` 并写 issue；
  "方法没有产出"是方法的结果，应是有效的 0 分。取消、超时、未启动由 Orbit 判定，不用处理。
- 原生 runner 自己起容器时用 `backend: "process"`，容器经过 PATH 中的 `docker`（Orbit shim）才会被标记、限 GPU 与清理。

调试循环：

```bash
orbit bench add mine /path/to/benchmark --adapter /path/to/adapter.py -c key=value --pass-env JUDGE_KEY
orbit bench tasks mine                                   # 调用 tasks；登记时已调用过一次
orbit bench run mine -t <task> -m empty -n smoke         # 走一遍 solve → verify → score
orbit bench show <job>                                   # issues 中有适配器的报错
orbit logs <solve 或 verify run>
```

也可以手工喂请求：`echo '{"protocol":1,"op":"tasks","benchmark":{"name":"x","path":"/p","config":{}}}' | ./adapter.py tasks`。
修改适配器后不需要重新登记（除非改了 `config`）。

## 4. 接入验收

每个新 benchmark（包括 Harbor 路线的新任务集）都要有这三项证据，写进任务记录：

1. **oracle 满分**：`-m oracle` 在抽样任务上全部 valid 且为满分（没有参考解的 benchmark 省略，并写明）。
2. **空答案零分**：`-m empty` 全部 valid 且为 0。invalid 说明适配器把"没有产出"当成了环境错误，要修。
3. **与原版一致**：对同一批产物运行原版打分（或用原版工具跑同一方法），逐任务比较；差异要能解释（随机性、版本），
   不能解释的视为适配器错误。评审为 LLM 时，同一份产物多次打分的波动本身就要先量出来。

然后再用真实 Agent 方法跑，`orbit bench compare <job...>` 或 Web `/bench/compare` 查看。
