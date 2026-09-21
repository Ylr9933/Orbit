# 项目当前状态

Updated at: 2026-09-21T20:24:40+08:00

Basis: 以本文在 `main` 中的版本为集成依据；涵盖 A/B/C/D、H/E/I/W，以及 `c22fd80` 的模块整理与回归。
本文随用户授权的本次集成更新；具体合并与双远端同步事实以 Git 历史为准，不表示已配置常驻部署。
G1/G2 任务分支提出的更新仅在合并后成为集成事实；真实 CUDA 容器验收尚未完成。

当前定位：本机、单管理员、小型 CPU 科研工作流已可试用。
初始化、版本化规划、冻结 Task、容器执行、记录、分析和 Web 已有连接；GPU/原生 benchmark/多节点尚未验收。

## 阶段概览

| 阶段 | 状态 | 当前结论 |
| --- | --- | --- |
| S0：工程基础 | `accepted` | 锁文件、检查、依赖边界和协作规范建立，并有本机验证。 |
| S1：模块契约与任务样例 | `in_progress` | 核心契约已有实现；ToolBinding、稳定任务目录与原生 benchmark 等价性未完成。 |
| S2：完整单节点工作流 | `in_progress` | CPU 科研两条路径已有证据；GPU 与原生 benchmark 等价性仍缺。 |
| S3：两节点执行与故障处理 | `not_started` | Worker/Ray、节点加入、远程记录与故障恢复未实现。 |
| S4：Web 与批量评测 | `in_progress` | 科研项目、实验提交/取消、结果与分析已有页面；批量评测未实现。 |

## 已有能力与验证范围

- **A/B/C/D**：项目初始化、研究方案快照与精确确认、材料编译冻结，以及本机 Controller 的预检、幂等提交、取消和重启清理。
  真实 Codex CPU 统计实验已有 D 验收；业务可恢复不等于恢复训练进程。
- **H/E/I**：宿主机 CLI/MCP 控制长期 Docker 环境和 Job；Python CPU 环境准备、smoke、锁引用与有限修复；
  基于真实产物的分析、用户决定、有限 Task 授权和可替换 Planner。各批已有真实模型证据，适用范围见任务记录。
- **Agent/Tasks/Resources/Records**：三种 CLI Agent adapter、Task 可见视图、资源 YAML 与宿主机观测；本地原始流、事件、产物、轨迹与 JSONL 导出。
  Python 执行内核支持求解与隔离评测；正式 Controller 提交仍限 Codex 和无评测科研 Task。
- **G1/G2（合并后）**：GPU 只读诊断、限定单卡的 CUDA smoke 命令与 Controller UUID 白名单；冻结 Task 的 GPU 请求复用既有资源租约和 Docker 设备映射。当前主机缺 NVIDIA Container Toolkit，未通过真实 CUDA 容器验收。
- **W**：Web 兼容旧 catalog 和新工作区，支持初始化、研究方案查看、实验编译/预检/提交/取消、产物下载和分析展示。
- **模块整理**：修复 Web-first 启动权限、统一状态目录/研究运行上下文，以及事件/产物/轨迹可见性；拆分 Records 内部实现并保留兼容 API。
  `make verify` 通过（272 项非 E2E）；18 项无模型真实 Docker 集成、两套浏览器流程和独立 wheel 安装通过。
  包括真实 Web → Controller → Docker → Records → Analysis；浏览器执行后端是替身，模型能力沿用此前证据。

## 主要缺口

- **科研训练**：长期科研环境的 GPU 入口、CUDA/系统依赖模板、外部不可变数据与大权重传输；当前 HTTP 下载上限 16 MiB。G1/G2 真实 GPU 容器与训练验收仍缺。
- **执行与任务**：其他 provider 的完整容器链、ToolBinding、原生 benchmark 接入和评分等价、持久等待队列与训练 checkpoint 接续。
- **自动研究**：仅能在冻结 Task 授权集合内迭代；自动新任务授权和科学真实性判断未实现。
- **记录和界面**：平台外轨迹依赖显式导入，缺跨进程 spool/远端备份/token-logprob；Web 未覆盖 H/E/I 全部控制，HTTP/TypeScript 契约仍手工维护。
- **运维和扩展**：Web 资产需单独提供；单管理员服务未产品化为安装即用部署；无 Worker/Ray、多节点或多人在线权限。

## 下一步优先级

1. 确定长期状态目录，补齐安装诊断和启动/备份指南，用一个真实科研项目试用完整流程。
2. 围绕该项目补齐单 GPU 准入、训练镜像及大数据/权重入口，并在明确资源预算后验收。
3. 分阶段拆分 Run 内部执行逻辑，补 Web 长期 Job 操作和跨入口契约测试；具体拆分见[检查与计划](development/20260920-integration-review.md)。

## 项目级阻塞与限制

纯代码开发无外部阻塞。真实模型、GPU、两节点分别需要凭据与费用预算、获准设备与镜像、第二台节点和网络。当前主机还缺 NVIDIA Container Toolkit/Docker runtime，已有其他容器与 Controller 在运行；需安排安全维护窗口后验收 GPU。
本轮只完成只读 GPU 诊断和无 GPU 替身检查，没有真实 CUDA 容器或模型验收。HTTP 仅限本机管理员；托管 CI/分支保护尚需平台核实，License 尚未确定。

## 相关记录

- [本轮整理与验证](changes/20260920-integration-audit-r61c4e.md)、[代码检查与后续任务](development/20260920-integration-review.md)
- [G1/G2 GPU 诊断和准入](changes/20260921-gpu-diagnostics-admission-f1d9c6.md)、[单机 GPU 操作说明](operations/gpu-local.md)
- [D 本机执行](changes/20260918-local-run-controller-d73a91.md)、[H 宿主机科研](changes/20260920-host-research-mcp-a81f2c.md)
- [E 环境准备](changes/20260920-environment-preparation-e92b6a.md)、[I 分析迭代](changes/20260920-research-iteration-i73c9a.md)、[W Web](changes/20260920-web-workflow-w84d2a.md)
- [文档导航](README.md)、[使用入口](../README.md)、[Web 使用说明](operations/web-console.md)
