export interface PollOptions {
  poll?: boolean;
  pollMs?: number;
}

type Visibility = Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">;

/** Schedule after each settled request; a visible tab refreshes once before polling resumes. */
export function visiblePolling(
  reload: () => void,
  options: () => PollOptions,
  visibility: Visibility = document,
) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pending = true;
  let refresh = false;
  let disposed = false;
  const enabled = () => {
    const o = options();
    return !disposed && visibility.visibilityState !== "hidden" && o.poll && o.pollMs;
  };
  const run = () => {
    if (!enabled()) return;
    pending = true;
    refresh = false;
    reload();
  };
  const changed = () => {
    clearTimeout(timer);
    if (!enabled()) return;
    if (pending) refresh = true;
    else run();
  };
  visibility.addEventListener("visibilitychange", changed);
  return {
    settled() {
      pending = false;
      clearTimeout(timer);
      if (!enabled()) return;
      if (refresh) run();
      else timer = setTimeout(run, options().pollMs);
    },
    dispose() {
      disposed = true;
      clearTimeout(timer);
      visibility.removeEventListener("visibilitychange", changed);
    },
  };
}
