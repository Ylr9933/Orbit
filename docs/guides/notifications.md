# 通知目标

Webhooks 支持 `feishu`、`dingtalk`、`wecom`、`slack` 和 `webhook`。推荐通过 stdin 或环境变量提供 URL：

```bash
orbit notify add team --kind feishu --url-stdin --on failed,group
orbit notify add team --kind feishu --url-env FEISHU_HOOK --on failed,group
```

`--url-stdin` 在终端隐藏输入，也可以接收管道（如 `cat webhook-url.txt | orbit notify add team --kind feishu --url-stdin`）。
`--url-env` 从已设置的环境变量读取。旧的 `--url <url>` 仍可用，但会在 stderr 警告：URL 中的密钥可能被其他本机用户
从进程参数读取，也可能留在 shell 历史里。成功输出只包含目标名称、类型和事件，不回显完整 URL。

`--on` 支持逗号分隔的 `succeeded,failed,group`，默认全部启用。`group` 在组内 Run 都结束后发送汇总。
保存后可用 `orbit notify test team` 发测试消息；`orbit notify list` 查看目标，`orbit notify rm team` 删除。
飞书自建应用使用 `orbit feishu init`，或 `orbit notify add --kind feishu-app --app-id ... --secret-stdin`。
