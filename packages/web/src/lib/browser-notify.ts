// Optional desktop notifications while the Web UI is open: runs that end, and groups that finish.
import type { Run } from "./api.ts";
import { isActive } from "./format.ts";
import { navigate } from "./router.ts";

const KEY = "orbit.browserNotify";
/** Auth checks are started from the CLI and reported there. */
const QUIET_GROUPS = new Set(["auth-test"]);

export const browserNotify = {
  supported: () => typeof Notification !== "undefined",
  enabled: () =>
    browserNotify.supported() &&
    Notification.permission === "granted" &&
    localStorage.getItem(KEY) === "1",
  async enable(): Promise<boolean> {
    if (!browserNotify.supported()) return false;
    const p = await Notification.requestPermission();
    if (p === "granted") localStorage.setItem(KEY, "1");
    return p === "granted";
  },
  disable: () => localStorage.removeItem(KEY),
};

/** Call for every live update with the previous version of the run (if known). */
export function notifyTransition(prev: Run | undefined, run: Run, all: Iterable<Run>): void {
  if (!prev || !isActive(prev.state) || isActive(run.state)) return;
  if (!browserNotify.enabled()) return;
  const group = run.spec.group;
  if (group && QUIET_GROUPS.has(group)) return;
  if (!group) {
    if (run.state === "cancelled") return;
    show(
      `${run.spec.name ?? run.id} ${run.state}`,
      run.reason ?? "",
      `/runs/${encodeURIComponent(run.id)}`,
      run.id,
    );
    return;
  }
  const members = [...all].filter((r) => r.spec.group === group);
  if (members.some((r) => r.id !== run.id && isActive(r.state))) return;
  const ok = members.filter((r) => (r.id === run.id ? run : r).state === "succeeded").length;
  show(
    `Group ${group} finished`,
    `${ok} of ${members.length} succeeded`,
    `/compare?group=${encodeURIComponent(group)}`,
    `group:${group}`,
  );
}

function show(title: string, body: string, href: string, tag: string) {
  const n = new Notification(`Orbit · ${title}`, { body, tag });
  n.onclick = () => {
    window.focus();
    navigate(href);
    n.close();
  };
}
