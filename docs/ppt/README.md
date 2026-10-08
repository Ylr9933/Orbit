# Orbit · 让实验有迹可循

打开 `index.html` 即可演示，无需构建或启动服务。字体和动画已内嵌，断网可用。
推荐使用 16:9 横屏或浏览器全屏演示。
采用 guizang-ppt-skill 的电子杂志模板与「牛皮纸」主题：卡其纸色、深棕墨色、衬线大标题。

## 操作

- `←` / `→`、空格、滚轮或左右滑动：翻页。第 5 页按步骤推进，再进入下一页。
- `Esc`：页面总览；点击缩略图跳页。
- `B`：静态模式，关闭背景和入场动画。
- `P`：演讲者模式，弹出独立观众窗口；需要允许浏览器弹窗。
- 演讲者模式提供讲稿、计时、排练、激光笔、圈选和观众屏恢复。该模式的 `B` 是黑屏。
- 可用 `index.html?slide=5` 直接打开第 5 页。浏览器打印可导出横向 PDF。

页面共 13 页。没有指定演讲时长，因此备注不预设分钟数，也不默认自动翻页。
本地修改的讲稿保存在当前浏览器，分享 HTML 不会带走这些修改。

## 内容与页面计划

资料截至 2026-10-08，来自当前仓库的 [README](../../README.zh-CN.md)、[设计](../design.md)、
[状态](../status.md)与飞书功能分支的任务记录。示意图表达结构，不展示伪造的实验结果。
单机、benchmark、多节点和飞书功能分别说明验证范围。

| 页 | 页面 ID | 主题 | 版式 | 观众看什么 / 演讲目的 |
| --- | --- | --- | --- | --- |
| 01 | cover | hero light | 封面 | Orbit 的定位与实验执行主线 |
| 02 | questions | dark | 三栏大字报 | 运行位置、代码来源与结论依据 |
| 03 | responsibilities | light | 双栏对比 | Agent 与 Orbit 的职责 |
| 04 | one-run | hero dark | 章节幕封 | 一个 Run 贯穿整个实验 |
| 05 | lifecycle | light | Pipeline | 预检、资源、执行、采集、清理 |
| 06 | resources | dark | 图文混排 | GPU / CPU / 内存租约与外部负载 |
| 07 | evidence | hero light | 大引用 | 从执行转向可追溯的证据 |
| 08 | review | dark | 记录矩阵 | 代码、日志、指标、产物、会话与笔记 |
| 09 | benchmarks | light | 结构图 | task × method × seed，solve 与 verify |
| 10 | cluster | dark | 图文混排 | 多节点放置、数据与记录的去向 |
| 11 | phone | hero light | 图文混排 | 飞书配对、只读查询、结果通知 |
| 12 | first-run | light | 代码 / 操作步骤 | 从环境检查到第一次运行 |
| 13 | closing | hero light | 收束 | 资源说清、过程留下、结论可查 |

每页的目的、补充讲述和转场均保存在 HTML 的 `SPEAKER_NOTES` 中。后续可直接编辑 HTML 的
`section[data-slide-id]`，重排页面时同步重排备注，保留稳定 ID。

## 来源与许可

- 模板、演讲者运行时及其修改源自[歸藏 guizang-ppt-skill](https://github.com/op7418/guizang-ppt-skill)，
  源版本 `c91369c449d34755d320a8b81d0734000d99d1ab`，保留 [AGPL-3.0 许可](licenses/guizang-AGPL-3.0.txt)。
  `index.html` 即完整可编辑源码；本目录演示稿沿用该许可，Orbit 主程序的许可见仓库根目录。
- 内嵌 Motion 动画模块随技能提供，其 MIT 许可保留在 [Motion 许可](licenses/motion-MIT.txt)。
- Noto CJK 与 Liberation 字体按本演示稿字符集裁剪并内嵌；原始版权和 OFL 许可分别见
  [Noto](licenses/noto-cjk.txt)与 [Liberation](licenses/liberation.txt)。
