# 本地 Project 初始化的存储与恢复

状态：本次 A00–A07 实施采用。范围：Linux 本机单管理员、初始化和元数据；不涉及研究规划和执行。

## 决定

1. Projects 是独立模块，位于 gateways 与 runs 之间。下层模块不得反向导入 Projects。
2. SQLite 是 Project 元数据、revision、初始化请求和文件快照的权威存储；与 Records 的运行证据分开。
   旧 Web catalog 不迁移、不双写，后续 W01 显式适配并保留旧 ID。
3. `project.yaml` 和模板文档是可读投影，原始目标精确保留。用户可编辑科研文档；重跑 init 不重置文件。
   初始化尚未完成时如果发现文件内容冲突，保留现场并返回冲突。没有自动导入外部编辑或移动工作区的命令。
4. `agent-infra init [directory] --goal TEXT` 为主入口；`project init/preview/show/list/recover` 复用相同用例。
   `--name` 为显示名称；未指定 directory 时由名称生成目录名，再无名称则生成 `project-<随机标识>`。
   `--root` 或 `AGENT_INFRA_PROJECTS_DIR` 指定根目录，默认当前目录。父目录必须已存在。
   ID 随请求生成并持久保存，重命名或移动不会重新计算 ID，但移动后本版只报告位置不一致。
5. 默认状态根为 `$XDG_STATE_HOME/agent-infra` 或 `~/.local/state/agent-infra`；
   `--state-dir` 优先于 `AGENT_INFRA_STATE_DIR`。位置固定使换终端、换工作目录仍可查询。
   自动选择的用户默认路径先解析已有链接，支持服务器将 ~/.local 迁到数据盘；显式状态路径仍拒绝链接。
   每个状态根中使用 `projects/projects.sqlite3`；禁止与生成工作区互相包含。
6. 只创建不存在的新目录，包括已存在的空目录也不接管。无 `--force`，无自动 Git 初始化、提交或依赖安装。

## 幂等与故障恢复

- 初始化先在事务中保留操作 ID、项目 ID、目标路径、请求与完整渲染快照，再在同一父目录的私有 staging 中生成文件。
- 一个 state root 的写操作用进程锁串行化，事务仍校验 expected_revision；不同 store 竞争同一目标时，
  Linux `renameat2(RENAME_NOREPLACE)` 原子发布，绝不替换已存在目录。
- 发布后将初始化状态从 pending 改为 ready。ready 是目录交付状态，不表示科研完成。
- 崩溃在登记后：从存储快照补全 staging。崩溃在发布后：逐文件验证目标快照，完成 store 状态。
- 暂存写入通过独立临时文件与不覆盖的发布操作完成；重试只处理本请求的 staging 和内部临时文件。
- 已生成的文件与快照不一致时拒绝自动修复，保留修改。ready 项目重复 init 只返回原身份并检查清单身份，不重写科研文档。
- 同 operation ID 不同参数报冲突。未提供 ID 时，指定相同路径且参数相同也返回原项目；
  无目录/无名称每次默认创建新项目，要重试自动命名请求请保留输出中的 operation ID 或使用 recover。
- preview、show、list 不创建 store 或目录；预览输出包含 operation ID，可传给 init 固定自动名称和项目 ID。

## 最小修订能力

公共 store 支持 get/list 和带 expected_revision 的标题、研究状态更新；原始目标和项目 ID 不可修改。
元数据变更保留旧投影快照并标记 projection_pending，recover 仅在旧投影未被用户改写时更新 `project.yaml`，
随后保存新快照并恢复 ready；若新清单已发布但最后的事务未提交，可继续完成。
本版 CLI 只开放初始化、查询和恢复；研究方案版本、导入、改名和移动待后续任务。

## 边界与替代方案

仅用 YAML 难以原子协调操作 ID、唯一目录和并发 revision；直接写目录会暴露半成品；二者均不选用。
不引入后台服务和分布式事务。支持 Linux 本地文件系统；不承诺 NFS 跨机锁或断电后的磁盘损坏修复。
目录访问拒绝 symlink，使用目录描述符固定写入父目录。可信本机同 UID 用户仍可改数据库；
这些措施不构成同 UID 恶意进程之间的权限隔离。未来容器仅挂允许的工作区，不挂控制面 store。
