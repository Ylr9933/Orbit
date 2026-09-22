# 文档导航与归档规则

没有对话历史时，先读根目录 [AGENTS.md](../AGENTS.md) 或其同内容副本 [CLAUDE.md](../CLAUDE.md)，再读[项目进度](project-status.md)、相关任务记录和设计文档。当前目录中的草案、空目录和占位文件不代表功能已实现。

## 文档应该放在哪里

| 位置 | 回答的问题 | 内容举例 |
| --- | --- | --- |
| [product/](product/) | 要做什么、为谁做、验收什么？ | 产品目标、用户场景、范围、功能验收要求 |
| [architecture/](architecture/) | 系统如何组成、模块怎样协作？ | 整体架构、模块边界、接口方案、技术设计问答 |
| [adr/](adr/) | 某项重要技术选择为什么这样决定？ | 背景、备选方案、决定、代价与影响；标明提议、采纳或被替代状态 |
| [development/](development/) | 开发者如何开发和协作？ | 开发顺序、开发环境、测试方式、贡献流程、工程准备度评估 |
| [operations/](operations/) | 系统如何部署、维护和排障？ | 安装初始化、节点加入与移除、监控、升级、备份与恢复手册 |
| [reference/](reference/) | 某个接口、参数或命令的精确定义是什么？ | API、配置项、命令参数、协议语义、兼容矩阵；注明版本和实现状态 |
| [implementation/](implementation/) | 当前代码具体怎样工作、从哪里继续读？ | 已实现调用链、对象关系、关键分支、失败路径和扩展点；必须与源码同步 |
| [changes/](changes/) | 某个开发任务做了什么、证据与下一步是什么？ | 每任务一份记录，格式与生命周期见 AGENTS.md |
| [assets/](assets/) | 文档引用的小型素材在哪里？ | 架构图片、说明截图；不放训练日志、数据集或运行产物 |
| [project-status.md](project-status.md) | 项目总体做到哪里了？ | 当前阶段、已有能力、主要缺口和下一步优先级 |
| 本文件 | 如何找到文档、如何选择归档位置？ | 目录地图与阅读入口 |

## 放置与维护原则

- 优先更新已有权威文档。一个主题需要多种视角时，用链接关联，避免多处复制完整说明。
- “系统应该怎样设计”放 `architecture/`；“当前代码为什么这样走”放 `implementation/`；“按这些步骤部署已有功能”放 `operations/`。实现解读必须区分已落地代码与后续连接点，代码路径发生实质变化时同步更新。参考手册和操作手册中的未实现内容必须明确标为草案，操作步骤注明前置条件与验证范围。
- 重要架构取舍写 ADR，任务记录引用它；任务记录不能代替长期接口文档，项目进度不能变成总流水日志。
- 文档移动时更新引用。目录一旦有实际受 Git 跟踪的文件，就不再需要 `.gitkeep`；空目录可以用它占位。
- 产品运行需要的提示模板和资源随源码交付；运行日志、权重、数据和任务产物进入配置的持久存储，不放 `docs/assets/`。
- 已有历史文件可以保留原位置，通过导航说明用途。本轮不批量搬迁：初始目标文档和手绘图仍在 `architecture/`，后续新增纯产品需求或文档素材按上表归档。

## 当前阅读入口

1. [项目进度](project-status.md)：确认实际状态。
2. [初始目标与需求](architecture/Agent_Infra_目标与架构设计_v0.1.md)、[仓库工程设计](architecture/repository-architecture.md)：理解项目背景与初始骨架。
3. [Agent / Environment 模块设计](architecture/agent-environment-modules.md)：了解功能模块边界；一级目录已在 S0 落地，业务接口仍为草案。
4. [环境与运行问题问答](architecture/environment-operations-qa.md)：了解自动建环境、集群、轨迹与两种运行方式的建议。
5. [开发顺序](development/development-sequence.md)、[协作开发准备度](development/development-readiness.md)：确定开发先后；准备度文档保留 S0 实施前评估。
6. [S0 工程基础计划与验收](development/s0-engineering-foundation.md)、[贡献指南](../CONTRIBUTING.md)：查看当前可执行的安装、检查和协作入口。
7. [四人协作分工](development/four-person-collaboration.md)：认领 S1/S2 模块职责、接口共同评审和集成任务。
8. [S1 开发计划](development/s1-contracts-and-examples.md)：最小契约、替身、任务样例与验收安排；Agent、Resources、Tasks 及首版 Run/Environment 已部分落地，仍以项目进度和实现文档为准。
9. [Agent 模块与可替换 CLI Agent](architecture/agent-module.md)：公共抽象、Codex/Claude Code/DSH、宿主机/容器模式、认证隔离和后续集成边界。
10. [初期检查和复盘](architecture/初期检查和复盘.md)：明确 Agent 操作 Docker 内任务的边界、HTTP/CLI/MCP 分工、产品用途、当前可用能力与后续打通顺序。
11. [0917 设计微调](architecture/0917设计微调.md)：详细设计从一句研究目标到 Project 初始化、研究规划、自动环境、实验分析和迭代的主线，并明确代码与 Skill 分工。
12. [资源管理、Docker 与 Ray 多节点](architecture/resource-management.md)：资源 YAML、宿主机实时观测、资源不足、Docker 限额、Ray 调度和集群认证方案。
13. [Tasks 建模与 benchmark 转换](architecture/task-model.md)、[Tasks API 与命令](reference/tasks.md)：完整目标与首批实现范围；任务契约、可见视图、草稿和索引导入已落地，自动工作流、工具运行与原生评测等价仍待接入。
14. [Agent 实现解读](implementation/agent-implementation-guide.md)、[Resources 实现解读](implementation/resource-implementation-guide.md)：沿当前源码理解公共对象、调用链、关键判断、失败路径和未实现边界。
15. [Records 模块详细设计](architecture/records-design.md)：原始证据、规范事件、产物与评测、宿主机/容器采集、存储查询，以及面向轨迹分析和 Agentic RL 的派生数据设计。
16. [Records API 与命令](reference/records.md)、[Records 实现解读](implementation/records-implementation-guide.md)：查看已实现的本地存储、Run 接入、轨迹派生、查询命令和当前限制。

`AGENTS.md` 与 `CLAUDE.md` 中的简表用于快速定位；具体归档示例与阅读导航在本文件维护。更新规则时同步两个根规则文件。

## 当前代码检查

- [模块衔接检查与下一步计划](development/20260920-integration-review.md)：实际调用链、已修复问题、维护入口、功能缺口与分步验收。

## 单节点执行

- [当前功能与首次科研任务试用](operations/first-research-trial.md)：从初始化、Codex MCP、Docker 实验到 Web 查看结果，并说明 GPU 已有基础与待接通边界。
- [单机 GPU 诊断与准入](operations/gpu-local.md)：G1/G2 的诊断、自检、Controller UUID 授权、冻结 Task 请求及真实环境限制。

- [科研工作流细分开发计划](development/research-workflow-implementation-plan.md)：A 批初始化、B 批研究规划及后续执行的实施顺序；实际验收与集成状态以任务记录为准。
- [Project 初始化命令](reference/projects.md)：一句目标创建研究工作区，支持指定目录、自动命名、预览、查询和恢复。
- [科研规划使用说明](reference/research-planning.md)：保存 Brief/Plan/Experiment、版本确认、笔记导入、会话恢复及项目内 Skill。
- [实验编译命令](reference/experiment-compilation.md)：将采用的实验与选中材料转成冻结 Task，查询历史关联，显式重绑定移动后的项目。
- [科研工作流代码结构](implementation/project-workflow-code-guide.md)：实际模块边界、Projects 存储拆分、编译调用链及修改入口。
- [实验编译 ADR](adr/20260918-experiment-compilation.md)：材料副本、稳定 Task 身份、发布恢复及控制库升级。
- [研究快照 ADR](adr/20260918-research-planning.md)：研究 revision、精确确认、数据库升级与文档冲突的处理。
- [初始化存储与恢复 ADR](adr/20260918-project-initialization.md)：权威存储、工作区所有权、并发和旧 Web catalog 的边界。

- [Web 科研控制台方案](architecture/web-console-design.md)：完整页面规划、模块边界与分期验收。
- [W 批科研工作流](architecture/web-research-workflow.md)：新旧项目兼容、研究方案、实验预检/提交/取消、产物和分析的实现边界。
- [Web 控制台使用说明](operations/web-console.md)：已实现简版的启动、SSH 访问、页面范围、HTTP 接口与验证方式。

- [Run / Environment 契约](architecture/run-environment-contract.md)：仅求解与隔离评测设计。
- [Benchmark 接入层设计](architecture/benchmark-integration-layer.md)：四类协议/执行适配、调度、状态轨迹与外层优化；BM00/BM01/BM02-A 已进入本地 `main`，BM02-B 在当前分支完成工程验收。
- [Benchmark SDK 与命令](reference/benchmark-sdk.md)：独立适配包、显式启用、规划冻结和兼容性检查。
- [BM01 受管执行](reference/benchmark-execution.md)、[执行实现说明](implementation/benchmark-execution.md)：可信本机进程、持久提交、恢复、取消和 Records；通用本机进程后端。
- [BM02-A TB-Science 试运行](operations/tb-science-native-trial.md)、[Harbor 实现](implementation/benchmark-harbor.md)：独立适配包、原生容器 trial 与工程验收边界。
- [BM02-B ASI-Bench 试运行](operations/asi-bench-native-trial.md)、[实现路径](implementation/benchmark-asi-bench.md)：公开 seed31415 原生产出/评分及 seed42 外部提交边界。
- [Benchmark 实施顺序](development/benchmark-development-plan.md)、[适配包开发指南](development/benchmark-adapters.md)：每阶段检查点与新 bench 的独立包接入方式。
- [Benchmark 协议与执行分离 ADR](adr/20260922-benchmark-protocol-execution.md)：原生 runner、独立适配包、执行后端与优化循环的职责边界。
- [执行 API 与验证说明](reference/run-environment.md)：Python 组装、记录、安全边界及真实 Docker 测试。
- [宿主机科研与 MCP](reference/host-research-mcp.md)：长期环境、后台 Job、MCP 接入、文件、日志、产物及宿主机原生流导入。
- [宿主机 Codex 会话绑定与采集](reference/codex-host-sessions.md)：按项目目录发现候选会话，显式绑定、增量导入与通知触发同步。
- [H 批实现导读](implementation/host-research-mcp.md)：监督进程、Controller 用例、幂等状态、采集和故障恢复。
- [本机 Run 控制服务](reference/local-run-controller.md)：冻结 Task 的预检、提交、查询、取消、认证、结果下载与 CPU 示例。
- [Controller 实现与恢复](implementation/local-run-controller.md)：命令持久化、单 worker、资源互斥、Docker 对账及扩展入口。

- [环境准备与有限修复](reference/environment-preparation.md)：E 批 intent/proposal/lock、CPU 模板、预算、缓存及 H/D 接入。
- [环境准备实现导读](implementation/environment-preparation.md)：模块职责、容器构建与独立 smoke、持久化和故障边界。

- [结果分析与有界迭代](reference/research-iteration.md)：真实结果、用户决策、冻结 Task 授权和容器 Planner。
- [I 批实现导读](implementation/research-iteration.md)：状态存储、提交恢复、资源共享与 Planner 隔离。
