# TB-Science：单任务原生 Harbor 试运行

状态：BM02-A 任务分支，CPU 工程验收入口。尚未合并；不代表整套 benchmark、模型 Agent 或正式榜单验收。

## 当前支持范围

- 独立 `agent-infra-tb-science` 适配包；复用独立 `agent-infra-harbor` 执行包。
- TB-Science commit `0efab0e6d7c6af5886e838990352ab85484cc234`；
  Harbor commit `bac9a80d1d63a0265cf85e8fe18f1b752dad62d7`（包版本 0.23.0）。
  同名版本但文件摘要不同会拒绝，升级须重新验收。
- 一次一个 Linux CPU 单步骤任务、原生 Oracle/Nop Agent、独立 verifier。
  Oracle 执行上游参考解，是基础设施测试，不能当作模型成绩。本轮真实验收为 Oracle；
  Nop 仅提供接入选项，未列入示例兼容性声明。未给 Codex 等模型 Agent 宣称兼容性。
- 保留任务原有 agent/verifier/build 时限、网络策略、产物交接和评分。
  多服务 Compose、GPU、额外 MCP/凭证、跨节点及多任务调度不在此 profile 内。
- 示例选用 `tasks/mathematical-sciences/statistics/symbolic-regression`。
  其固定版本的能力声明见 `adapters/tb-science/capabilities.json`，不能随意用于其他任务。

上游参考：[任务仓库](https://github.com/harbor-framework/terminal-bench-science/tree/0efab0e6d7c6af5886e838990352ab85484cc234)、
[Harbor](https://github.com/harbor-framework/harbor/tree/bac9a80d1d63a0265cf85e8fe18f1b752dad62d7)。
不要修改 benchmark 内核以迁就本平台；能力不够时更换/扩展 runtime profile。

## 安装

需要 Linux、本机 Docker Engine + Compose、Python 3.12、项目固定的 uv 版本，且能拉取任务和 Harbor 所需镜像。
推荐独立虚拟环境，避免 Harbor 的可选依赖进入科研 Controller 的环境。
以下从本项目仓库根目录执行，先自行准备好指定版本的原始任务仓库。

```bash
RUNTIME=/tmp/infra-tb-runtime
WHEELS=/tmp/infra-tb-wheels
uv venv --python 3.12 "$RUNTIME"
uv build --wheel --out-dir "$WHEELS"
uv build adapters/harbor-runtime --wheel --out-dir "$WHEELS"
uv build adapters/tb-science --wheel --out-dir "$WHEELS"
uv pip install --python "$RUNTIME/bin/python" \
  -r adapters/harbor-runtime/requirements.lock "$WHEELS"/*.whl
CLI="$RUNTIME/bin/agent-infra"
```

只安装包不会启用适配器。必须通过显式的 `--config` 指定信任的 distribution/version/entry point。
这些包和 native runner 以宿主机用户权限工作，必须信任其代码与原生 Docker 构建输入；这不是不可信插件沙箱。

## 计划、检查、执行

文件输出与运行状态放在 benchmark 源码之外。`TASK` 指向一个任务目录，而不是整个仓库。

```bash
TASK=/path/to/terminal-bench-science/tasks/mathematical-sciences/statistics/symbolic-regression
STATE=/path/to/infra-tb-state
OUT=/path/to/infra-tb-plans
mkdir -p "$OUT"
CONFIG="$PWD/adapters/tb-science/adapters.toml"
CAPABILITIES="$PWD/adapters/tb-science/capabilities.json"

"$CLI" benchmark inspect tb-science --source "$TASK" --config "$CONFIG"
"$CLI" benchmark plan tb-science --source "$TASK" --config "$CONFIG" \
  --request adapters/tb-science/request.json --output "$OUT/plan.json"
"$CLI" benchmark check "$OUT/plan.json" --config "$CONFIG" --capabilities "$CAPABILITIES"
"$CLI" benchmark prepare "$OUT/plan.json" --config "$CONFIG" --output "$OUT/execution.json"
"$CLI" benchmark run "$OUT/execution.json" --config "$CONFIG" \
  --capabilities "$CAPABILITIES" --state-dir "$STATE" \
  --operation-id symbolic-oracle-001 --allow-native-runtime
```

`prepare` 的输出需要核对命令、任务摘要、资源与输出范围。新运行使用新的 operation ID；重放同一请求与同一 ID 不会重复启动。
运行是异步的，保存返回的 `run_id`：

```bash
RUN_ID=返回的run_id
"$CLI" benchmark status "$RUN_ID" --state-dir "$STATE" --config "$CONFIG"
"$CLI" benchmark events "$RUN_ID" --state-dir "$STATE" --config "$CONFIG"
"$CLI" benchmark artifacts "$RUN_ID" --state-dir "$STATE" --config "$CONFIG"
"$CLI" benchmark cancel "$RUN_ID" --state-dir "$STATE" --config "$CONFIG"
"$CLI" benchmark reconcile --state-dir "$STATE" --config "$CONFIG"
```

`status/reconcile` 查询已提交工作，绝不自动重启未知原生任务。native runtime 查询也需要原始启用配置。
`quarantined` 表示身份或清理待确认，不等同于评测失败；刚提交时短暂等待 supervisor 身份也可能出现。
继续查询确认；不要换 operation ID 来绕过还占用的槽位。

## 资源与数据怎么看

请求里的 `cpu`、`memory_mb` 是本次主容器准入上限；若原任务超过它们，拒绝执行，不悄悄缩减任务要求。
原任务声明的 CPU/内存保持不变；未声明的 verifier 数值使用显式默认值（1 CPU / 2048 MiB）。
求解和评测顺序执行；网络辅助容器另限 0.1 CPU / 128 MiB，因此示例同时最多 1.1 CPU / 2176 MiB。
Docker 实际 NanoCpus、Memory、镜像 ID、容器 ID 进入 `attestations/`。不使用 GPU。

这是容器限额与单活动槽，尚非全局资源租约/等待队列。磁盘声明只记录，Docker 存储配额未实现；
镜像下载、构建进程与持久化产物存储也不受这些容器运行期限额约束。共享机器仍须预留构建与存储空间。

Records 位于 `$STATE/benchmarks/records`，运行工作区在 `$STATE/benchmarks/workspaces/<run_id>`。
持久产物 `native-submission` 的 `outputs/` 包含：

| 文件 | 用途 |
| --- | --- |
| `native-job.json` | Harbor trial UUID、名称、实际任务请求 |
| `native-ownership.json` | 本次唯一 Compose 命名空间 |
| `native-cleanup.json` | 原生清理结果；查询时再次检查 Docker 中无残留 |
| `attestations/` | 容器限额与镜像证据 |
| `trials/<name>/result.json` | 原生 reward、异常、时序、任务 checksum |
| `trials/<name>/agent/` | 原生 Agent 日志/轨迹（取决于 Agent 是否产生） |
| `trials/<name>/verifier/`、`artifacts/` 等 | Harbor 原始评测日志与提交产物 |

原生 stdout/stderr 以 bounded raw stream 保存，成功收集后才释放执行槽。
默认合并日志上限 8 MiB、产物收集上限 16 MiB；超限会明确截断或停在 `collecting`，不会假报完整。
Oracle 不产生模型思考/token 轨迹。原生目录保留格式，不伪造统一 RL 样本。

执行成功、评测成功、reward、清理与采集是不同字段。异常或缺少 reward 不能解释为有效 0 分。
`native_result` 给出原生 trial ID、评分解释及原始证据相对路径；没有自动提交榜单或自动优化。
所有原生材料、计划和日志目前均为 ADMIN，不将评测日志或私有答案推送给求解 Agent。

## 故障处理

- 镜像下载失败：查看原生 `trial.log`/合并日志，修复镜像网络后启动一个新 trial；不能改 verifier 网络规则绕过失败。
- 无清理回执、daemon 不可达、仍存在原生容器：保留隔离状态和原始证据，先恢复 Docker/调查对应 ownership。
  不得凭“主进程已退出”直接释放槽，也不得对全机执行 prune/down。
- 源码或 adapter/runner 改动：重新生成计划、执行文件并检查版本组合，不重用旧 prepared execution。
- 镜像缓存保留供后续使用；只清理本任务容器、网络、卷，不删除其他任务或共享镜像。

实现说明：[Harbor 接入与边界](../implementation/benchmark-harbor.md)。

## 重复工程验收

在已安装上述 wheel 的专用环境中，可运行：

```bash
"$RUNTIME/bin/python" scripts/acceptance/benchmark_tb_science.py \
  --allow-docker --source "$TASK" --output /tmp/infra-tb-new-acceptance \
  --config "$CONFIG" --capabilities "$CAPABILITIES" \
  --request adapters/tb-science/request.json
```

输出目录必须尚不存在。脚本串行运行 Oracle、同产物原生 regrade、以及容器启动后取消，
并验证相同 operation ID 不重复启动。每轮观察最多 20 分钟，超时请求本任务取消；
不调用模型或使用 GPU，完整原始证据保留在输出目录，摘要在 `acceptance.json`。
