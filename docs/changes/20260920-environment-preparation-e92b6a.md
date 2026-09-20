---
record_version: 1
task_id: "20260920-environment-preparation-e92b6a"
title: "E 批：可验证的 Python CPU 环境准备与有限修复"
branch: "feat/environment-preparation"
base_commit: "43c78f0fb8f85a08ba23036a1a7fe5d57aedfc97"
work_status: completed
updated_at: "2026-09-20T17:34:00+08:00"
pull_request: null
---

## Goal and acceptance

- 完成 E01–E04 的 Python CPU 范围：需求、提案与锁分离；模板构建、独立 smoke，通过后用于 H/D。
- 接入既有 Controller 单执行槽、资源租约、Docker 所有权恢复与 Records；保留每次提案、日志、缓存来源和失败。
- Agent 在原 intent 的次数、时间、依赖及网络范围内修复；不能通过取消 smoke 或扩大权限绕过错误。
- 单元/集成、真实本机 Docker、独立 wheel；真实 gpt-5.6-sol 读取缺依赖错误、修复并实际使用锁定环境。

## Changes

- E01：EnvironmentIntent/Proposal/Preparer 契约，独立 environments.sqlite3 catalog；固定本机基础镜像 ID，
  版本 CAS、project/session 来源、锁定 intent/proposal 摘要、镜像、验证器版本和有效期。
- E02：Python CPU wheel 模板；复用 DockerEnvironment 隔离、配额、日志、取消、所有权恢复；
  成功停止的专用无凭据 build 容器才能发布镜像。缓存以固定构建输入和模板版本为键，镜像不存在时重建。
- E03：每次新建非 root、无网络 smoke 容器，检查 imports、精确依赖版本、工作区读写、可选 Codex 版本。
  失败不生成可用锁；最后清理、释放与记录完成后才发布 ready。记录写入失败隔离 Controller，避免假成功。
- E04：CLI `environment plan/propose/build/status/cancel/list`；原 MCP 新增六个准备工具，
  `environment_plan_status` 与原 `environment_status(run_id)` 区分。异步执行不依赖 MCP 连接；
  固定 intent、持久预算预扣、有限重试、停止条件和明确用户新决策边界。
- H：`environment_open` / `research open --environment-lock`；D：Task environment 可带 lock_id，
  编译保存 image+lock，预检核验项目、最新提案、有效期和 Agent 层；原手工镜像路径保留兼容。
- 新增[使用指南](../reference/environment-preparation.md)、[维护导读](../implementation/environment-preparation.md)、
  [示例](../../examples/environment-preparation/intent.yaml)，更新 README、导航、计划、相关命令参考和项目概览。
- 新增环境契约、工作流、锁绑定、工具注册测试；增加真实模板修复、缓存、取消/超时、CLI/MCP 和 SIGKILL 恢复测试。
  wheel 检查覆盖新命令及模块打包。

## Decisions

- 使用固定安装命令及公开 PyPI wheel 精确版本；不执行任意模型 Dockerfile、Shell、源码包或私有索引配置。
  安装在容器镜像层中，commit 不包含自有空工作区挂载；后续独立 smoke 不继承构建可写状态。
- Codex 层通过已有可信 Codex 0.154.0 基础镜像继承并实际检查；E 不另行读取或安装宿主机账号。
  宿主机真实客户端实测 0.155.1，不改变既有 D 版本兼容要求。
- 构建、H 和 D 复用同一 Controller 与配额；没有第二套 Docker 管理器或调度路径。E 只准备环境，
  不自动确认科研方案、上传数据或启动训练。Agent 修复由现有外部 MCP 客户端执行，Controller 不隐式调用模型。
- 时间按 intent 持久计数；崩溃不返还预扣，重启清理后标 interrupted，不自动重放。正常失败保留并允许预算内新提案。
- 用户批准 E04：gpt-5.6-sol，最多 3 次 CLI、累计模型运行不超过 10 分钟；本机同时最多 1 CPU/2 GiB、不用 GPU；
  公开 Python 包，只清理本任务资源。实际 2 次 CLI，221.769294 秒；未使用 gpt-6-astra。
- Docker 无模型检查同样本机、同时最多 1 CPU/2 GiB，无 GPU；真实安装与长进程测试均设超时，累计测试运行未超记录的 15 分钟范围。
  CPU/内存限制针对容器进程，Docker daemon 镜像发布与磁盘不承诺硬配额；控制调用/清理有超时宽限。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | 最终代码快照，子树见下 | passed | 249 项非 E2E 测试、Ruff、mypy（101 source files）、模块边界、文档、Web 检查与 Python/Web 构建；`/tmp/e-final-verify-2.log` |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 最终代码构建 wheel，仓库外安装 | passed | 原 A/B/C 场景、新 environment 命令与模块、既有 MCP 打包检查；`/tmp/e-wheel.log` |
| 六个 Docker 测试文件合并回归：environment_preparation / environment_controller / host_research / research_mcp / controller_recovery / run_environment | MCP 工具改名前工作区 | failed | 18 passed、1 failed；发现 environment_status 工具重名。旧 D/H 的 13 项全部通过；`/tmp/e-docker-full.log` |
| `uv run --locked pytest -q -m e2e tests/e2e/test_environment_preparation.py tests/e2e/test_environment_controller.py` | 最终代码快照 | passed | 6 项，59.17 秒；真实构建、缺依赖修复、缓存、锁、Codex 基础层、运行中取消/超时、CLI/MCP、SIGKILL 恢复；`/tmp/e-final-docker.log` |
| `uv run --locked python /tmp/e04-acceptance.py` 第二次启动 | E04 最终工具接口工作区 | passed | 真实 gpt-5.6-sol，20 次 MCP 调用全部成功；实际读到 ModuleNotFoundError 后修复并运行、关闭锁定 H 环境 |
| 原始 JSONL 独立核对 | E04 第二次证据 | passed | 20 个 completed MCP 调用、0 失败；错误日志进入 environment_plan_status 响应；无 host command_execution |
| Docker 容器及验收镜像清理检查 | 最终工作区 | passed | 本任务容器与两轮创建的四个镜像已清理；Python/Codex 输入镜像保留，原三个 RSI 容器保持运行 |
| GPU、系统包、任意 Dockerfile、多节点、其他真实模型客户端 | None | not_run | 本批范围外；D 新锁的编译/预检和真实 Codex binary smoke 已测，未重复调用容器内模型 |

最终代码子树：`src=1a3739b547f5e79454b0c5b1ae90137efe6cddcc`、
`tests=439c9f5b4648162f9ba8a62e84e3421dda2d21e6`、
`scripts=ee3b44070c3ea0d835f80792a8182917b999841b`、
`examples=aa62cd506940f05775cddb1721665257e9491040`。
日志与证据为非版本化本地文件，不进入 Git。

第一轮模型运行 121.904856 秒，虽然根据包清单修复成功，但新旧工具重名使原始日志工具不可用，
不算完整 E04 通过。改名并加入 19 个工具及不同输入 schema 的注册回归后，第二轮 99.864438 秒完整通过。
先完成真实 CLI/MCP 修复验证，再使用原授权预算重验；没有扩大模型权限或预算。
其他开发中失败包括 fixture 遥测超时、测试清理 helper 误用及完成状态提前发布，均已修正并由最终检查覆盖。
SDK 的既有 Pydantic lifespan 警告仍可见，不影响 MCP 调用与测试通过。

E04 后仅增加包清单防符号链接读取、来源关联和收尾边界等维护修正，最终规则/真实 Docker 测试覆盖，
没有追加第三次模型调用。

### 真实 E04 证据

目录 `/tmp/agent-infra-e04-20260920-e92b6a`，临时证据不提供永久归档保证。
Project `245aa9e7-b175-557d-a325-e6ed3c809119`；
第二轮计划 `8766d6b6ca73097691a61d5cf2ff475455b7b89f7fe5caf0dfbca351ed038708`；
失败尝试 `3595f2251bba418c8a10b91d00e04ab3`，成功尝试 `511a7260c0004376844b6f75b97cf3e6`；
H Run `2904c868c5ae4fcea1435c8b26b19961`。

Agent 读取实际缺少 six 的日志，把空 dependencies 修订为 `six==1.17.0`；独立 smoke 通过后使用 lock，
容器实际输出 `1.17.0`，关闭结果 cleanup_complete、lease_released、archive_complete 均为 true。
全程没有 GPU、训练、账号复制或全局 Codex 配置改动。

- `acceptance.json` SHA-256：`d4be71129d740165ed2e4cbb59e782e87b53744056b6af774de49abdc54329d8`
- `codex-2.jsonl` SHA-256：`cceebfb5176596ecec7655b49dab8a1fa8f80399db75b06f74429b2cc8f61fd9`
- `plan.json` SHA-256：`d2f4f40916f6d12b655953d13a0b8bf2134f230b628918caede9190cafc8b43e`

## Open items and blockers

- None：E01–E04 的 Python CPU 范围实现及验收完成。
- GPU/系统依赖、任意镜像生成、镜像自动 GC/远程备份、大数据材料和 I 批科研分析迭代仍是后续范围。
- 未部署常驻服务；任务分支未合并/推送，不代表远端已集成。

## Next steps

- 审查并集成 H/E，再按使用指南开展实际科研试用；下一功能批为 I 结果分析与方案迭代。

## Compatibility and rollback

- 新增 catalog schema 1；既有 Projects/Run/Records 库不迁移，依赖/锁文件未改变。
- Task schema 1 增加可选 environment.lock_id；旧二进制不识别此字段，回退时使用旧 Task 或重新生成不带锁的手工配置，
  不能修改已有冻结 Task 冒充原版本。旧手工镜像入口继续可用，但不承诺 E 验证。
- 回退前停止 Controller、确认自有环境已清理，备份状态/Records；构建镜像按精确 ID 管理，不做全局 Docker prune。
  不删除主机锁或所有权日志来绕过不确定清理。远端分支与其他服务未改动。
