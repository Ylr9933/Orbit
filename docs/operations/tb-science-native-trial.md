# TB-Science：单任务原生 Harbor 试运行

状态：BM02-A 已集成；本次扩展原生 Codex 与批次检查。真实 Codex 求解与轨迹归档已有证据，但验收达到时间上限并在评分前取消；完整求解→评分链、完整套件和正式榜单尚未验收。

## 当前支持范围

- 独立 `agent-infra-tb-science` 适配包；复用独立 `agent-infra-harbor` 执行包。
- TB-Science commit `0efab0e6d7c6af5886e838990352ab85484cc234`；
  Harbor commit `bac9a80d1d63a0265cf85e8fe18f1b752dad62d7`（包版本 0.23.0）。
  同名版本但文件摘要不同会拒绝，升级须重新验收。
- 每个 Run 一个 Linux CPU 单步骤任务、原生 Codex / Oracle / Nop Agent、独立 verifier。
  Oracle 执行上游参考解，是基础设施测试，不能当作模型成绩。本轮真实验收为 Oracle；
  Nop 仅提供接入选项，未列入示例兼容性声明。Codex 配置与验收范围见下文扩展章节。
- 保留任务原有 agent/verifier/build 时限、网络策略、产物交接和评分。
  多服务 Compose、GPU、额外 MCP/凭证、跨节点不在此 profile 内；本机批次复用统一队列。
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

单任务默认使用单活动槽；批次可配置并发与持久租约/等待队列。磁盘声明只记录，Docker 存储配额未实现；
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
默认合并日志上限 8 MiB、产物收集上限 256 MiB；超限会明确截断或停在 `collecting`，不会假报完整。
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

## Codex 与全套离线检查（2026-09-26 扩展）

新的模型入口使用同一个 `tb-science` 适配器和原生 Harbor Codex，不使用 Oracle 替代模型。
安装当前主包、Harbor runtime 和 TB-Science 三个 wheel 后，使用
`adapters/tb-science/request-codex.json`。候选的 `agent=codex`、`agent_version=0.157.1`、
`model=gpt-6-sol`；版本必须为精确版本号，不能用 latest。可选 `codex_version` 必须与
`agent_version` 一致。候选配置变更时同步更新 `configuration_digest`。

认证参数 `auth_mode=host_codex` 默认读取执行用户 `~/.codex/auth.json`，由原生 Harbor 上传至
求解容器专用认证位置并清理；不挂载整个宿主机 Codex 目录，不继承本地 MCP、skills 或配置文件。
另一方式 `auth_mode=api_key` 通过参数 `api_key_file` 引用用户所有、权限 0600 的单行密钥文件；
worker 读取后仅在进程内设置原生 OPENAI_API_KEY。受管进程不继承终端环境变量，因此不能只在终端 export 密钥。密钥不能放在 request、
命令行或版本化文档中。私有 verifier 不接收求解 Agent 的认证。

`cpu`、`memory_mb` 是主容器资源准入上限，不会降低或覆盖任务明确声明的资源。
未声明 verifier 资源时使用这两个显式默认值。租约按求解/评测两个顺序阶段的峰值加上
最多 0.1 CPU / 128 MiB 网络辅助容器计算；构建和宿主机进程、磁盘仍不受容器限额控制。
外层预算覆盖原生 agent + verifier 时限和 2400 秒准备/清理余量，原生时限不变。

先做全套离线检查，不调用模型或 Docker：

```bash
"$RUNTIME/bin/python" -m agent_infra_tb_science \
  --source /path/to/terminal-bench-science/tasks \
  --request adapters/tb-science/request-codex.json \
  --output /path/to/new-suite-audit.json
```

输出每项任务的 eligibility、资源、预算和拒绝原因。此结果是静态准入检查，不是运行成功证明。
4 CPU / 8192 MiB 上限下，固定版本 70 个任务中 51 个通过；15 个超过内存上限，4 个被
Compose profile 拒绝（另一个 Compose 任务同时超内存，首先报告内存原因）。不能把这 51 项称为完整套件。
这些结论仅针对固定 revision 的资源声明，不保证所有代码路径或未来版本无 GPU 需求。
具体来说，70 项求解环境均声明 `gpus = 0`；评测环境有 2 项明确声明为 0、68 项未单独声明。
`physical-sciences/astronomy/rv-astrometry-fitting/task.toml` 的求解配置旁仍有
`max 1, expect H100` 注释，与数值声明不一致，须进一步核对上游意图与实际运行。
因此不能将离线准入通过表述为“所有任务均已验证不需要 GPU”。
更大资源预算须先明确授权；多服务任务仍需独立实现与验收，当前不自动削减资源或跳过任务。

单任务也使用与 ASI 一致的批次命令：

```bash
"$CLI" benchmark batch prepare \
  --directory /path/to/new-tb-batch \
  --config adapters/tb-science/adapters.toml --adapter tb-science \
  --sources /path/to/terminal-bench-science/tasks/mathematical-sciences/statistics \
  --pattern symbolic-regression --request adapters/tb-science/request-codex.json \
  --concurrency 1 --declare-compatibility
"$CLI" benchmark batch submit --directory /path/to/new-tb-batch --allow-native-runtime
"$CLI" benchmark batch worker --directory /path/to/new-tb-batch
"$CLI" benchmark batch status --directory /path/to/new-tb-batch
```

批量时 `--sources` 指向 tasks，`--pattern '*/*/*'` 匹配当前三层任务目录。
整个批次必须全部通过准备校验，否则不生成可运行批次，不默默排除失败项。
可将 `--sources` 指向已审阅的原始学科子目录、选择相应 glob；不要复制修改任务来绕过 Git 版本校验。
`--declare-compatibility` 仅是操作者声明，不是账号/模型/任务验收。

Records 归档完整原生 `trials/`（包括 Codex `agent/sessions/*.jsonl`、`trajectory.json`、
日志、原生导出提交、verifier 日志和 result），另加 `native-evidence.json` 文件摘要清单及缺失状态。
上限 256 MiB；超限会停在 collecting 等待处理，不静默截断原始产物。不是任意容器文件系统备份。
Web 通过同一只读轨迹入口展示 ATIF 派生视图，每次分页；视图最多 2000 步、每步 4000 字符，
明确标注截断，原始轨迹保持完整。模型隐藏推理、未导出的文件及完整系统调用不在记录承诺内。
评分、执行结果、证据完整度、清理状态分别展示；有分数不等于轨迹完整，也不代表官方榜单提交。

### 可选：复用本机固定版本发行包

精简任务镜像可能需要下载 Node/npm 大量依赖，超过原生 Agent 安装时限。
可在请求参数中设置 `codex_bundle`（绝对路径）和 `codex_bundle_digest`（本项目
`content_digest` 目录摘要），指向已安装的 **Linux 原生完整发行目录**，其中包含 `bin/codex`、
配套 helper/resources 和 `codex-path/rg`。不能传 npm JavaScript 启动脚本，也不能只复制一个
不带配套资源的可执行文件。示例来源是官方 npm 包 `@openai/codex-linux-x64` 的 vendor 平台目录。

准备与执行时分别核对目录摘要；只上传到求解容器，运行 `codex --version` 核对冻结版本。
版本/架构不匹配即失败，不静默回退。Harbor 随后的原生 Codex installer 检测到指定版本已就绪，
跳过重复安装；模型调用、指令、产物与 verifier 均仍由原生 Harbor 管理。安装证明进入 attestations。
未配置发行包时继续使用 Harbor 原生网络安装方式。目录应为可信官方包且不含凭据。

### 可选：容器访问宿主机 loopback 代理

`proxy_url=http://127.0.0.1:17890` 指向宿主机已有 HTTP 代理（不能带密码）。
本次 worker 在默认 Docker bridge 网关的临时端口建立转发，只接受实际核验过的求解主容器 IP，
退出时关闭连接与监听端口。原生 Harbor 通过 Agent 的 HTTP(S)_PROXY 使用它。
求解环境或 agent phase 声明非 public 网络时拒绝该参数，不以代理绕过原生 allowlist/no-network。
评测容器不会获得代理变量或转发授权，不改成 host network。使用自定义 Docker daemon/network 的部署
应先确认默认 bridge 网关可达；模型连接不能仅凭安装成功推断可用。

补充离线检查：将上限改为 4 CPU / 16 GiB（仅检查，没有实际启动大内存容器）后，65/70 项通过。
剩余 5 项涉及自定义 Compose，其中一项还声明环境变量；当前按实际首个拒绝原因报告。
这不等于 65 项真实模型验收，也不等于 GPU 在未来版本中永远不需要。
