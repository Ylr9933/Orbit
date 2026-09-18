# 项目当前状态

Updated at: 2026-09-18T20:32:27+08:00

Basis: 以本文在本地 `main` 中的版本为集成状态依据；涵盖原基线 `f8f47f3`、A 批初始化 `c9f3498` 与 B 批研究规划 `39e97f0`。
开发分支上的本文是合并后的状态提案；实际集成以 Git 历史为准，本地合并不代表远端同步或部署。

当前结论：工程基础、核心模块首版、本机容器执行内核和简版 Web 已建立；现已补充本地科研项目初始化和研究规划的持久接口。
用户可以保存研究目标并创建工作区，并保存研究方案；正式 Run 提交入口与真实 Agent 实验仍未形成产品闭环。

## 阶段概览

| 阶段 | 状态 | 当前结论 |
| --- | --- | --- |
| S0：工程基础 | `accepted` | 工程、锁文件、检查、依赖边界、CI 配置和协作规范已建立，有本机验收证据。 |
| S1：模块契约与任务样例 | `in_progress` | 核心模块有首版契约；ToolBinding、稳定任务目录与原生 benchmark 等价性未完成。 |
| S2：完整单节点工作流 | `in_progress` | CPU Docker fixture 已验收；本次补充项目初始化与真实 Codex 规划验收，尚缺真实 Agent 实验与公开执行闭环。 |
| S3：两节点执行与故障处理 | `not_started` | Ray backend、Worker 服务、节点加入、远程归档和故障恢复尚未实现。 |
| S4：Web 与批量评测 | `in_progress` | 本机查询与项目整理可用；不能启动/取消 Run，批量评测未实现。 |

## 已有能力与验证范围

- **Projects（本次）**：`init` 支持指定路径、名称或自动目录；原始目标持久保存，生成科研目录和阅读入口。
  CLI 可预览、查询、幂等重试与恢复；SQLite 元数据有 revision 冲突检查。
  真实子进程中断/并发和独立安装验证见[本次记录](changes/20260918-project-init-72a94b.md)。
- **研究规划（本次）**：Brief/Plan/Experiment 快照、来源声明、版本差异、精确确认、只读检查与恢复上下文；
  支持受保护的 Markdown 投影、显式笔记导入和项目内研究 Skill。B05 实际交互证据见[研究规划记录](changes/20260918-research-planning-b6f2a1.md)。
- **Agent、Tasks、Resources**：Codex/Claude Code/DSH 适配、任务清单与可见性、benchmark 索引、资源 YAML、
  Linux/NVIDIA 监控和进程内 Lease；CLI 可诊断、准备任务和校验资源。
- **Run / Environment / Records**：Python 可组装单 Attempt 的求解、冻结提交、隔离评测、取消、清理和资源释放；
  保存原始流、事件、产物与反馈，可查询轨迹及导出 JSONL。7 个真实 CPU Docker E2E 曾通过，使用 fixture，
  未调用模型或 GPU，不等于原生 benchmark 验收。
- **Web**：本机 loopback 单管理员界面，可查看资源、维护轻量 Project/里程碑、关联已有 Task/Run、查询轨迹和 Agent 状态。
  新初始化工作区暂不接入旧 Web catalog。
- **工程**：`make verify` 覆盖格式、类型、依赖边界、文档、非 E2E 测试和 Python/Web 构建。
  操作方式见 [README](../README.md) 与[贡献指南](../CONTRIBUTING.md)；各次验证版本以任务记录为准。

## 主要缺口

- **研究入口**：Task 编译、结果关联和自动迭代尚未实现；保存或确认方案不会启动实验。
- **单机执行入口**：没有公开 submit/status/cancel/retry、后台 Controller 或 bootstrap 统一组装；
  Run 仍需调用者用 Python 配置，真实 Agent 镜像与凭据流程尚未验收。
- **环境与资源**：缺少长作业、Session、MCP、自动镜像构建、持久 Lease、队列与崩溃对账；
  监控和分配尚非同一服务，多控制进程不能安全共享分配状态。
- **记录、任务与界面**：缺少宿主机 Agent 全链路采集、跨进程 spool、ToolBinding 与原生 benchmark 评分等价证据；
  Web Task 关联仍依赖路径哈希，HTTP/TypeScript 契约手工维护。实时日志、Run 控制、受控下载和新 Project 适配待实现。
- **分布式**：尚无 Worker/Ray 实现及两节点验收。GPU 仅有观测和 Docker 参数，没有实际负载证据。

## 下一步优先级

1. 按[科研工作流细分计划](development/research-workflow-implementation-plan.md)推进 C01–C03：
   将保存的实验方案关联并编译成现有 Task，冻结材料和版本，明确执行缺项。
2. D 批补齐共享资源服务、执行入口、已有镜像和真实 Codex 单次实验验收。
3. H 批实现宿主机 MCP 科研作业，再推进环境自动构建和实验迭代；W01 统一适配新旧 Project。

## 项目级阻塞与限制

本地初始化和后续纯代码开发无外部阻塞。真实 Agent、GPU、两节点验收分别需要可用模型凭据与费用预算、
获准 GPU 和镜像、第二台获准节点及网络。托管 CI、分支保护和 reviewer 权限需在 GitHub 核实。
本机 HTTP 不能直接当多人公网服务；wheel 仍需显式提供 Web 资产路径。License 尚未确定。

## 相关记录与说明

- [研究规划记录](changes/20260918-research-planning-b6f2a1.md)、[使用说明](reference/research-planning.md)、[快照 ADR](adr/20260918-research-planning.md)
- [Project 初始化记录](changes/20260918-project-init-72a94b.md)、[命令参考](reference/projects.md)、[存储与恢复 ADR](adr/20260918-project-initialization.md)
- [初期检查和复盘](architecture/初期检查和复盘.md)、[0917 设计微调](architecture/0917设计微调.md)
- [执行内核与验证](reference/run-environment.md)、[Records 实现](implementation/records-implementation-guide.md)
- [Web 实现记录](changes/20260916-web-console-3c7e91.md)、[Web 使用说明](operations/web-console.md)
