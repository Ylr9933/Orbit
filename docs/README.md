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
10. [资源管理、Docker 与 Ray 多节点](architecture/resource-management.md)：资源 YAML、宿主机实时观测、资源不足、Docker 限额、Ray 调度和集群认证方案。
11. [Tasks 建模与 benchmark 转换](architecture/task-model.md)、[Tasks API 与命令](reference/tasks.md)：完整目标与首批实现范围；任务契约、可见视图、草稿和索引导入已落地，自动工作流、工具运行与原生评测等价仍待接入。
12. [Agent 实现解读](implementation/agent-implementation-guide.md)、[Resources 实现解读](implementation/resource-implementation-guide.md)：沿当前源码理解公共对象、调用链、关键判断、失败路径和未实现边界。
13. [Records 模块详细设计](architecture/records-design.md)：原始证据、规范事件、产物与评测、宿主机/容器采集、存储查询，以及面向轨迹分析和 Agentic RL 的派生数据设计。
14. [Records API 与命令](reference/records.md)、[Records 实现解读](implementation/records-implementation-guide.md)：查看已实现的本地存储、Run 接入、轨迹派生、查询命令和当前限制。

`AGENTS.md` 与 `CLAUDE.md` 中的简表用于快速定位；具体归档示例与阅读导航在本文件维护。更新规则时同步两个根规则文件。

## 单节点执行

- [Web 科研控制台方案](architecture/web-console-design.md)：项目、任务、资源、Agent、运行与记录的页面规划，以及 HTTP 接入和分期验收。

- [Run / Environment 契约](architecture/run-environment-contract.md)：仅求解与隔离评测设计。
- [执行 API 与验证说明](reference/run-environment.md)：Python 组装、记录、安全边界及真实 Docker 测试。
