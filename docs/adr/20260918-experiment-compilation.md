# 确认的实验、冻结任务包与显式目录重绑定

状态：C01–C03 采用；承接[研究快照 ADR](20260918-research-planning.md)。

## 背景与备选

Plan 是可修订的研究描述，Task 是供执行读取的具体材料与协议。
直接引用活动项目目录会使同一任务在不同时间读取不同内容；复制整个项目则会暴露未选材料并浪费空间。
分别新增一套任务 DTO、YAML 协议和 Docker runner 会让后续维护出现重复规则。

## 决定

1. Projects 选择已采用的 ResearchRevision 和 Experiment；通过 Tasks 公开的加载、检查、视图、冻结与资源校验函数验收生成物。
   现有 Task manifest schema 1 不改变，新增不含路径的 TaskReference；来源关系保留 Project/Experiment/research revision/digest。
2. 仅复制选定输入，加上生成说明和明确指定的控制配置。代码/数据使用项目内相对路径，输入必须有声明版本，同时记录实际内容摘要。
   编译不读取隐藏 benchmark 评测协议；科研入口要求显式 evaluation=none，原生 benchmark 继续沿已有适配器。
3. 以现有 Task sections 作为 execution YAML，不再设计一套相似配置。镜像与工具需求必须明确；实际镜像解析、工具绑定、预算和执行授权由 D 批预检。
4. Task ID 稳定，revision 对生成文档（不包含 revision 自身）取摘要；绝对位置、时间和复制预算不参与身份。
   TaskSnapshot 记录定义和材料摘要，关联另外保存整个包摘要，以便检测未声明额外文件。
5. 在控制目录同文件系统上暂存，再通过不覆盖的原子 rename 发布，最后登记 SQLite 关联。
   发布后登记前中断可用原输入重试；既有同名包先验证，不覆盖损坏内容。工作区移动不影响控制目录中的旧包。
6. rebind 仅重新登记用户已经移动的工作区。以旧路径缺失、精确清单和身份标记校验归属，借用既有 projection_pending/recover 完成跨介质恢复。
   不增加另一套项目迁移状态机；不自动移动、合并目录或接管复制出的身份。

## 结构与兼容

拆分 Projects 的连接/迁移、研究 SQL、编译关联 SQL；LocalProjectStore 保留旧入口并组合这些查询。
编译协调、材料复制和纯内容转换分别放在独立文件，入口不包含 SQL 或材料规则，详见[维护说明](../implementation/project-workflow-code-guide.md)。

控制库 schema 升到 3，增加 compiled_tasks 表。旧 Project/Research 表与研究规范化逻辑不变；只读旧库支持返回空编译关联。
旧 A/B 二进制拒绝 schema 3；降级必须恢复升级前备份。Task manifest 及已有 benchmark 接口保持兼容。

## 后果与限制

需要额外磁盘来复制材料；默认大小、条目和深度限制使开销可控。大型不可变对象存储引用留待独立适配，不用活动绝对路径冒充冻结。
当前一次编译持有控制库 writer 锁，适合本机单管理员；长复制会阻塞其他写入，未来优化需保留确认与提交的一致性。
进程崩溃可重试，但强制退出的临时目录和未登记包不会自动清扫。
普通编辑检测不是同 UID 安全边界；返回 manifest 路径之后也可能被人为修改，执行方必须继续验证 TaskReference 的快照。
compiled 仅是准备结果，不能替代 Run 的预检、资源租约、镜像安装或真实实验验收。
