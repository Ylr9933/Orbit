---
record_version: 1
task_id: "20260920-web-workflow-w84d2a"
title: "W 批：统一科研项目与实用 Web 执行入口"
branch: "feat/web-research-workflow"
base_commit: "3a031468c337efe09bbb8bf1e6395e50e75cd6a7"
work_status: completed
updated_at: "2026-09-20T19:33:16+08:00"
pull_request: null
---

## Goal and acceptance

- 实现 W01/W02：新旧项目统一列表；旧 ID、目标、里程碑、Task/Run 关联保留，未绑定和无法解析的关联明确显示，读取不创建工作区。
- 新建项目使用 CLI 同一服务；查看 Brief/Plan/未知项及已采用实验，编译、预检、显式提交与取消，刷新恢复 Run。
- Project/Run/Job 分开显示；实际 Controller 能力驱动按钮；产物复用 D 的成员校验与私有过滤；查看 I 的分析证据。
- 验证兼容/幂等/错误与隐私边界、HTTP 和浏览器流程，运行工程检查；本批不调用真实模型或启动 Docker/GPU 工作负载。

## Changes

- `projects/console.py` 联合读模型；初始化、研究和编译复用 A/B/C 服务。旧 catalog 追加显式工作区绑定和路径哈希任务身份表，旧记录不重写；读取不初始化工作区。
- `gateways/http/workflow.py` 提供项目详情、编译、D 预检/提交/取消、持久运行及 I 分析的安全投影；`bootstrap/web.py` 注入同一状态目录中的服务。
- CLI `web --state-dir` 与项目及 Controller 共用状态；Controller 凭据仅在服务端。默认 Records 改为 Controller 目录，旧目录仍可显式 `--records-root` 指定。
- 前端按项目创建、详情、实验提交、运行和产物拆分；选择已采用实验、显示资源预检、明确模型/时限/网络后提交；修改参数使预检失效，sessionStorage 操作 ID 支持不确定结果重试。
- Run、Job、项目进度和清理状态分别展示；产物文本预览/下载走 D 的过滤和 manifest 成员检查，分析展示数值与来源；无控制器时仍可查询持久数据。
- 更新 README、文档导航、设计与使用说明、项目概览；新增 HTTP/存储兼容测试、实际 CLI 启动测试和 Chromium 工作流回归。没有新增依赖或更改根治理规则。

## Decisions

- 从 I 分支建立独立 W 分支，保留 H/E/I 依赖；未合并或推送。
- 保留旧 catalog，采用联合视图与显式一对一绑定；绑定是别名，不删除任何条目。两种项目 ID 均保留，条目总数不等于研究主题去重数量。
- 路径哈希首次注册时固定身份，后续缺失或版本改变显示待处理；旧关联可保留，新关联必须验证。没有猜测未提供的研究字段。
- Web 只转交执行请求，不复制运行状态机；绑定、浏览、编译及预检都不会隐式启动模型。
- [设计与代码分工](../architecture/web-research-workflow.md)和[操作指南](../operations/web-console.md)说明接口、兼容和范围。
- 本批不增加聊天、研究方案编辑器、自动采纳方案、多用户权限或 H/E/I 生命周期按钮；长期环境和 Planner 仍通过既有 CLI/MCP 操作。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | 最终代码子树，见下 | passed | 267 passed，22 E2E deselected；Ruff、mypy（113 source files）、依赖图、政策镜像/文档链接、Web 类型及 Python/Web 构建通过；`/tmp/w-verify-final.log` |
| `uv run --locked pytest -q tests/unit/web` | 最终行为实现工作区 | passed | 9 passed；HTTP 双提交相同 Run、取消/清理、旧映射与初始化幂等、缺失关联、未完成投影、跨项目拒绝、私有过滤、离线读取、实际 web CLI；`/tmp/w-focused-final.log`，最终全量也覆盖 |
| `node tests/web/workflow.smoke.cjs`，设置本机 Playwright / Chromium 路径 | 最终 Web asset `index-iZVo-FFD.js` 与代码子树 | passed | 真浏览器 → HTTP → Projects/Records/Controller；初始化、绑定、编译、预检参数变化、丢失提交回执重试、刷新 Run、取消、Job、指标预览/下载、分析、390px；`/tmp/w-browser-final2.log` |
| `node tests/web/console.smoke.cjs`，同一浏览器工具 | W Web 资产与兼容服务 | passed | 旧项目创建/编辑/关联、导航、轨迹、私有过滤、真实主机只读采样、窄屏与退出；`/tmp/w-legacy-browser.log` |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 最终源码构建 wheel，仓库外独立安装 | passed | 原有 CLI、Project/编译、包内资源及新入口兼容；`/tmp/w-wheel-final.log` |
| 视觉与最终差异检查 | 最终工作区 | passed | 查看项目/运行截图、检查敏感文件与无关变化；没有运行产物进入 Git，没有遗留本任务测试服务 |
| 真实 Agent / Docker / GPU / 多节点 | None | not_run | 本批未运行模型或容器；浏览器执行端明确使用 FakeEnvironment/CredentialFixture，不能视作新增真实实验验收 |

测试快照：`src=38631592af20644a2ff81e5592b0fa9d7d3c524f`，`tests=975957115d96e911c69ae31d1e038dfa0f2c1b8e`。
浏览器工具复用 `/home/wangxuehai/.npm/_npx/e41f203b7505f1fb/node_modules/playwright` 和已安装 Chromium；未修改项目依赖。
截图在 `/tmp/agent-infra-w-project.png`、`/tmp/agent-infra-w-results.png`、`/tmp/agent-infra-w-mobile.png`，仅用于本机验收。
开发期失败已修正：旧未知 POST 的状态码回归、测试 JSON tuple/list 差异、折叠表单定位、GPU 字段类型与 fixture 内存预期。
全量检查仍有原先 MCP/Pydantic lifespan warning；没有修改依赖或跳过测试来消除它。

## Open items and blockers

None：W01/W02 范围已完成。单管理员、无聊天、H/E/I 控制仍用 CLI、Codex CPU 执行范围和真实模型未追加验收属于明确产品边界。

## Next steps

- 审查本分支并按用户后续授权集成 H/E/I/W；部署时选择与现有项目一致的状态目录，再用实际科研工作区试用。

## Compatibility and rollback

- catalog 旧 projects 表不变，新增 workspace_bindings/task_identities 可被旧代码忽略；新工作区保存在 Projects 原状态库，无 Projects schema 升级。
- 默认 Records 目录与 Controller 统一；原 `var/runs/_records` 等目录必须显式传 `--records-root`。新增工作流端点与旧 runs/attempts 查询端点分开。
- 回滚代码后旧页面仍读取原 catalog；新增项目、编译与执行证据保留，不删除目录、映射或产物。不要把 Web 退出或回滚当作停止后台 Run。
