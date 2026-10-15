import { afterEach, expect, it, vi } from "vitest";
import { type PollOptions, visiblePolling } from "../src/lib/polling.ts";

class Visibility extends EventTarget {
  visibilityState: DocumentVisibilityState = "visible";
  set(state: DocumentVisibilityState) {
    this.visibilityState = state;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}
afterEach(() => vi.useRealTimers());

it("pauses scheduled polling while hidden and refreshes once on return", () => {
  vi.useFakeTimers();
  const document = new Visibility();
  const reload = vi.fn();
  const poll = visiblePolling(reload, () => ({ poll: true, pollMs: 1000 }), document);
  poll.settled();
  document.set("hidden");
  vi.advanceTimersByTime(60_000);
  expect(reload).not.toHaveBeenCalled();
  document.set("visible");
  expect(reload).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(5000);
  expect(reload).toHaveBeenCalledTimes(1);
  poll.settled();
  vi.advanceTimersByTime(1000);
  expect(reload).toHaveBeenCalledTimes(2);
  poll.dispose();
  document.set("hidden");
  document.set("visible");
  vi.advanceTimersByTime(10_000);
  expect(reload).toHaveBeenCalledTimes(2);
});

it("waits for a slow in-flight request and coalesces visibility changes", () => {
  vi.useFakeTimers();
  const document = new Visibility();
  const reload = vi.fn();
  const poll = visiblePolling(reload, () => ({ poll: true, pollMs: 1000 }), document);
  for (let i = 0; i < 3; i++) {
    document.set("hidden");
    document.set("visible");
  }
  expect(reload).not.toHaveBeenCalled();
  poll.settled();
  expect(reload).toHaveBeenCalledTimes(1);
  document.set("hidden");
  poll.settled();
  vi.advanceTimersByTime(10_000);
  expect(reload).toHaveBeenCalledTimes(1);
  document.set("visible");
  expect(reload).toHaveBeenCalledTimes(2);
  poll.dispose();
});

it("respects disabled polling, updated intervals and disposal before a request settles", () => {
  vi.useFakeTimers();
  const document = new Visibility();
  const reload = vi.fn();
  let options: PollOptions = { poll: false, pollMs: 1000 };
  const poll = visiblePolling(reload, () => options, document);
  poll.settled();
  document.set("hidden");
  document.set("visible");
  vi.advanceTimersByTime(5000);
  expect(reload).not.toHaveBeenCalled();
  options = { poll: true, pollMs: 2000 };
  poll.settled();
  vi.advanceTimersByTime(1999);
  expect(reload).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(reload).toHaveBeenCalledTimes(1);
  poll.dispose();
  poll.settled();
  vi.advanceTimersByTime(10_000);
  expect(reload).toHaveBeenCalledTimes(1);
});
