---
record_version: 1
task_id: "20260921-gpu-diagnostics-admission-f1d9c6"
title: "G1 容器 GPU 诊断与 G2 Controller GPU 准入"
branch: "feat/gpu-diagnostics-admission"
base_commit: "0e3c7f67feced88915e148d145ad7e9979713e84"
work_status: in_progress
updated_at: "2026-09-21T20:28:00+08:00"
pull_request: null
---

## Goal and acceptance

- G1：提供无副作用的主机/Docker GPU 诊断及明确指定设备、镜像的可选容器 CUDA smoke；失败时指出缺失的宿主机条件。
- G2：Controller 只授权管理员列出的真实 GPU UUID；冻结 Task 的 GPU 请求复用现有资源预检、租约、容器设备映射和清理；未授权或占用设备明确拒绝/等待。
- CPU 默认行为保持不变；相关单元、契约及可运行的本机检查通过。共享服务器上的 Docker/驱动配置和既有容器不能被本任务修改。

## Changes

- `resources/gpu.py` 负责 UUID 白名单，`bootstrap/gpu.py` 负责只读主机/Docker 诊断和限定资源的本地 CUDA smoke；CLI 提供 `resource gpu-doctor`、`resource gpu-smoke`。
- `controller serve --gpu-uuid` 将实际观测设备显式加入授权容量，未列出的设备不可分配；启动时拒绝缺失运行时。冻结 Task 使用既有预检/Lease/SandboxSpec/Docker UUID 映射。
- 新增测试，更新 GPU 操作说明、本机 Run 参考、首次科研试用说明及项目状态。

## Decisions

- 本机可观测 4 张 RTX 3090，但 Docker 只报告 runc，未发现 nvidia-ctk；其他项目容器正在运行。本轮不重启 Docker，不从 GPU 存在推断容器 CUDA 就绪。
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
| 真实 GPU 容器 CUDA smoke/冻结 Task | None | not_run | 宿主机缺 Toolkit/运行时；不重启共享 Docker 服务；尚无本地 CUDA/PyTorch 镜像验收 |

## Open items and blockers

- G1 的真实 CUDA 容器与 G2 冻结 Task 端到端验收受宿主机 Toolkit/Docker runtime 前置条件阻塞；现有 Controller 独占锁。代码与替身测试已完成，不能据此声称 GPU 真实运行通过。

## Next steps

- 由管理员在不影响现有容器的维护窗口配置 NVIDIA Container Toolkit，准备本地 CUDA/PyTorch + Codex 兼容镜像；按[GPU 操作说明](../operations/gpu-local.md)完成指定设备 smoke 和冻结 Task 真实验收，再更新本记录与项目状态。

## Compatibility and rollback

- GPU 授权默认关闭；新增显式 CLI 参数。回退分支代码即可；不迁移状态或改动宿主机服务。
