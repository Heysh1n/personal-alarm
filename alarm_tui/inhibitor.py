"""Sleep and idle inhibition via systemd-inhibit while an alarm is active."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading


class SleepInhibitor:
    """Holds a systemd-inhibit lock while an alarm is armed or ringing.

    Degrades gracefully when `systemd-inhibit` is unavailable on the host.
    """

    def __init__(
        self,
        who: str = "alarm-tui",
        why: str = "Alarm active",
        what: str = "sleep:idle",
    ) -> None:
        self._who = who
        self._why = why
        self._what = what
        self._bin = shutil.which("systemd-inhibit")
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[bytes] | None = None

    @property
    def available(self) -> bool:
        """Return True if systemd-inhibit is present in PATH."""
        return self._bin is not None

    @property
    def active(self) -> bool:
        """Return True if an inhibitor subprocess is currently running."""
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def acquire(self) -> bool:
        """Start systemd-inhibit lock; returns True if lock is active."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            if not self._bin:
                self._proc = None
                return False

            cmd = [
                self._bin,
                f"--what={self._what}",
                f"--who={self._who}",
                f"--why={self._why}",
                "--mode=block",
                "sleep",
                "infinity",
            ]
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except OSError:
                self._proc = None
                return False

    def _terminate_proc(self, proc: subprocess.Popen[bytes] | None) -> None:
        if proc is None:
            return
        try:
            if proc.poll() is not None:
                return
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                proc.terminate()
            try:
                proc.wait(timeout=0.5)
                return
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        except OSError:
            pass

    def emergency_stop(self) -> None:
        """Signal-handler safe immediate termination of the inhibitor process."""
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    pass

    def release(self) -> None:
        """Stop the systemd-inhibit subprocess if running."""
        with self._lock:
            proc = self._proc
            self._proc = None
        self._terminate_proc(proc)

    def cleanup(self) -> None:
        """Idempotent cleanup alias for release()."""
        self.release()
