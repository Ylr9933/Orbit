---
record_version: 1
task_id: "20260918-research-planning-b6f2a1"
title: "Persist research planning and deliver a reusable planning skill (B01–B05)"
branch: "feat/research-planning"
base_commit: "c9f3498110c6b30a39cf2855fbb0250ba406a7ca"
work_status: completed
updated_at: "2026-09-18T20:32:27+08:00"
pull_request: null
---

## Goal and acceptance

- 实现 B01–B04：允许缺项的 Brief/Plan/Experiment、来源与用户选择、不可变修订、精确版本确认、上下文和差异、受保护的 Markdown 投影、显式笔记导入、包内研究 Skill 与 CLI。
- B05：真实 Codex 保存方案、处理用户纠正并通过新会话恢复。用户指定 `gpt-5.6-sol`，最多启动 3 次 CLI、累计 10 分钟；一次 CLI 内可以有多轮模型请求。不能用替身代替，不使用 `gpt-6-astra`。
- 实际场景为“比较位置编码对长上下文的影响”；用户纠正为“只比较两种方法，最多一张 GPU，数据待定，只做规划”。
- 复用 Projects SQLite、文件保护、Resources YAML；不新增聊天引擎，不启动实验，不迁移旧 Web catalog。
- 自动测试、make verify、安装 wheel 后的规划与 Skill 验收通过；文档如实区分实现、真实验收及合并。

## Changes

- B01：新增 `ResearchDraft` / `ResearchRevision`，保存 Brief、关键来源声明、未决问题和下一步；不可变快照、并发版本检查、幂等重试、精确版本及摘要确认。允许不完整草稿，原始目标保持不变。
- B02：同一快照内增加 Plan 和稳定 ID 的 Experiment，表达方法、变量、输入版本、指标、输出、资源引用和停止条件；拒绝未知字段、重复 JSON 键、越界路径和无效结构。check 复用 Resources YAML 校验器，不分配资源或启动执行。
- B03：上下文、历史和差异查询，受保护的 Markdown 投影、中断恢复及显式笔记导入。B01–B03 沿用 Projects 控制库并事务升级到 schema 2；薄 CLI `agent-infra project research` 接入 save/show/history/diff/confirm/context/check/export/import-notes/skill。
- B04：随 wheel 交付 `agent-infra-research` Skill，可安装到单个项目 `.agents/skills/`；复用 Agent 对话，指导澄清、修订、来源区分、保存和恢复，不修改全局配置。
- B05：新增显式启用的 `scripts/acceptance/research_codex.py`，已完成三次真实模型会话和人工证据核对。运行材料留在仓库外，不进入版本控制。
- 新增[使用说明](../reference/research-planning.md)与[快照 ADR](../adr/20260918-research-planning.md)，更新开发计划、文档导航、README 和项目概览。用户随后授权本地合并，在任务分支上将概览与开发计划调整为适用于 main 的表述。

## Decisions

- Brief 和 Plan 在同一研究快照中版本化，避免确认的 Plan 关联到后来被改写的 Brief。
- 草稿可不完整，来源声明不等于真实性验证。检查仅报告结构/引用缺口，不分配资源或宣称可以运行。
- 复用 Codex 的交互；代码管理持久状态、精确确认和冲突，Skill 指导按需澄清。
- 实验 ID 在同一实验修订中保持稳定；当前 context 明确返回空 run_references 和 execution_links_supported=false，避免伪造未实现的实验关联。
- 采用决定由可信本机调用者记录，不提供多人身份认证；保存与确认都不会启动实验。具体取舍、兼容及失败行为见 ADR。
- 本次按用户明确指令进行本地合并；设计、开发计划、A 批和 B 批分支为同一祖先链，可通过快进一并纳入。保留分支，不推送远端；集成结果由 Git 历史证明。

## Validation

| Check or command | Tested revision or snapshot | Result | Evidence or limitation |
| --- | --- | --- | --- |
| `make verify` | 最终自动验收快照，见下方树摘要 | passed | Ruff、mypy、导入边界、Web 检查、文档校验、181 项测试与 Python/Web 构建通过；7 项 Docker E2E 不在本次范围。 |
| `uv run --locked python scripts/ci/smoke_wheel.py` | 同上，最终构建 wheel | passed | 脱离源码目录独立安装；初始化、规划保存、用户笔记冲突与导入、context、Skill 读取及安装均通过。 |
| `uv run --locked python /disk/disk_20T/wangxuehai/.codex/skills/.system/skill-creator/scripts/quick_validate.py src/agent_infra/projects/skills/agent-infra-research` | 本分支 Skill | passed | Skill 格式校验通过。 |
| `uv run --locked python scripts/acceptance/research_codex.py --run-real-codex --model gpt-5.6-sol --output-dir /tmp/agent-infra-b05-20260918-b6f2a1 --correction-file /tmp/agent-infra-b05-user-correction-20260918.txt --seconds 600` | B05 源码树 `dcfc155b21793cdb936c5aa424138eb4a0aa2d4b` | passed | Codex CLI 0.154.0；3 次全新真实会话均退出 0，累计 347.16 秒；逐一核对实际保存命令、内容和恢复回答。 |
| Docker / GPU / 训练 / 其他 Agent 自动 Skill 发现 | 本分支 | not_run | 不属于获准 B 批验收范围；不据规划验收推断执行闭环可用。 |
| 合并前 `check_repository.py`、`git diff --check` 与代码树核对 | `39e97f0` 加本次三份文档调整 | passed | 文档链接与格式检查通过；src/tests/scripts 与上次通过验收的树一致，未重复运行模型或全套测试。 |

最终自动验收内容以 Git 子树标识：`src=8b423e46bc2dd13926f7a8b417fb96eacd9c809f`、
`tests=779b60d9fee8529715098b7c2327fce2abca8975`、`scripts=2fe1eca8232bc1bc82be1a74e912f3280b7284e3`。
父提交为 front matter 中 base_commit；依赖声明和锁文件未变。真实验收后补充了历史确认查询、重复 JSON 键拒绝、
Skill 参数位置提示及相应测试，最终自动验收覆盖这些调整；未额外调用模型超出三次预算。

### B05 真实交互证据

证据目录：`/tmp/agent-infra-b05-20260918-b6f2a1`，包含 sessions.json、各轮工具事件、回答和 context；
这些是本机非版本化材料，不保证永久保留。项目 ID 为 `4e752573-1b2b-50b3-b0c5-8554cf16d635`。

| 会话 | 用时 | 持久 revision | 核对结果 |
| --- | --- | --- | --- |
| 初稿 | 147.92 秒 | 1 | 真实 CLI 保存 Brief/Plan；三种方法、合成数据及长度设置作为初步假设，未知条件被保留，未确认采用。 |
| 用户纠正 | 128.39 秒 | 2 | 写入两种方法、最多一张 GPU、数据待定、只做规划；撤回未授权的三方法/数据/长度选择，保留原始目标和实验 ID。 |
| 新会话恢复 | 70.85 秒 | 2 | 从 context 和 check 恢复全部用户约束、未决问题和下一步；未写入新版本，未启动实验。 |

稳定实验 ID：`pilot-posenc-length-extrapolation`。第一轮文档摘要为
`sha256:827cf2455e16cfdc163174c42649c3f2c14d9ca9a9046d0be89209cd550409b2`；第二、三轮同为
`sha256:a6873d65aaa7e96f3c4c2e45692dde65f067db766abe2d8e952233fe74b6d2b1`。
三轮 accepted_revision 均为 null：用户约束不等于采用 Agent 额外建议，精确确认行为另外由自动测试覆盖。
第三轮 check 如实报告 10 项缺口，execution_validated/source_truth_verified 均为 false。

原始事件 SHA-256（events-1/2/3.jsonl 顺序）：

- `70388a0612338de400aee79d648ff5572d9bc55f2440b789aedb5685029cc525`
- `5e0276df2e7e403953ce0a5243def48da769bfea5b2d5b33d079b71816df3bc7`
- `fdbfc13a8a7addd937dab60fae8bd4b101c730f8672439ff67213c607c853b7a`

过程中 Agent 两次将 --state-dir 放错位置，另一次尝试了不存在的 jq，随后自行纠正并成功保存。
因此不是所有中间工具调用都成功；已在 Skill 命令说明中强调参数位置以及 save 自带校验、不依赖 jq。

## Open items and blockers

- None：获准 B01–B05 范围与对应验证已完成。Task 编译、实验执行、结果关联和 Web 接入属于后续批次。

## Next steps

- 按用户授权快进本地 main 并核对祖先关系、代码树与任务记录；后续按开发计划推进 C01–C03，把一个实验编译为现有 Task。远端发布不在本次范围。

## Compatibility and rollback

- 新增研究 CLI 和存储表；保留旧项目、原始目标与初始化操作。只读旧库不升级，首次写入事务升级 schema 1 → 2。
- 升级前备份外部控制状态与工作区。旧 A 批程序不支持 schema 2；回退代码时同时恢复升级前备份，不直接改 user_version。
- 未改依赖/锁文件、旧 Web catalog、Docker/GPU 环境或全局 Agent 配置。记录完成表示实现和验收完成，不表示已合并 main。
