import type { TraceEvent } from "../api/console";

export interface TimelineItem {
  event: TraceEvent;
  response?: TraceEvent;
}

export type TimelineFilter = "highlights" | "all" | "tools" | "agent";

const routineTools = new Set([
  "read",
  "list",
  "logs",
  "status",
  "artifact",
  "artifacts",
  "events",
  "trajectory",
]);

const toolLabels: Record<string, string> = {
  open: "启动实验环境",
  close: "关闭环境并归档",
  write: "写入实验文件",
  read: "读取工作区文件",
  list: "列出工作区文件",
  start: "启动容器任务",
  stop: "停止容器任务",
  logs: "读取任务日志",
  status: "查询环境状态",
  archive: "保存产物快照",
  artifacts: "列出归档产物",
  artifact: "读取归档产物",
  events: "查询运行事件",
  trajectory: "查询派生轨迹",
};

function field(event: TraceEvent, key: string): string | null {
  const value =
    event.payload && typeof event.payload === "object"
      ? (event.payload as Record<string, unknown>)[key]
      : null;
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : null;
}

function isToolError(event: TraceEvent): boolean {
  const payload = event.payload;
  return (
    event.type === "tool.failed" ||
    (payload !== null &&
      typeof payload === "object" &&
      (payload as Record<string, unknown>).is_error === true)
  );
}

export function groupTimeline(events: TraceEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  const requests = new Map<string, number>();
  for (const event of events) {
    const callId = field(event, "tool_call_id");
    const key = callId ? `${event.producer}:${callId}` : null;
    if (
      (event.type === "tool.completed" || event.type === "tool.failed") &&
      key &&
      requests.has(key)
    ) {
      items[requests.get(key) as number].response = event;
      continue;
    }
    if (event.type === "tool.requested" && key) requests.set(key, items.length);
    items.push({ event });
  }
  return items;
}

export function filterTimeline(
  items: TimelineItem[],
  filter: TimelineFilter,
): TimelineItem[] {
  if (filter === "all") return items;
  if (filter === "tools")
    return items.filter((item) => item.event.type.startsWith("tool."));
  if (filter === "agent")
    return items.filter((item) => item.event.producer === "agent");
  return items.filter((item) => {
    if (timelineTone(item) === "warning") return true;
    if (item.event.producer === "agent") return true;
    if (item.event.type === "tool.requested") {
      const tool = field(item.event, "tool_name");
      return !tool || !routineTools.has(tool);
    }
    if (item.event.type === "tool.completed") {
      const tool = field(item.event, "tool_name");
      return !tool || !routineTools.has(tool);
    }
    return true;
  });
}

export function timelineDuration(item: TimelineItem): string | null {
  if (!item.response) return null;
  const elapsed = Date.parse(item.response.at) - Date.parse(item.event.at);
  if (!Number.isFinite(elapsed) || elapsed < 0) return null;
  if (elapsed < 1000) return `${elapsed} 毫秒`;
  if (elapsed < 60_000) return `${(elapsed / 1000).toFixed(1)} 秒`;
  return `${(elapsed / 60_000).toFixed(1)} 分钟`;
}

export function timelineSummary(item: TimelineItem): string | null {
  const duration = timelineDuration(item);
  if (duration) return `耗时 ${duration}`;
  const node = field(item.event, "node_id");
  if (node) return `节点 ${node}`;
  const job = field(item.event, "job_id");
  if (job) {
    const code = field(item.event, "exit_code");
    return `Job ${job.slice(0, 8)}${job.length > 8 ? "…" : ""}${code ? ` · exit code ${code}` : ""}`;
  }
  const name = field(item.event, "name");
  if (name && item.event.type === "artifact.committed") return `产物 ${name}`;
  return null;
}

export function timelineTone(
  item: TimelineItem,
): "normal" | "warning" | "success" {
  const status = field(item.event, "status");
  if (
    isToolError(item.event) ||
    (item.response && isToolError(item.response)) ||
    item.event.type.endsWith(".failed") ||
    item.event.type.startsWith("capture.") ||
    status === "rejected" ||
    status === "failed" ||
    item.event.capture_status !== "complete"
  )
    return "warning";
  if (item.event.type === "process.exited" && status === "completed")
    return "success";
  return "normal";
}

export function timelineTitle(item: TimelineItem): string {
  const { event } = item;
  const tool = field(event, "tool_name");
  if (event.type.startsWith("tool.")) {
    const owner = event.producer === "agent" ? "Agent 工具" : "平台工具";
    return `${owner}：${tool ? (toolLabels[tool] ?? tool) : "未知操作"}`;
  }
  if (event.type === "lease.granted") return "已分配计算资源";
  if (event.type === "environment.ready") return "容器环境已就绪";
  if (event.type === "agent.message") return "Agent 消息";
  if (event.type === "job.submitted") return "已提交容器任务";
  if (event.type === "process.started") return "容器任务已启动";
  if (event.type === "artifact.committed") return "已归档产物";
  if (event.type === "capture.gap") return "记录存在缺口";
  if (event.type === "capture.truncated") return "记录被截断";
  if (event.type === "process.exited") {
    const status = field(event, "status");
    return status === "completed"
      ? "容器任务已完成"
      : status === "rejected"
        ? "容器任务被拒绝"
        : `容器任务结束${status ? `：${status}` : ""}`;
  }
  return event.type;
}

export function timelineStatus(item: TimelineItem): string {
  if (item.event.type === "process.exited") {
    const status = field(item.event, "status");
    if (status === "completed") return "已完成";
    if (status === "rejected") return "被拒绝";
    if (status === "failed") return "执行失败";
  }
  if (item.event.type === "tool.requested")
    return item.response && isToolError(item.response)
      ? "调用失败"
      : item.response
        ? "已返回响应"
        : "本页未见响应";
  if (item.event.type === "tool.completed")
    return isToolError(item.event) ? "调用失败" : "已返回响应";
  if (item.event.type === "tool.failed") return "调用失败";
  return item.event.capture_status === "complete" ? "记录完整" : "记录不完整";
}

export function timelineDetails(item: TimelineItem): string {
  const { event, response } = item;
  return JSON.stringify(
    {
      type: event.type,
      event_id: event.id,
      capture_status: event.capture_status,
      payload: event.payload,
      ...(response && {
        response_event_id: response.id,
        response_at: response.at,
        response_capture_status: response.capture_status,
        response_payload: response.payload,
      }),
    },
    null,
    2,
  );
}
