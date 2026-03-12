from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path


class DialogLogger:
    def __init__(
        self,
        enabled: bool,
        output_path: str | Path | None = None,
        capture_dir: str | Path = "captures",
    ):
        self.enabled = bool(enabled)
        self.path: Path | None = None
        self._fp = None
        self._lock = threading.Lock()

        if not self.enabled:
            return

        if output_path is None:
            capture_root = Path(capture_dir)
            capture_root.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            self.path = capture_root / f"tui-dialog-{ts}.log"
        else:
            self.path = Path(output_path)
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self._fp = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        with self._lock:
            if self._fp:
                self._fp.close()
                self._fp = None

    def record(self, message: str) -> None:
        if not self.enabled:
            return
        line = str(message).rstrip("\n")
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self._lock:
            if self._fp:
                self._fp.write(f"{ts} {line}\n")
                self._fp.flush()
