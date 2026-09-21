---
record_version: 1
task_id: "20260921-gpu-diagnostics-admission-f1d9c6"
title: "G1 容器 GPU 诊断与 G2 Controller GPU 准入"
branch: "ops/gpu-host-enablement"
base_commit: "0e3c7f67feced88915e148d145ad7e9979713e84"
work_status: in_progress
updated_at: "2026-09-21T21:11:56+08:00"
pull_request: null
---

## Goal and acceptance

- G1：提供无副作用的主机/Docker GPU 诊断及明确指定设备、镜像的可选容器 CUDA smoke；失败时指出缺失的宿主机条件。
- G2：Controller 只授权管理员列出的真实 GPU UUID；冻结 Task 的 GPU 请求复用现有资源预检、租约、容器设备映射和清理；未授权或占用设备明确拒绝/等待。
- CPU 默认行为保持不变；相关单元、契约及可运行的本机检查通过。用户随后明确授权安装宿主机 Toolkit 和真实 GPU 验收；不停止或清理既有容器，不改 GPU 驱动。

## Changes

- `resources/gpu.py` 负责 UUID 白名单，`bootstrap/gpu.py` 负责只读主机/Docker 诊断和限定资源的本地 CUDA smoke；CLI 提供 `resource gpu-doctor`、`resource gpu-smoke`。
- `controller serve --gpu-uuid` 将实际观测设备显式加入授权容量，未列出的设备不可分配；启动时拒绝缺失运行时。冻结 Task 使用既有预检/Lease/SandboxSpec/Docker UUID 映射。
- 宿主机安装 NVIDIA Container Toolkit 1.20.1、注册 Docker runtime，并通过 `systemctl reload docker` 生效。Docker 29 在本机对 `--gpus` 报 `AMD CDI spec not found`；后续代码优先使用 CDI `--device nvidia.com/gpu=UUID`，核对实际 DeviceRequests，旧环境保留 `--gpus` 路径。自检改为内置 CUDA Driver API 的短计算，可复用本地 Python 镜像。
- 新增测试，更新 GPU 操作说明、本机 Run 参考、首次科研试用说明及项目状态。

## Decisions

- 初始本机可观测 4 张 RTX 3090，但 Docker 只报告 runc，未发现 nvidia-ctk。用户后续授权安装；Docker 的 `live-restore=false` 且 4 个现有容器在运行，因此用官方支持的 Docker 动态配置重载，避免直接重启。重载后 4 个容器仍在运行。
- 复用 `LocalResourceManager` 和 `SandboxSpec.gpu_device_ids`，不新增调度器；管理员以 UUID 明确授权，未传入时 GPU 容量为空。
- 长期科研环境的 GPU 请求属于后续 G3，本轮只完成冻结 Task 的 G2 准入和底层链路。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `nvidia-smi`、`docker ps`、Docker runtime/Toolkit 只读检查 | 起始工作区 + 本机 | passed | 4 张 GPU；Docker 仅 runc；共享容器在运行 |
| `uv run --locked pytest -q tests/unit/resources/test_gpu.py tests/unit/resources/test_local.py tests/unit/runs/test_service.py tests/unit/test_cli.py` | 本任务分支 20:22 工作区 | passed | 38 项，含白名单、缺卡/占用、冻结 Task 设备传递；Docker 为替身 |
| `make verify` | 本任务分支 20:24 工作区 | passed | 306 项非集成/E2E 测试；lint、mypy、依赖边界、文档链接、包和 Web 构建通过 |
| `uv run --locked agent-infra resource gpu-doctor` | 本机 2026-09-21 | passed | 如预期返回 `ready=false`/退出码 1，4 张 RTX 3090，但缺 nvidia-ctk 与 Docker nvidia runtime |
| `uv run --locked agent-infra resource gpu-smoke --gpu-uuid GPU-5f0e3501-fdf7-9b81-5743-aab70102b71e --image local:cuda-test` | 本机 2026-09-21 | passed | 如预期 `smoke=not_run`/退出码 1；前置诊断失败，没有 inspect、拉镜像或启动容器；镜像名仅用于确认门禁 |
| Controller GPU 启动探测 | 本机 2026-09-21 | not_run | 现有 Controller 持有主机锁，第二个实例报 `Errno 11`；未停止共享服务 |
| 初始真实 GPU 容器 smoke | 初始本机快照 | not_run | 当时宿主机缺 Toolkit/运行时；下方记录后续用户授权安装后的验收 |
| `apt-get install` Toolkit 1.20.1、`nvidia-ctk runtime configure --runtime=docker`、`systemctl reload docker` | 本机 Ubuntu 22.04，2026-09-21 | passed | `nvidia` runtime 已注册；Docker 原有 4 个容器保持运行；原配置备份在 `/etc/docker/daemon.json.agent-infra-gpu-backup-20260921` |
| `docker run --device nvidia.com/gpu=GPU-5f0e... --entrypoint nvidia-smi ...` | 本机 Docker 29.8.0 | passed | 容器仅见指定 UUID 的 RTX 3090；相同镜像 `--gpus` 报 `AMD CDI spec not found` |
| `docker run --device nvidia.com/gpu=GPU-5f0e... --entrypoint python ... cuda_probe.py` | 本机 Docker 29.8.0 | passed | CUDA Driver API 内核算出 `1.25 + 2.5 = 3.75`；1 CPU/2 GiB、无网络，容器自动删除 |
| `uv run --locked agent-infra resource gpu-smoke --gpu-uuid GPU-5f0e... --image agent-infra/codex-research:0.154.0` | 当前叠加任务分支工作区 + 本机 | passed | `ready=true`、`smoke=passed`，镜像固定 ID、指定卡 CUDA 计算成功 |
| `uv run --locked python - <<'PY'` 使用 `DockerEnvironment(gpu_mode='cdi')`、`SandboxSpec` 指定 GPU 与 `cuda_probe.py` | 当前叠加任务分支工作区 + 本机 | passed | 真实 backend `exited/0`、CUDA 结果 3.75、`cleanup_complete=True`；不涉及模型/完整冻结 Task |
| `make verify` | 当前叠加任务分支 21:11 工作区 | passed | 306 项非集成/E2E 测试；lint、mypy、依赖边界、文档链接、包和 Web 构建通过；不代替真实模型验收 |

## Open items and blockers

- G1 的真实 CUDA 容器与 G2 的 DockerEnvironment 基础链已通过；完整冻结 Task + Codex GPU Run、训练镜像和真实训练结果仍未验收。现有 Controller 独占主机锁，未中断它以启动 GPU 版 Controller。

## Next steps

- 完成代码全量检查；在适当窗口重启现有 Controller 并用 `--gpu-uuid` 授权，准备 CUDA/PyTorch + Codex 兼容镜像，执行冻结 Task 的完整 GPU Run 验收。长期科研环境 GPU 入口属于后续 G3。

## Compatibility and rollback

- GPU 授权默认关闭；新增显式 CLI 参数，CDI 与旧版 `--gpus` 保持兼容。宿主机已安装软件包和软件源并修改 Docker daemon 配置；如需回退，在确认运行任务影响后恢复上述备份并重载 Docker。没有迁移项目状态或修改 GPU 驱动。
