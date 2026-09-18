# 一个可运行的 CPU 科研样例

比较单个异常值对均值与中位数的影响。这里提供数据和待采用的计划，分析脚本与结果必须由真实 Agent 生成。
需要已安装项目、Docker、已登录 Codex，以及构建好的 `agent-infra/codex-research:0.154.0` 镜像。
准备方法见[控制服务命令](../../../docs/reference/local-run-controller.md)。

在仓库根目录操作。`/absolute/demo-state` 和 `/absolute/statistics-project` 请换为自己的空目录：

```bash
export AGENT_INFRA_STATE_DIR=/absolute/demo-state
agent-infra init /absolute/statistics-project --goal '比较均值与中位数对单个异常值的敏感性'
cp examples/research/cpu-statistics/data.csv /absolute/statistics-project/data/raw/values.csv
cp examples/research/cpu-statistics/resources.yaml /absolute/statistics-project/configs/resources/pilot.yaml
cp examples/research/cpu-statistics/execution.yaml /absolute/statistics-project/configs/experiments/pilot.yaml

agent-infra project research save /absolute/statistics-project \
  --file examples/research/cpu-statistics/plan.json --expected-revision 0 --reason '采用小型 CPU 示例'
```

阅读保存输出中的方案；决定采用后，用输出中的精确 digest 确认（不是随意填写摘要）：

```bash
agent-infra project research confirm /absolute/statistics-project \
  --revision 1 --digest RESEARCH_DIGEST --decision '确认按该方案运行 CPU 示例'
agent-infra project compile /absolute/statistics-project --experiment robust-statistics \
  --revision 1 --execution configs/experiments/pilot.yaml
```

另一个终端使用相同 `AGENT_INFRA_STATE_DIR` 启动服务：

```bash
agent-infra controller serve --cpu 1 --memory-gib 2
```

使用 compile 输出的 Task ID 和 revision 提交。此步骤会调用真实模型，先确认自己的账号和费用/时间预算：

```bash
agent-infra run preflight TASK_ID --task-revision TASK_REVISION \
  --model gpt-5.6-sol --reasoning-effort low --network --timeout 180
agent-infra run submit TASK_ID --task-revision TASK_REVISION \
  --model gpt-5.6-sol --reasoning-effort low --network --timeout 180 --operation-id statistics-1
agent-infra run status RUN_ID
agent-infra run artifacts RUN_ID
agent-infra run artifact RUN_ID ARTIFACT_ID
agent-infra run artifact RUN_ID ARTIFACT_ID --member artifacts/metrics.json --output ./metrics.json
agent-infra run trajectory RUN_ID
agent-infra project research context /absolute/statistics-project
```

Artifact 选择名称为 `solver-submission` 的项。应得到：完整数据 mean=22、median=3；
去掉最后一个观测值后 mean=2.5、median=2.5。还应有 Agent 编写的 `code/analysis.py` 和
`artifacts/report.md`。这些数字用于本样例的人工核验，不是平台伪造的评测分数。
中途停止用 `agent-infra run cancel RUN_ID`，重新做一次实验用新的 operation ID。
