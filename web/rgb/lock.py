"""Cross-process exclusion for one rgb-lib datadir."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO


class WalletInUseError(RuntimeError):
    """Another process already owns this wallet datadir."""


class WalletProcessLock:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()
        self.path = self.data_dir.parent / f".{self.data_dir.name}.rgb-bill.lock"
        self._handle: IO[str] | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise WalletInUseError(
                f"wallet datadir is already owned by another process: {self.data_dir}"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None

    def __enter__(self) -> WalletProcessLock:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()
