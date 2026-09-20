# 项目当前状态

Updated at: 2026-09-20T19:33:16+08:00

Basis: 以本文在 `main` 中的版本为集成状态依据；涵盖原基线 `f8f47f3`、A 批初始化 `c9f3498`、B 批研究规划 `39e97f0`、
C 批实验编译 `92d5209` 与 D 批本机 Controller `9363ee1`。本任务分支基于 I（3a03146），提出 H/E/I/W 合并后的概览；这四批尚未合并 main。
实际集成以 Git 历史为准，本地实现不代表远端同步或常驻部署。

当前结论：工程基础、核心模块首版、本机容器执行内核和简版 Web 已建立；现已补充本地科研项目初始化和研究规划的持久接口。
已形成小型 CPU 科研闭环：创建工作区、保存并采用方案、编译冻结 Task、提交容器内真实 Codex、
查询轨迹和下载指标。本分支新增宿主机 MCP → 长期环境 → 多轮 Job 路径，并通过真实 Codex CPU 实验；
E 批补充 Python CPU 环境生成与验证；I 批补充结果分析、用户决策、有限任务授权与可替换容器 Planner。GPU 与原生 benchmark 验收仍待完成。

## 阶段概览

| 阶段 | 状态 | 当前结论 |
| --- | --- | --- |
| S0：工程基础 | `accepted` | 工程、锁文件、检查、依赖边界、CI 配置和协作规范已建立，有本机验收证据。 |
| S1：模块契约与任务样例 | `in_progress` | 核心模块有首版契约；ToolBinding、稳定任务目录与原生 benchmark 等价性未完成。 |
| S2：完整单节点工作流 | `in_progress` | 小型 CPU 真实 Codex 执行闭环已验收；本分支长期 Job/MCP CPU 验收通过；GPU 与原生 benchmark 等价性尚未验收。 |
| S3：两节点执行与故障处理 | `not_started` | Ray backend、Worker 服务、节点加入、远程归档和故障恢复尚未实现。 |
| S4：Web 与批量评测 | `in_progress` | Web 接入工作区、已采用实验的提交/取消、产物与分析；批量评测未实现。 |

## 已有能力与验证范围

- **Projects（本次）**：`init` 支持指定路径、名称或自动目录；原始目标持久保存，生成科研目录和阅读入口。
  CLI 可预览、查询、幂等重试与恢复；SQLite 元数据有 revision 冲突检查。
  真实子进程中断/并发和独立安装验证见[本次记录](changes/20260918-project-init-72a94b.md)。
- **研究规划（本次）**：Brief/Plan/Experiment 快照、来源声明、版本差异、精确确认、只读检查与恢复上下文；
  支持受保护的 Markdown 投影、显式笔记导入和项目内研究 Skill。B05 实际交互证据见[研究规划记录](changes/20260918-research-planning-b6f2a1.md)。
- **实验编译（C 批）**：选定实验与材料生成独立 Task 包，支持内容摘要、历史关联、重复编译、缺项报告和移动后的项目重绑定。
  使用真实 Tasks 接口和独立 CLI/wheel 验证；维护结构与范围见[编译记录](changes/20260918-experiment-compilation-c42d8e.md)。
- **本机运行（D 批）**：Controller 与 CLI/HTTP 支持预检、幂等提交、查询、取消、事件/轨迹和受控 Artifact 下载；
  单活跃 Run、同账户主机互斥、持久意图与 Docker 重启对账。已有镜像固定 ID，账号副本独立清理。
  真实 Codex 生成并执行统计分析脚本、保存正确指标；取消和 CPU Docker SIGKILL 恢复均有证据，见[执行记录](changes/20260918-local-run-controller-d73a91.md)。
- **宿主机科研（H 批，本分支）**：项目绑定的 CLI/stdio MCP 可创建长期 Docker 环境、启动/停止 Job、读写工作区、查询日志和归档结果。
  与 D 共用资源准入；关闭 MCP 不停止 Job，重启 Controller 按中断清理策略恢复。平台调用及显式导入的宿主机原始流可追溯，覆盖缺口标记 partial。
  真实 Codex 两轮 CPU 训练、MCP 断连重连与后台停止通过，见[H 记录](changes/20260920-host-research-mcp-a81f2c.md)。
- **环境准备（E 批，本分支）**：项目关联的 intent/proposal/lock、Python CPU wheel 模板、独立 smoke、缓存、日志和预算内修复。
  CLI/MCP 共用 Controller 准入和清理；H 与 D 支持精确锁引用。真实 gpt-5.6-sol 从缺少 six 修复到可用环境，
  2 次 CLI、累计约 222 秒；模板/故障验证与范围见[E 记录](changes/20260920-environment-preparation-e92b6a.md)。
- **分析与迭代（I 批，本分支）**：真实 Run/Artifact/指标引用、不可变 Analysis、用户决策生成并采用新计划；
  冻结 Task 集合的持久次数/时间/资源授权，提交幂等与停止条件；容器 Planner 与实验共享总配额、状态外置。
  两个真实 gpt-5.6-sol Planner 会话接续两轮 Docker 统计脚本，累计约 111 秒；脚本执行适配器为确定性 fixture，
  非两次额外模型实验。能力边界与恢复验证见[I 记录](changes/20260920-research-iteration-i73c9a.md)。
- **Agent、Tasks、Resources**：Codex/Claude Code/DSH 适配、任务清单与可见性、benchmark 索引、资源 YAML、
  Linux/NVIDIA 监控和进程内 Lease；CLI 可诊断、准备任务和校验资源。
- **Run / Environment / Records**：Python 可组装单 Attempt 的求解、冻结提交、隔离评测、取消、清理和资源释放；
  保存原始流、事件、产物与反馈，可查询轨迹及导出 JSONL。执行内核和 Controller 的真实 CPU Docker E2E 使用 fixture；
  D07 另做真实 Codex 验收，两类证据分开，不等于 GPU 或原生 benchmark 验收。
- **Web（W 批，本分支）**：统一展示新工作区与旧 catalog，旧 ID/里程碑/关联保留并支持显式绑定；初始化与 CLI 共用服务。
  项目页展示研究方案、未知项、已采用实验与 I 分析；编译、预检、显式提交、取消和受控产物下载接入 D。
  真实浏览器验证包括丢失响应后的幂等重试、刷新恢复与私有过滤，执行后端为明确替身；未追加模型/Docker 验收。
- **工程**：`make verify` 覆盖格式、类型、依赖边界、文档、非 E2E 测试和 Python/Web 构建。
  操作方式见 [README](../README.md) 与[贡献指南](../CONTRIBUTING.md)；各次验证版本以任务记录为准。

## 主要缺口

- **研究入口**：已有证据分析和有限授权集合内迭代；自动生成新任务并判定其授权范围、科学真实性裁决仍缺。保存、确认和编译不会自行启动实验。
  大数据外部不可变存储适配尚缺。
- **执行范围**：D 批 Run 提交入口只接收编译的无评测科研 Task，容器认证只验收 Codex；
  H 批另支持已初始化项目直接开启 CPU 研究环境；
  其他 provider、直接 benchmark 注册、自动重试/队列和公网多用户服务未完成。
- **环境与资源**：已有受限 Python CPU 环境生成；任意 Dockerfile、系统包/GPU 模板、GPU 准入与分布式持久 Lease 尚缺；
  当前通过单控制进程和启动前清理恢复 CPU 容量，不支持恢复中断的模型会话或训练进程。
- **记录、任务与界面**：宿主机 Agent 仅支持平台操作记录和显式原始流导入，仍缺平台外全链路采集、跨进程 spool、ToolBinding 与原生 benchmark 评分等价证据；
  旧 Web Task 已有显式身份映射，无法解析的关联保留待处理；HTTP/TypeScript 契约仍手工维护。实时聊天、页面编辑研究方案和 H/E/I 生命周期控制暂未开放。
- **分布式**：尚无 Worker/Ray 实现及两节点验收。GPU 仅有观测和 Docker 参数，没有实际负载证据。

## 下一步优先级

1. 审查、集成 H/E/I/W 分支，按[宿主机科研指南](reference/host-research-mcp.md)试用并选择常驻 Controller 状态目录。
2. 用实际科研任务补齐所需镜像和材料入口；有授权后推进单 GPU 准入及训练验收。
3. 用真实科研工作区试用 Web 闭环，再按需求补齐大数据与长期任务操作；避免提前扩展复杂界面。

## 项目级阻塞与限制

本地初始化和后续纯代码开发无外部阻塞。真实 Agent、GPU、两节点验收分别需要可用模型凭据与费用预算、
获准 GPU 和镜像、第二台获准节点及网络。托管 CI、分支保护和 reviewer 权限需在 GitHub 核实。
本机 HTTP 不能直接当多人公网服务；wheel 仍需显式提供 Web 资产路径。License 尚未确定。

## 相关记录与说明

- [实验编译记录](changes/20260918-experiment-compilation-c42d8e.md)、[编译使用说明](reference/experiment-compilation.md)、[代码结构](implementation/project-workflow-code-guide.md)
- [本机运行记录](changes/20260918-local-run-controller-d73a91.md)、[运行命令](reference/local-run-controller.md)、[维护说明](implementation/local-run-controller.md)
- [研究规划记录](changes/20260918-research-planning-b6f2a1.md)、[使用说明](reference/research-planning.md)、[快照 ADR](adr/20260918-research-planning.md)
- [Project 初始化记录](changes/20260918-project-init-72a94b.md)、[命令参考](reference/projects.md)、[存储与恢复 ADR](adr/20260918-project-initialization.md)
- [初期检查和复盘](architecture/初期检查和复盘.md)、[0917 设计微调](architecture/0917设计微调.md)
- [执行内核与验证](reference/run-environment.md)、[Records 实现](implementation/records-implementation-guide.md)
- [W 任务记录](changes/20260920-web-workflow-w84d2a.md)、[科研界面设计与边界](architecture/web-research-workflow.md)
- [Web 实现记录](changes/20260916-web-console-3c7e91.md)、[Web 使用说明](operations/web-console.md)
