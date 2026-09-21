import type { TraceEvent } from "../api/console";

export interface TimelineItem {
  event: TraceEvent;
  response?: TraceEvent;
}

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

export function timelineTitle(item: TimelineItem): string {
  const { event } = item;
  const tool = field(event, "tool_name");
  if (event.type.startsWith("tool.")) {
    const owner = event.producer === "agent" ? "Agent 工具" : "平台工具";
    return `${owner}：${tool ? (toolLabels[tool] ?? tool) : "未知操作"}`;
  }
  if (event.type === "lease.granted") return "已分配计算资源";
  if (event.type === "environment.ready") return "容器环境已就绪";
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
  if (item.event.type === "tool.requested")
    return item.response?.type === "tool.failed"
      ? "调用失败"
      : item.response
        ? "已返回响应"
        : "本页未见响应";
  if (item.event.type === "tool.completed") return "已返回响应";
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
