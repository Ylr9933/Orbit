# 单机 GPU 诊断与冻结 Task 准入

状态：G1/G2 叠加任务分支已在本机完成指定设备的真实 CUDA 计算和 DockerEnvironment 清理验收；冻结 Task + Codex 的完整 GPU Run 尚未验收。本文只适用于单机、管理员明确授权的整张 NVIDIA GPU。长期科研 Job 的 GPU 参数属于 G3。

先只读检查主机与 Docker：

```bash
agent-infra resource gpu-doctor
```

输出列出观测到的 GPU UUID、NVIDIA Container Toolkit、Docker runtime、CDI 设备和缺失条件；`ready=false` 时退出码为 1。GPU 在 `nvidia-smi` 中可见，不代表 Docker 已能使用。本机 Ubuntu 22.04 已安装 Toolkit 1.20.1，使用配置重载后保留了原有 4 个容器；Docker 29 的 `--gpus` 在本机报 `AMD CDI spec not found`，因此本项目优先使用已验证的 NVIDIA CDI UUID 设备映射。若主机只有旧版 runtime，可回退到 `--gpus`。参考 [NVIDIA 安装说明](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)及 [Docker runtime 热重载说明](https://docs.docker.com/reference/cli/dockerd/)。本命令不安装软件或修改 daemon。

准备一个**已经在本机存在**、含 Python 的可信镜像后，选一张获准且空闲的 GPU 运行有上限的自检：

```bash
agent-infra resource gpu-smoke --gpu-uuid GPU-REPLACE_WITH_APPROVED_UUID --image LOCAL_PYTHON_IMAGE
```

该命令不拉取镜像，在单个新容器内限制为 1 CPU、2 GiB 主机内存、无网络、90 秒，并通过 CUDA Driver API 在 GPU 上计算 `1.25 + 2.5 = 3.75`；无需在测试镜像内安装 PyTorch。它只清理本次创建的容器。输出包含设备 UUID、固定镜像 ID 和结果。它是环境诊断，不创建 Project、Run、Lease 或 Records；真实训练任务仍需相应框架的 CUDA 版镜像并单独验收。GPU 显存不是 Docker `--memory` 的硬配额，测试前须确认主机无其他使用者并保留足够空闲显存。

通过自检后，管理员在 Controller 启动时明确授权 UUID：

```bash
agent-infra controller serve --state-dir /absolute/state --cpu 2 --memory-gib 8 \
  --gpu-uuid GPU-REPLACE_WITH_APPROVED_UUID --port 8766
```

可重复 `--gpu-uuid` 授权多张卡。不指定时容量仍为零；UUID 重复、不存在、或 Docker GPU 运行条件未就绪会拒绝启动。已编译冻结 Task 的 `resources.yaml` 可申请一张授权卡，例如：

```yaml
version: 1
request_id: gpu-example
resources:
  cpu: 2
  memory: 8GiB
  gpu:
    count: 1
    min_memory: 8GiB
    device_ids: [GPU-REPLACE_WITH_APPROVED_UUID]
```

Task 自身的资源约束仍须允许该请求。`run preflight` 检查任务、镜像与授权容量，`run submit` 在执行时重新检查空闲量并创建 Lease。未授权或总容量不足报 `unsatisfiable`；暂时被本平台 Lease、外部计算进程占用或空闲显存不足报 `waiting`，当前不会自动排队。Run 将 Lease 中的确切 UUID 传到 Docker CDI `--device nvidia.com/gpu=UUID`，在没有对应 CDI 设备时使用旧版 `--gpus`，并核对容器实际 DeviceRequests；清理成功后才释放 Lease。详情见[本机 Run 控制服务](../reference/local-run-controller.md)。

Controller 启动检查和自检都不能保证之后的任务一定获得 GPU：外部进程可能在采样后启动，Docker 设备映射也可能因主机配置变化失败。应核查 Run 的最终状态、清理和释放结果，并查看任务自己的 CUDA/训练指标。
