# H 批实现导读

状态：与 H 批实现对应；使用和边界见[命令参考](../reference/host-research-mcp.md)，验证见
[任务记录](../changes/20260920-host-research-mcp-a81f2c.md)。

## 调用方向

```text
Codex / CLI
  -> gateways/mcp/research.py / gateways/cli/research_runtime.py
  -> 项目绑定的 HTTP research/bind、research/call
  -> runs/research.py（研究用例）
      -> LocalRunController 单运行槽 + LocalResourceManager
      -> environments/job_api.py -> environments/research.py
          -> 现有 DockerEnvironment prepare/start/execute_control/cleanup/collect
          -> 容器内 _research_runtime.py
      -> runs/research_evidence.py -> Records
```

bootstrap/controller.py 组装依赖。Projects context 和 Agent 原生事件导入通过
bootstrap/host_research.py 注入，Runs 不访问 Projects 后端。MCP 使用 SDK 生成 schema，
协议入口只做参数适配，不拥有线程、资源租约或 Docker 客户端。

## 各文件维护什么

| 文件 | 维护范围 |
| --- | --- |
| `environments/job_api.py` | 长期环境的公共 Job/文件契约，保留原 solver API |
| `environments/_research_runtime.py` | 可独立运行的标准库监督进程：进程组、超时、有界日志、工作区文件 |
| `environments/research.py` | 把 Job 契约转换成 Docker 内私有 Unix socket 请求 |
| `runs/research.py` | 项目绑定检查、幂等入口、环境生命周期、Job 创建、停止和后台采集调度 |
| `runs/research_store.py` | 绑定 token 摘要、操作回执、Job 意图；不重复保存 Run 状态 |
| `runs/research_evidence.py` | 原始工具调用 Blob、日志 stream、Job 完成事件与关联 |
| `agents/recording.py` | 托管运行和宿主机导入共用的 AgentEvent → EventDraft 转换 |
| `gateways/cli/research_runtime.py` | 人工操作入口、明确文件上传和绑定 HTTP 客户端 |
| `gateways/mcp/research.py` | stdio MCP 工具；连接终止不操作环境生命周期 |
| `runs/query.py`、`runs/_artifact_view.py` | 共用产物授权/成员查找；原始下载与有界文本/二进制视图；不修改存储 |
| `gateways/mcp/artifacts.py` | 将读取视图转为 MCP 文本、图片或资源链接；资源读取仍经过绑定客户端 |

### 归档读取与兼容

`ResearchController` 的 artifact 请求带 `format` 时调用 `RunQueries.artifact_view`；
未带 format 的历史调用和 HTTP 下载继续走 `RunQueries.artifact`。两个入口共用可见性与
精确成员查找，私有评测产物不能通过新文本、图片或资源路径绕过检查。
内容视图只进行有界采样和分页读取；增量 UTF-8 解码将页尾未完成字符留给下一页，
`next_offset` 按实际返回字节推进。不解析模型权重或执行文件内容。

MCP schema 将 auto 作为默认；小图片的原始数据进入 ImageContent，不再复制到文本或
structuredContent。资源模板固定 MIME 类型并校验图片类型；URI 只编码身份与成员，不暴露
存储目录。科研 CLI 共用相同视图，Web/`run artifact --output` 保留整文件下载。
详细参数、限额和更新已有服务的步骤见[归档文件可读视图](../reference/host-research-mcp.md#归档文件的可读视图)。

`tests/unit/runs/test_artifact_views.py` 验证真实 Records 上的范围、编码与访问检查；
`test_artifact_mcp.py` 通过 SDK 内存传输、真实 loopback HTTP 和 Controller/Records 验证
工具与资源协议、项目隔离及旧下载。未使用的执行后端为替身，不启动 Docker 或调用模型。

## 状态权威与故障窗口

RunControlStore 的 command document 保存 Run/环境/租约引用，独立 research.sqlite3 保存 Job 和
操作回执。Records 保存证据。SQLite 提交先于执行；操作已写入但回复未提交的窗口返回
operation_uncertain，要求查状态，不自动重复副作用。Controller 与 D 批共用主机锁和单运行槽。

监督进程是容器主进程，控制 socket 在容器 `/tmp`，控制代码以只读输入挂载。Job 是其子进程，
有独立进程组。Docker exec 仅传输控制消息，连接退出不终止 Job。命令结束/超时/停止会终止组内
残留进程。日志在容器内有界缓冲，Controller 定期写本地日志副本和 Records 流，正常结束封存。

Environment 结束：停止 Job、排空日志、确认 Docker 删除、释放租约、冻结工作区并提交 artifact。
清理失败与归档失败分别报告。Controller 关闭先关闭研究用例，再关闭已有一次性运行协调器。
异常重启复用 Docker ownership journal 和 D04 清理，后续封存不完整 Job 日志；没有恢复训练进程。

文件读写通过容器内 dir_fd + O_NOFOLLOW 逐级打开，避免把检查后可能变化的路径交给宿主机操作。
环境结束后的归档复用现有正则文件/目录遍历和 digest 检查；不增加另一套归档实现。

## 扩展与验证入口

新增 MCP 工具先扩公共用例，再接 CLI/HTTP/MCP；不要直接从 gateway 调 Docker。
增加 GPU 或并发前须同时调整授权准入、单运行槽、清理和重启恢复，不能只添加 Docker 参数。
训练依赖通过已有镜像提供，自动环境准备属于 E 批。大型数据同步、网络授权和更强 Job 隔离需独立设计。

`tests/unit/environments/test_research_runtime.py` 检验实际监督逻辑、路径边界和超时；
`tests/e2e/test_host_research.py` 检验真实容器/Records/资源；
`tests/e2e/test_research_mcp.py` 启动独立 Controller 和真实 stdio 客户端，验证重连和 SIGKILL 恢复。
这些是无模型测试；H05 另用真实宿主机 Codex 调用 MCP，不能混称。
