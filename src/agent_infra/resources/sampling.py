"""One bounded shared sampling loop for local console clients."""

from collections import deque
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from threading import Event, Lock, Thread
from typing import Any

from agent_infra.resources.api import HostResourceSnapshot


class ResourceSampler:
    def __init__(self, sample: Callable[[], HostResourceSnapshot], interval: float = 2) -> None:
        if interval <= 0:
            raise ValueError("sampling interval must be positive")
        self.sample = sample
        self.interval = interval
        self._stop = Event()
        self._lock = Lock()
        self._history: deque[dict[str, Any]] = deque(maxlen=450)
        self._error: str | None = None
        self._thread = Thread(target=self._loop, daemon=True, name="console-resource-sampler")

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=12)

    def collect(self) -> None:
        try:
            snapshot = asdict(self.sample())
            snapshot["captured_at"] = snapshot["captured_at"].isoformat()
            with self._lock:
                self._history.append(snapshot)
                self._error = None
        except Exception:
            with self._lock:
                self._error = "资源采样失败；保留上次数据"

    def read(self) -> dict[str, Any]:
        with self._lock:
            history = list(self._history)
            latest = history[-1] if history else None
            age = (
                (datetime.now(UTC) - datetime.fromisoformat(latest["captured_at"])).total_seconds()
                if latest
                else None
            )
            return {
                "latest": latest,
                "history": history,
                "error": self._error,
                "stale": age is None or age > max(10, self.interval * 3),
                "interval_seconds": self.interval,
            }

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.collect()
            self._stop.wait(self.interval)
