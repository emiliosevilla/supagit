#!/usr/bin/env python3
"""Busy-line spinner and startup welcome for supagit."""

from __future__ import annotations

import sys
import threading
from typing import TextIO

from supagit_i18n import t

CYAN = "\033[36m"
GREEN = "\033[32m"
RESET = "\033[0m"
_SPINNER_FRAMES = ("|", "/", "-", "\\")


class BusySpinner:
    """Animate a green status line with \\r while work runs.

    Quick commands (< delay_s) never show the spinner. Non-TTY or disabled
    mode is a no-op so captured CI output stays clean.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        stream: TextIO | None = None,
        delay_s: float = 0.35,
        interval_s: float = 0.1,
    ) -> None:
        self.enabled = enabled
        self.stream = stream or sys.stderr
        self.delay_s = delay_s
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._shown = False

    def __enter__(self) -> BusySpinner:
        if not self.enabled:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="supagit-spinner", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._shown:
            # Clear the spinner line.
            self.stream.write("\r\033[K")
            self.stream.flush()
            self._shown = False

    def _run(self) -> None:
        if self._stop.wait(self.delay_s):
            return
        message = t("busy_working")
        abort = t("busy_abort_hint")
        index = 0
        while not self._stop.is_set():
            frame = _SPINNER_FRAMES[index % len(_SPINNER_FRAMES)]
            line = f"{frame} {message} {abort}"
            self.stream.write(f"\r{GREEN}{line}{RESET}\033[K")
            self.stream.flush()
            self._shown = True
            index += 1
            if self._stop.wait(self.interval_s):
                break


def print_welcome(*, colour_enabled: bool, stream: TextIO | None = None) -> None:
    out = stream or sys.stdout
    text = t("welcome_banner")
    if colour_enabled:
        out.write(f"{CYAN}{text}{RESET}\n")
    else:
        out.write(f"{text}\n")
    out.flush()
