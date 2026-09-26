import { useEffect, useRef, useState } from "react";
import type { Batch } from "./types";

export function BatchNotifications({ batches }: { batches: Batch[] }) {
  const previous = useRef(new Map<string, number>());
  const [message, setMessage] = useState("");
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    const completed = batches.filter((b) => {
      const before = previous.current.get(b.id);
      return before != null && before < b.total && b.finished === b.total;
    });
    previous.current = new Map(batches.map((b) => [b.id, b.finished]));
    if (completed.length) {
      const text = completed
        .map((b) => `${b.name} 已结束，${b.scored}/${b.total} 有效评分`)
        .join("；");
      setMessage(text);
      if (
        enabled &&
        "Notification" in window &&
        Notification.permission === "granted"
      )
        try {
          new Notification("Benchmark 批次结束", { body: text });
        } catch {
          /* In-page completion remains visible. */
        }
    }
  }, [batches, enabled]);
  return (
    <div className="section-line">
      <span role="status">{message}</span>
      {"Notification" in window && (
        <button
          type="button"
          onClick={async () => {
            if (enabled) {
              setEnabled(false);
              return;
            }
            try {
              const permission = await Notification.requestPermission();
              setEnabled(permission === "granted");
              if (permission !== "granted")
                setMessage("浏览器通知未开启，完成状态仍在页面显示。");
            } catch {
              setMessage("此浏览器不支持桌面通知。");
            }
          }}
        >
          {enabled ? "关闭完成通知" : "开启完成通知"}
        </button>
      )}
    </div>
  );
}
