# E 批实现导读

状态：与 E 批源码同步；使用方式见[命令参考](../reference/environment-preparation.md)，验证见[任务记录](../changes/20260920-environment-preparation-e92b6a.md)。

## 模块与调用链

| 文件 | 维护职责 |
| --- | --- |
| `environments/preparation_api.py` | Intent、Proposal、执行结果、Preparer 协议；白名单、版本、资源/预算范围校验 |
| `environments/preparation_store.py` | 独立 SQLite catalog；持久方案、修订、尝试、锁、镜像缓存 |
| `environments/preparation_locks.py` | 精确锁核验；供 H 与 D 共用，不信任用户编辑的导出 JSON |
| `environments/preparation_docker.py` | 固定 Python 模板命令、安装结果、独立 smoke、日志排空、取消和清理 |
| `environments/docker.py` | 原容器引擎；新增 build phase 和成功停止后的镜像发布，继续维护所有权日志 |
| `runs/environment_preparation.py` | 有预算的准备工作流；资源槽/lease、版本条件、后台线程、状态完成及 Records |
| `runs/research.py` | 复用项目/会话绑定、幂等回执和错误转换；转发 environment 操作，打开环境时解析锁 |
| `gateways/cli/environment.py`、`gateways/mcp/environment.py` | 参数和工具协议适配；不自行接触 Docker 或状态数据库 |
| `bootstrap/controller.py` | 组装相同的 Docker 实例、资源管理器、Records 与环境准备服务 |
| `bootstrap/run_preflight.py` | D 冻结 Task → 验证 environment.lock_id → 固定 image ID 与 Run lineage |

CLI 与 MCP 都经过原有 authenticated loopback HTTP `research/call`。HTTP 无需再复制一套环境路由。
幂等作用域是 project/session/operation ID；参数不同拒绝重用。回复丢失可以查询状态，未确认意图不自动重放。

## 为什么采用容器模板

安装在专门的 build 容器内进行，复用现有 CPU/内存、日志、所有权和取消能力。
此阶段根文件系统可写，UID 0，但无 capabilities、无 GPU、无 Agent 账号、无 Docker socket，
仅有自有空工作区；实际安装使用固定的 `python -I -m pip --isolated` 命令。
依赖来自已校验的精确版本列表，只允许公开 wheel，不执行模型生成的 Dockerfile 或 Shell。

进程成功退出后 `publish_build` 再核验容器归属与退出状态，用 Docker commit 发布固定镜像 ID，
重置镜像运行用户和启动命令；已安装依赖在镜像层中，临时工作区不进入镜像。
这里采用 commit 的范围很窄：它只发布无凭据模板容器，不能用于科研求解容器，也不会把 Agent 改写过的求解环境当可信评测环境。
[Docker commit 官方说明](https://docs.docker.com/reference/cli/docker/container/commit/)明确区分镜像层和挂载内容。

成功安装不等于 ready：先移除构建容器，再创建无网络、非 root、根文件系统只读的新容器进行 smoke。
检查由 immutable intent 指定的 imports、直接依赖的精确版本、工作区输出读写，以及可选 Codex 版本。
因此同一时刻只有一个执行容器，修复提案无法关闭检查。
安装元信息取自 [pip 安装报告](https://pip.pypa.io/en/stable/reference/installation-report/)，仅保留包名、版本和包哈希，不把下载 URL 或账号写入锁。

## 状态、并发和预算

环境准备、H 研究环境、D 单次求解共享 `LocalRunController` 单执行槽。准备线程独立于 MCP/CLI 连接，
使用已有 `ResourceRequest` 准入；不足直接拒绝。lease 只有确认全部容器清理后才释放。
失败原因、是否清理和锁是否可用分开表示；失败记录不被后续成功覆盖。

Intent 保存后固定基础镜像 ID；Proposal CAS 检查 expected_revision。
每次 build 必须指定当前 revision，并在启动前持久记录尝试及预算预扣。
正常完成后归还未用时间；崩溃保守保留全部预扣值。重启先运行原 Docker ownership journal 清理，
再将未终结准备尝试标 interrupted，保留历史及剩余预算，不自动重放。

缓存索引只对应生成镜像的输入，smoke 每次单独执行；锁绑定 intent digest、proposal digest、revision、
模板/验证器版本、镜像 ID、有效期和来源 Run。新提案使旧锁不能用于新 Run。
旧手工镜像路径保留，不能把它表述为自动验证路径。

## 扩展时改哪里

新增依赖源或 GPU 模板：先扩展 Intent 白名单与授权契约，再扩展 backend 和真实验证；不要在 gateway 拼接命令。
修改固定安装步骤/检查语义：更新模板或 smoke 版本，令旧缓存/旧验证按设计失效。
增加 Claude Code 等容器 Agent：扩展 Agent 层解析、版本检查和 D 的 provider/凭据适配；不能只放宽字符串枚举。
分布式构建：实现 EnvironmentPreparer 公共协议，另行处理远端镜像可达性、持久租约和日志，不把 Ray/Docker 对象传给上层。

单元测试覆盖参数边界、预算、版本、失败和清理；真实 Docker 测试覆盖缺依赖修复、缓存、Codex 基础层、MCP 与重启。
测试里显式 FakePreparer 只验证工作流规则，不能替代真实 Docker 或真实 Agent 验收。
