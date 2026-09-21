# 当前功能与首次科研任务试用

状态：基于 main `c4b4bb7`（Agent Infra 0.1.0），2026-09-21 整理。
本文记录功能说明和首次手动试用步骤；不代表已经替用户启动服务、调用模型或执行训练。
总体状态见[项目概览](../project-status.md)，本次整理见[任务记录](../changes/20260921-research-trial-gpu-b51d7e.md)。

## 1. 当前能完成什么

当前可试用本机、单管理员、小型 CPU 科研流程：创建项目、讨论并保存研究方案、运行 Docker 实验、记录与分析结果，再开展下一轮。

| 功能 | 当前能力 |
| --- | --- |
| 项目初始化 | 根据研究目标建立工作区，生成 docs、code、configs、data、runs、artifacts |
| 研究规划 | Agent 与用户讨论背景和方法；保存版本、用户修改、采用决定；新会话恢复上下文 |
| Task | 把选定实验、材料、资源和输出约定编译为冻结任务 |
| 宿主机 Agent 控制 Docker | CLI/MCP 创建长期环境、写代码、启动后台 Job、看日志、多轮实验和归档 |
| 容器内 Agent 执行 | 冻结任务交给容器内 Codex；支持预检、提交、取消和结果收集 |
| 环境准备 | 受限 Python CPU 依赖提案、构建、独立 smoke、环境锁与预算内修复 |
| 资源管理 | 观测 CPU/内存/GPU；当前产品入口分配 CPU/内存并施加 Docker 限额 |
| Records | 保存平台操作、命令日志、原始流、产物和统一轨迹；宿主机完整原始流需显式导入 |
| 分析与迭代 | 引用实际 Run/Artifact 指标保存分析；在预先授权的冻结 Task 集合内迭代 |
| Web | 查看资源、项目、方案、运行和结果；编译、预检、提交、取消实验 |

GPU 产品入口、Ray 多节点、任意 benchmark 刷榜、大数据自动挂载尚未打通。
Claude Code/DSH 有适配器，但正式容器提交链目前只开放 Codex。
Web 尚未覆盖全部长期 Job、环境准备和 Planner 控制。

上一轮对本服务器的只读检查确认：仓库 venv CLI、Docker 和 Web 构建文件可用，Codex 已登录，
本地存在 `python:3.12-slim` 与 `agent-infra/codex-research:0.154.0`；当时未检测到运行中的 Controller/Web。
这是当时的检查结果，不保证下一次操作时安装、账号和进程状态不变。可重新检查：

```bash
cd /disk/disk_20T/wangxuehai/infra
.venv/bin/agent-infra --version
.venv/bin/agent-infra agent doctor codex
docker version
docker image ls
```

其他服务器先按[贡献指南](../../CONTRIBUTING.md)安装依赖；Web 资产缺失时在仓库根目录执行 `pnpm build`。

## 2. 首次建议走宿主机 Agent + MCP + Docker

用户可以选择实验在**宿主机**还是 **Docker** 中运行。轻量计算、已有依赖和快速查看结果可选宿主机；
需要隔离依赖、后台任务管理或验证平台执行链路时选 Docker。Agent 可以建议，但不能仅因任务简单就自行换模式。
首次执行前确认一次即可；已有明确指令或已采用方案时沿用，不反复询问。
选择写入研究方案现有 `brief.constraints` 文本并随版本保存；目前这是协作约定，不是新增的运行后端参数。

| 用户选择 | 当前怎么执行 | 结果边界 |
| --- | --- | --- |
| 宿主机 | Agent 在用户允许的本机环境运行脚本 | 可保存项目文件；尚无自动平台 Run、容器隔离或完整 Records 采集 |
| Docker | Agent 通过 MCP/CLI 调用 Controller | 平台保存 Run/Job、日志、归档和资源释放事实 |

这份首次试用流程要验证 Docker 与 Records，所以以下步骤选择 Docker。用户若只做本地计算，可跳过 Controller/MCP/Web 执行步骤，
按其选定范围运行并标明外部本机结果；不能将它报告为平台容器验收。

这条路径接近日常科研交互，方便中途修订实验：

```text
研究目标 → Project → 讨论与保存方案 → 用户采用
    → 宿主机 Codex → 项目 MCP → Controller → Docker Job
    → 日志/产物 → Records → 分析 → 下一轮建议
```

第一次可比较两个学习率对线性回归收敛速度和误差的影响，使用固定种子的合成数据和 Python 标准库。
换成自己的真实任务时，先选 CPU 能完成、数据量小、结果能人工核验的实验。
示例目录可以替换，但所有入口必须使用同一个状态根；研究工作区放在 infra 代码仓库外。

### 2.1 初始化工作区

```bash
cd /disk/disk_20T/wangxuehai/infra
source .venv/bin/activate
export AGENT_INFRA_STATE_DIR=/disk/disk_20T/wangxuehai/infra-state-personal

mkdir -p /disk/disk_20T/wangxuehai/research
agent-infra init /disk/disk_20T/wangxuehai/research/first-study \
  --name "第一次科研试用" \
  --goal "比较两个学习率对线性回归收敛速度和最终误差的影响"

agent-infra project research skill \
  /disk/disk_20T/wangxuehai/research/first-study --install
```

保存返回的 `project_id`。目标目录应尚不存在；后续会话使用已创建项目，不重复 init。
`--install` 只把科研 Skill 安装到该项目。初始化和安装 Skill 不会调用模型或启动 Docker。

### 2.2 启动 Controller

另开服务器终端，保持运行，也可放在 tmux 中：

```bash
/disk/disk_20T/wangxuehai/infra/.venv/bin/agent-infra controller serve \
  --state-dir /disk/disk_20T/wangxuehai/infra-state-personal \
  --cpu 1 --memory-gib 2 --port 8766
```

参数是管理员允许平台分配的总容量。当前同一 OS 用户不能同时启动第二个 Controller；资源不足明确拒绝，不自动扩容。
关闭 Codex/MCP 不停止后台 Job；关闭 Controller 会取消并清理执行中的环境。

### 2.3 接入 Codex MCP

在服务器执行，将 `PROJECT_ID` 替换为初始化返回的 ID：

```bash
codex mcp add infra-first-study -- \
  /disk/disk_20T/wangxuehai/infra/.venv/bin/agent-infra mcp \
  --state-dir /disk/disk_20T/wangxuehai/infra-state-personal \
  --project-id PROJECT_ID \
  --session-id first-study-session
```

这会新增 Codex MCP 配置；服务器名称应选未使用的名称。这条连接固定绑定该项目，不能在工具参数中切换到其他项目。
进入工作区开启新会话，用 `/mcp` 查看连接，并按客户端提示批准所需工具。
配置方式见 [Codex 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp)。

```bash
cd /disk/disk_20T/wangxuehai/research/first-study
export PATH="/disk/disk_20T/wangxuehai/infra/.venv/bin:$PATH"
export AGENT_INFRA_STATE_DIR=/disk/disk_20T/wangxuehai/infra-state-personal
codex --model gpt-5.6-sol
```

模型需要当前账号可访问。新会话可使用新的 session ID，重连同一次会话可沿用原 ID；不要将登录令牌当 session ID。

### 2.4 先讨论，再执行

第一段提示词只做规划：

> 使用 `$agent-infra-research`，读取当前项目上下文。我的目标是比较两个学习率对线性回归收敛速度和最终误差的影响。
> 使用固定随机种子的合成数据，只比较两个学习率，最多 1 CPU、2 GiB，不使用 GPU。
> 这次选择 Docker 执行，目的是同时验证平台链路；请把这个选择写入研究方案。
> 先完善研究背景、问题、方法、指标和输出约定，通过项目 CLI 保存方案。
> 遇到影响实验的重要未知项向我询问。现在只做规划，等我确认后再执行。

查看方案并实际纠正一次，例如“两个方法必须使用相同初始化和数据”，让 Agent 保存修订。
满意后再发送：

> 我采用你刚保存的这一版方案，请记录对应版本的确认。
> 这次同时验收 Agent Infra 执行链路。先读取绑定项目的 project_context，确认项目正确。
> 使用 `infra-first-study` MCP，在 `python:3.12-slim` 环境中执行两个实验；仅使用 Python 标准库，容器不联网。
> 申请最多 1 CPU、2 GiB，每个 Job 最多运行 120 秒；实验程序在 Docker 内执行。
> 通过 environment_open 取得 run_id，通过 workspace_write 放入代码和必要输入，再调用 job_start 取得 job_id。
> 平台操作失败时报告实际错误；可以用等价 agent-infra CLI，但不要直接在宿主机运行训练脚本，也不要绕过平台手动 docker run。
> 两组实验分别保存参数、随机种子、损失曲线 CSV、指标 JSON 和分析报告，避免相互覆盖。
> 读取实际结果并归档，结束环境后检查清理、归档和资源释放状态；再用 `analysis_save` 保存引用实际产物的分析。
> 完成后停止，后续实验先向我提出建议。

规划 Skill 是协作说明，不是宿主机执行沙箱；即使安装 Skill，Agent 仍可能选错执行方式。
看到代码和本地结果文件，并不证明平台运行成功。执行开始应有平台返回的 run_id/job_id，结束应有 Records 产物。
仅自行写出 `run_manifest.json` 不能代替这些证据。

120 秒是实验 Job 的时限，不是 Codex 会话的费用/模型调用硬上限。模型会话按自己批准的预算使用。
若需要 NumPy 等依赖，先让 Agent 通过环境准备工具生成并验证 Python CPU 环境，再使用环境锁；基础 Python 镜像没有这些包。
详见[环境准备指南](../reference/environment-preparation.md)。

### 2.5 打开 Web 看结果

第三个终端执行：

```bash
cd /disk/disk_20T/wangxuehai/infra
.venv/bin/agent-infra web \
  --state-dir /disk/disk_20T/wangxuehai/infra-state-personal \
  --console-dir /disk/disk_20T/wangxuehai/infra-state-personal/console \
  --port 8765
```

从自己电脑访问服务器时，先在电脑终端建立转发：

```bash
ssh -N -L 8765:127.0.0.1:8765 wangxuehai@服务器地址
```

用浏览器打开 Web 服务打印的完整访问链接。页面能查看方案、运行关联、产物和分析。
长期环境及 Job 的启动/停止仍主要通过 MCP/CLI；关闭网页不会停止训练。

## 3. 怎样判断这一轮真的跑通

- 原始目标、方案和用户纠正都能通过项目上下文恢复。
- 实验实际在 Docker 中执行，遵守 CPU、内存与 Job 时限。
- 两组实验各有参数、日志和真实指标，分析引用对应 Run/Artifact。
- 环境关闭后，确认 `cleanup_complete`、`lease_released`、`archive_complete`；不能只看请求成功。
- 容器清理后，仍能从 Records/Web 查看或下载产物。
- 新开 Codex 会话后，能从项目上下文和历史分析接续，而非依赖上一次聊天。

项目目录不会整体自动同步到 Docker，容器产物也不会自动全部回填宿主机项目的 artifacts 目录。
目前使用 MCP 文件接口传入小文件，通过 Records 查看/下载输出；不要假定宿主机 data 下的文件已在容器内。
宿主机 Agent 的平台外操作不会自动完整采集；需显式导入选定的原生轨迹文件。
详细限额、取消和恢复见[宿主机科研指南](../reference/host-research-mcp.md)。

### 如果 Agent 已经在宿主机执行了实验

先保留已有代码和结果，明确标记为外部本机执行。查看平台：

```bash
/disk/disk_20T/wangxuehai/infra/.venv/bin/agent-infra run list \
  --project-id PROJECT_ID \
  --state-dir /disk/disk_20T/wangxuehai/infra-state-personal
```

若没有该次 Run，不能把这次实验算作 Docker/Records 验收。服务和 MCP 都在线只证明可连接，不能证明 Agent 使用过执行工具。
让 Agent 重新读取本项目 Skill，并明确要求复用已确认的方法，通过上述 platform tools 重跑；使用新 Run，保留原本机结果，
取得真实归档后再创建 Analysis。重跑需要用户实际认可的资源和时间范围。

Skill 安装是文件副本，更新仓库不会自动更新已有项目。安装命令遇到不同内容会保护性报冲突，不能为了升级覆盖用户修改。
应先对比旧副本，备份后仅更新确认未自定义的文件；已打开的 Agent 会话需要显式重新读取它们。

### 不用 Docker，能否完整记录？

Records 不依赖 Docker。执行隔离和证据采集是两件事；决定记录完整性的关键是平台是否参与了执行和采集。

| 模式 | 当前状态 | 可以依赖的记录 |
| --- | --- | --- |
| Agent 直接运行宿主机脚本 | 可由用户选择；属于平台外执行 | 用户/Agent 实际保存的代码、数据、指标和报告；不自动产生平台 Run/Job |
| 平台管理的宿主机执行 | **尚未实现，后续建议** | 目标是共用 Records，管理 Run/Job、进程、日志、输入版本和产物；没有容器级隔离 |
| Controller 管理 Docker 执行 | 已实现 | 平台操作、Run/Job、进程日志及所归档产物；原生 Agent 轨迹依执行路径与提供方采集能力而定 |

平台管理的宿主机模式应在启动前创建 Run，记录参数、工作目录、环境/代码/数据版本；执行中采集 stdout/stderr、
状态和资源观测；结束时收集指标、指定产物与进程清理结果。它应复用现有 Records，而不是另建一套本机日志格式。
文件采集范围必须明确，不能声称自动记录宿主机上的所有文件变化或所有外部操作。

Agent 轨迹是另外一层：平台操作可直接记录，Agent 的消息和工具事件需从原生会话流采集、保留原文并规范化。
当前宿主机原始流导入绑定已有研究 Run，不是给任意本机脚本自动补建 Run 的入口。
只有本地报告时，应保留为外部证据，不能为了通过 analysis-save 的校验伪造 Run/Artifact。

即使平台管理执行，也要标记截断、崩溃窗口、平台外调用和提供方未输出的字段。
CLI 通常没有 token/logprob；这些缺失不能补造。Docker 的使用本身也不保证宿主机 Agent 的全部活动被采集。
后续可以先实现不带 Docker 的受控命令执行与 Records 接入，再增强原生会话采集；这不需要 Ray。

若要先测试“容器内 Codex 自主执行”的另一条路径，按[CPU 统计实验](../../examples/research/cpu-statistics/README.md)
执行保存/确认方案、编译 Task、预检、提交和读取产物的流程；本机已有示例镜像时可复用，无需重复构建。

### 使用 Docker，实验数据保存在哪里？

当前 H 路径（宿主机 Agent 控制长期科研环境）把宿主机的 Run 工作区绑定到容器 `/workspace`。
容器写入此目录就是写入宿主机；删除容器不会删除绑定的工作区。项目源码目录不会自动挂载进去，
两者也没有自动双向同步。下面是以本指南 state-dir 为根的实际存储布局；目录按需创建：

```text
infra-state-personal/controller/
├── workspaces/<run_id>/       # H 路径：容器 /workspace 对应的宿主机目录
├── job-logs/<job_id>          # H 路径：采集到的 Job 合并输出
├── archives/<archive_id>/     # H 路径：关闭环境时复制的工作区快照
└── records/
    ├── records.sqlite3       # Run、Attempt、事件、流和产物索引
    ├── blobs/sha256/          # 按内容摘要保存的文件、日志、原始数据
    └── spool/                # 尚在采集的流数据
```

训练脚本应明确把需要保留的结果写到 `/workspace` 下，例如 `outputs/metrics.json`、
`outputs/figures/`、`outputs/checkpoints/`；这些是建议约定，不是自动创建的目录。
程序必须主动写出指标和 checkpoint，平台不能从内存里自动恢复它们。`/tmp` 和其他未挂载路径
不属于工作区归档范围。Job 会采集标准输出/错误（H 路径合并为一条流），但不会自动把每个
子进程的内部操作还原成独立工具事件；宿主机 Agent 原生会话仍需单独导入。

正常关闭时，平台停止 Job、确认容器清理，再复制宿主机工作区并写入 Records。
检查 `cleanup_complete`、`lease_released` 和 `archive_complete`，不能只看进程退出码。
归档失败时返回 `archive_failed`，工作区保留在 state-dir 中；保留文件不等于已完成 Records 归档。
冻结 Task 的 D 路径采用另一套工作目录，只收集 Task 输出约定指定的提交路径，同样持久保存到 Records。

当前实现适合小实验：工作区/提交收集默认限制为 **1 GiB**，H 单 Job 日志捕获上限为 **8 MiB**，
在线文件读取/HTTP 产物下载还有 **16 MiB** 限制。大输入也会计入 H 的整工作区归档，
并产生工作区、快照和 Records 的存储开销。因此大型数据集与模型权重还需要补充独立数据存储、
只读挂载、流式上传/下载与 checkpoint 管理，不能把现有归档当成已完成的大规模训练存储方案。

宿主机持久化不等于备份。应保留并备份项目目录与整个 state-dir（包括数据库和 blob 文件）；
运行中备份需要一致性方案，不能只复制 SQLite 主文件或只备份项目的 `docs/`。
当前没有自动异地备份。不要把实验数据、认证材料或 state-dir 提交到 Git。

实现入口：[H 执行和归档](../../src/agent_infra/runs/research.py)、
[容器挂载和提交收集](../../src/agent_infra/environments/docker.py)、
[本地 Records](../../src/agent_infra/records/local.py)。本节来自源码核对，未新增 Docker 实验。

## 4. GPU：代码可用与平台接通是两回事

理解可以分为四层：

1. **主机条件**：GPU 驱动可用，Docker 已配置 NVIDIA Container Toolkit。
2. **平台分配**：选择被管理员允许使用的 GPU，核查占用，将确切设备传给容器，记录分配并在清理后释放。
3. **容器依赖**：镜像有 CUDA 可用的训练框架和匹配的运行库；普通 Python/CPU-only PyTorch 镜像不够。
4. **训练代码**：Codex 编写的程序将模型、数据和运算放到 GPU 上。

所以“真正运算看代码是否使用 GPU”是对的，但它以前三层已打通为前提。
Codex 作为使用远程模型的 Agent，通常不需要自己占用本机 GPU；需要 GPU 的是它启动的训练进程。

### 4.1 当前代码已经有的基础

| 文件 | 实际能力 |
| --- | --- |
| [resources/monitor.py](../../src/agent_infra/resources/monitor.py) | 通过 nvidia-smi 观测 UUID、显存、利用率和计算进程数量 |
| [resources/api.py](../../src/agent_infra/resources/api.py)、[local.py](../../src/agent_infra/resources/local.py) | GPU 请求/授权容量/Lease；从授权设备中筛选、排除已有 Lease 与观测到的外部占用 |
| [environments/api.py](../../src/agent_infra/environments/api.py) | SandboxSpec 的 gpu_device_ids |
| [environments/docker.py](../../src/agent_infra/environments/docker.py) | 将设备传给 Docker --gpus，并检查 DeviceRequests 与 Lease 设备一致 |
| [runs/service.py](../../src/agent_infra/runs/service.py) | 编译任务执行内核将 lease.gpu_device_ids 传给求解/评测环境 |

缺口主要在接入与真实验收：

- G1/G2 任务分支已加入 `resource gpu-doctor`、`resource gpu-smoke` 和 Controller `--gpu-uuid` 授权入口；未授权时 GPU 容量仍为空。当前服务器缺 NVIDIA Container Toolkit/Docker runtime，真实容器 GPU 链路未通过。具体操作见[单机 GPU 说明](gpu-local.md)。
- [runs/research.py](../../src/agent_infra/runs/research.py) 的 `_open` 只创建 CPU/内存请求，SandboxSpec 未传 GPU；[MCP environment_open](../../src/agent_infra/gateways/mcp/research.py) 也没有 GPU 参数。
- E 环境准备针对 CPU wheel，尚无 CUDA 训练环境验证；不存在本项目真实 GPU 训练与清理验收证据。

之前的实现先验证 CPU 工作流、认证、隔离、记录和故障恢复，并非 Docker 不能使用 GPU，也不需要等 Ray。
资源模块已有初步设备选择逻辑，接下来应复用它，补产品入口与真实测试，而不是另建一套 GPU 调度器。

### 4.2 Docker 原理与平台入口

NVIDIA 官方支持以 `--gpus device=GPU-UUID` 指定容器设备，前提是驱动和容器运行时配置正确。
下面仅展示 Docker 层的原理；平台已实现的诊断与授权命令见[单机 GPU 说明](gpu-local.md)。设备 UUID 与镜像必须替换为经授权的实际值：

```bash
docker run --rm \
  --gpus device=GPU-REPLACE_WITH_APPROVED_UUID \
  --cpus 2 --memory 8g \
  YOUR_EXISTING_CUDA_PYTORCH_IMAGE \
  python -c 'import torch; assert torch.cuda.is_available(); x=torch.randn(64,64,device="cuda"); y=x@x; torch.cuda.synchronize(); print(y.device)'
```

这里直接运行 Docker 不会自动纳入本平台的 Project、Lease 和 Records。G2 冻结 Task 已接通平台入口，但真实 CUDA 容器验收仍待宿主机运行时配置。
资料：[NVIDIA Toolkit 安装](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)、
[设备选择](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html)。

CUDA 环境正确后，训练代码还要实际使用 GPU，例如：

```python
import torch

assert torch.cuda.is_available(), "本实验要求 GPU，不能静默降级为 CPU"
device = torch.device("cuda:0")  # 当前容器可见设备中的序号
model = torch.nn.Linear(16, 1).to(device)
x = torch.randn(32, 16, device=device)
loss = model(x).square().mean()
loss.backward()
torch.cuda.synchronize()
print(next(model.parameters()).device, loss.item())
```

`is_available()` 只是条件检查；应同时验证 GPU 张量计算/反向传播和设备记录。
模型、输入及相关张量需要放到相容设备，见 [PyTorch CUDA 语义](https://docs.pytorch.org/docs/main/notes/cuda.html)。

设备可见性不是显存硬配额：Docker 的 `--memory` 约束容器主机内存，不是 GPU 显存。
现有请求里的 `min_memory` 是筛选设备和当前可用显存的下限，不表示“最多只能使用这些显存”。
第一版适合授权范围内整卡分配；平台 Lease 只能约束本平台，不能阻止外部用户另起 GPU 进程。

### 4.3 实用的下一步

只做单机、指定设备、已有 CUDA/PyTorch 镜像即可开始，不必同时开发 Ray、MIG 或多卡分布式训练：

1. G1/G2 任务分支已实现 Controller UUID 允许列表、诊断命令和冻结 Task 准入；仍需在配置好 Toolkit 的主机验证真实 CUDA 容器及任务。
2. G3 待实现 CLI/MCP 长期环境 GPU 请求，将 Lease 中的设备传入 SandboxSpec。
3. 先复用已准备的训练镜像，做可见设备检查、CUDA 张量运算与一次短训练，记录 GPU UUID、镜像、框架/运行库版本和实际指标。
4. 验证取消、异常及 Controller 重启后的容器清理和资源释放；清理未确认时不重新分配设备。
5. 再补环境模板自动构建和 Web 参数输入。

本次未修改 Docker/驱动配置，也未在这台主机运行真实 GPU 容器。
