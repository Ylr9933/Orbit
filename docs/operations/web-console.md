# 本机 Web 控制台使用说明

状态：简版已实现；对应 [Web 设计方案](../architecture/web-console-design.md) 的 W0/W1 部分。
这是单管理员、单节点控制台，不是公网部署方案。它展示已有数据并管理项目，尚不能从页面发起或取消 Run。

## 启动

前提：在仓库根目录完成 `make setup`。工具版本见 [贡献指南](../../CONTRIBUTING.md)。
不需要 Docker 或 Agent 账号即可启动页面；显示运行数据需要已有的 Records 存储。

```sh
pnpm build
uv run --locked agent-infra web \
  --records-root var/runs/_records \
  --console-dir var/console \
  --web-root src/web/dist \
  --task examples/task-packages/file-result/task.yaml \
  --port 8765
```

这些参数均可省略；除 `--task` 默认为空列表外，上例给出了当前默认值。
`--task` 可以重复使用；只注册清单，不会执行任务。不存在的 Records 目录会初始化为空存储，
因此页面为空时应首先确认 `--records-root`，而不是认为之前的运行丢失。
当前 Run API 的默认共享记录目录为运行工作目录下的 `_records`；自定义过记录目录的用户应使用实际路径。

终端输出带有 `#token=...` 的访问地址，打开该完整地址。令牌由服务随机生成，重启后失效。
前端读取后立即从地址栏移除，保存在当前标签页 `sessionStorage`，只通过 Authorization 请求头传输；退出连接会清除。
不要公开该完整链接。Ctrl+C 停止服务，不会取消已有科研运行。

服务器上的服务只绑定 `127.0.0.1`。从个人电脑访问时，在个人电脑执行：

```sh
ssh -N -L 8765:127.0.0.1:8765 wangxuehai@prompt
```

然后在个人电脑打开终端给出的地址。两端使用同一端口；Host 校验只允许服务端口上的 localhost / 127.0.0.1。
多个工作区各自使用不同端口、`--console-dir` 和运行状态目录。首版没有反向代理、TLS、远程登录或多用户权限支持。

`make dev-web` 仍是独立的 Vite 源码开发入口；它没有默认 API 代理。完整体验使用上面的生产构建和 Python 服务。
Python wheel 当前不包含 Web 构建，安装到仓库外需显式指定 `--web-root`。

## 可以做什么

| 页面 | 已实现行为 |
| --- | --- |
| 总览 | 项目数、注册任务数、最近最多 100 条运行窗口、最近执行入口 |
| 科研项目 | 新建/编辑名称、目标、状态、里程碑；关联注册 Task 与最近 100 条 Run；里程碑进度由用户确认 |
| 任务 | Agent 可见材料索引、工具声明、公开输出约定、资源意图；不读取任意文件、不显示私有评测材料 |
| 运行 | 每页最多 100 条 Run；Attempt 状态、评测状态、清理与租约释放状态 |
| 资源 | 本机 CPU/内存/NVIDIA GPU 实测数据；共享采样循环、2 秒轮询、最多 450 个内存采样点及 CPU 趋势 |
| Agents | Codex/Claude Code/DSH 的安装、认证、版本及能力声明；未知状态明确显示“未知” |
| 记录 | 从 Run 进入事件时间线、按当前页筛选、翻页及手动刷新；产物元数据索引 |
| 设置 | 当前能力和访问、存储边界说明 |

Agent 探测复用已有只读 probe，不执行安装、不调用模型，结果缓存 60 秒。
资源数值是实际观测，不是调度器承诺的剩余额度。CPU 第一次采样、无法探测的 GPU 状态均不冒充零占用。
采样失败会保留上次数据并展示提示，过期样本会明确标记；历史曲线只存在于服务内存中，重启后清空。

Run 状态每 5 秒轮询；事件按页显式刷新。现有 Agent 正规化通常在阶段结束后完成，页面不是实时 token 流。
事件正文是最多 8,000 字符的展示摘要，不代替原始轨迹。未知格式可能只有事件类型没有文本。
原始日志、CAS Blob 和产物内容尚未开放下载；公共评测反馈和 reward 可在事件中查看。
未开放任意命令执行、容器终端、任务上传、Agent 登录、启动/取消运行、集群管理及训练导出操作。

## 数据和访问边界

- Project 是独立 SQLite catalog：`--console-dir/projects.sqlite3`。修改项目不会改写 Run/Attempt 的执行证据。
  项目更新携带 revision，冲突返回 409；请保留本地编辑内容，取消编辑后刷新再合并修改。
- 同名里程碑不允许重复。任务/运行关联必须存在。已关联任务需继续在服务启动时注册，否则编辑项目时需先恢复注册。
- Records 查询扩展 `list_runs(limit=100, offset=0)`，上限 200；不改已有数据库 schema。
- HTTP 不暴露原始 Run 请求、凭据路径、完整 Attempt 结果、原始 Blob 引用或完整 scorer 日志。
  事件/产物先按 `data_class` 和 `visibility` 过滤，再按允许的字段投影。私有评测、凭据、secret 和 evaluator/admin 可见材料不可展示。
- 这仍然是可信本机管理员界面。Agent 自己输出的普通文本不具备自动秘密识别能力；不要把它当作可公开分享的脱敏报告。
  任务目录、Records 写入者与 Web 构建目录属于可信输入，错误标记的数据不等同于经过内容审计。
- React 以纯文本呈现内容；没有 HTML/Markdown 直接执行。静态服务限制在构建目录，不提供任意宿主机文件读取。
- Bearer 鉴权、严格 Host、同源访问和 CSP 用于本机控制台边界；不能代替未来的用户/项目级授权。

## 当前 HTTP 接口

除静态页面外，所有请求带 `Authorization: Bearer <启动令牌>`，JSON 响应。

| 方法和路径（前缀 `/api/v1`） | 用途 |
| --- | --- |
| `GET /capabilities` | 当前范围和未开放能力 |
| `GET /resources` | 当前采样、短期历史、过期和错误标记 |
| `GET /agents` | 只读 provider 探测 |
| `GET /tasks` | 注册任务的安全投影 |
| `GET /projects` | 项目列表 |
| `POST /projects` | 创建或按 id + revision 更新；正文上限 64 KiB |
| `GET /runs?offset=0` | Run 分页 |
| `GET /runs/{id}` | Run 与 Attempt 摘要 |
| `GET /attempts/{id}/events?cursor=...` | 可展示事件分页；cursor 为不透明字符串 |
| `GET /attempts/{id}/artifacts` | 可展示产物元数据 |

400 参数无效、401 缺少/错误令牌、403 Host 不符、404 记录/接口不存在、409 项目修改冲突、503 服务不可用。
API 是当前本机 UI 的首版接口，尚未承诺第三方客户端的长期兼容性。

## 验证与排障

```sh
make verify
uv run --locked pytest tests/unit/web -q
```

另有可选浏览器回归脚本，使用独立安装的 Playwright 和 Chromium，不增加产品运行依赖：

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome-headless-shell \
node tests/web/console.smoke.cjs
```

该脚本启动随机端口、临时状态目录的明确测试服务，使用 fixture Run/Agent 事件验证页面，资源来自本机只读采样。
覆盖项目创建/编辑/刷新恢复、关联跳转、轨迹和产物展示、私有材料过滤、导航、390px 窄屏和退出。
测试截图写入 `/tmp/agent-infra-web-*.png`，不进入 Git；不会进行模型、Docker 或 GPU 工作负载验证。

页面 401：服务可能已重启，退出页面连接后使用新的完整访问地址。页面为空：检查 Records 路径和 `--task` 注册。
503：检查状态目录权限与数据库是否损坏；不要删除原始记录来消除错误。
项目 catalog 可在停止 Web 后备份；执行 Records 的备份策略见其独立文档。
