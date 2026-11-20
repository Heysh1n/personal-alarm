"""Audio playback (speaker-test) and WirePlumber volume control (wpctl)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .config import AlarmConfig


@dataclass(frozen=True)
class AudioStatus:
    """Snapshot of audio controller state and available system tools."""

    speaker_test_available: bool
    wpctl_available: bool
    is_testing: bool
    is_ringing: bool
    current_vol: int
    active_freq_hz: int | None


class AudioController:
    """Manages sine-wave playback via speaker-test and volume via wpctl.

    Guarantees clean termination of child speaker-test processes and volume
    restoration to `config.restore_vol` (default 50%) whenever stopped or cleaned up.
    """

    def __init__(self, config: AlarmConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._is_testing = False
        self._is_ringing = False
        self._current_vol = config.restore_vol
        self._active_freq_hz: int | None = None

        self._speaker_test_bin = shutil.which("speaker-test")
        self._wpctl_bin = shutil.which("wpctl")

    @property
    def speaker_test_available(self) -> bool:
        return self._speaker_test_bin is not None

    @property
    def wpctl_available(self) -> bool:
        return self._wpctl_bin is not None

    def get_status(self) -> AudioStatus:
        with self._lock:
            return AudioStatus(
                speaker_test_available=self.speaker_test_available,
                wpctl_available=self.wpctl_available,
                is_testing=self._is_testing,
                is_ringing=self._is_ringing,
                current_vol=self._current_vol,
                active_freq_hz=self._active_freq_hz,
            )

    def _run_wpctl(self, args: list[str]) -> bool:
        if not self._wpctl_bin:
            return False
        cmd = [self._wpctl_bin, *args]
        try:
            res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            return res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def unmute(self) -> bool:
        """Ensure the configured audio sink is unmuted."""
        return self._run_wpctl(["set-mute", self._config.audio_sink, "0"])

    def set_volume(self, percent: int) -> bool:
        """Set audio sink volume in percent (0..150)."""
        clamped = max(0, min(150, int(percent)))
        ok = self._run_wpctl(["set-volume", self._config.audio_sink, f"{clamped}%"])
        with self._lock:
            self._current_vol = clamped
        return ok

    def restore_volume(self) -> bool:
        """Reset sink volume to configured restore_vol (default 50%)."""
        return self.set_volume(self._config.restore_vol)

    def _spawn_speaker_test(self, freq_hz: int) -> subprocess.Popen[bytes] | None:
        if not self._speaker_test_bin:
            return None
        cmd = [
            self._speaker_test_bin,
            "-t",
            "sine",
            "-f",
            str(int(freq_hz)),
            "-c",
            "2",
        ]
        try:
            return subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return None

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

    def emergency_stop_process(self) -> None:
        """Signal-handler safe immediate termination of any active speaker-test process."""
        self._stop_event.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    pass

    def stop_all(self, restore_vol: bool = True) -> None:
        """Stop any active sound test or siren and optionally restore volume."""
        worker: threading.Thread | None = None
        proc: subprocess.Popen[bytes] | None = None

        with self._lock:
            self._stop_event.set()
            worker = self._worker
            proc = self._proc
            self._proc = None

        self._terminate_proc(proc)

        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.5)

        with self._lock:
            if self._proc is not None:
                self._terminate_proc(self._proc)
                self._proc = None
            self._worker = None
            self._is_testing = False
            self._is_ringing = False
            self._active_freq_hz = None

        if restore_vol:
            self.restore_volume()

    def test_sound(
        self,
        freq_hz: int,
        duration_sec: float | None = None,
        on_finish: Callable[[bool], None] | None = None,
    ) -> bool:
        """Play a short sine-wave test tone (default 2s) and restore volume afterwards.

        `on_finish(completed_naturally: bool)` is invoked when the test ends.
        """
        if not self.speaker_test_available:
            return False

        self.stop_all(restore_vol=False)
        duration = self._config.test_sound_duration_sec if duration_sec is None else max(0.2, duration_sec)
        stop_event = threading.Event()

        def _worker() -> None:
            completed_naturally = False
            try:
                self.unmute()
                self.set_volume(self._config.test_sound_volume)
                proc = self._spawn_speaker_test(freq_hz)
                with self._lock:
                    self._proc = proc
                if proc is not None:
                    interrupted = stop_event.wait(timeout=duration)
                    completed_naturally = not interrupted
            finally:
                with self._lock:
                    is_current = self._stop_event is stop_event
                    proc_to_kill = self._proc if is_current else None
                    if is_current:
                        self._proc = None
                        self._is_testing = False
                        self._active_freq_hz = None
                self._terminate_proc(proc_to_kill)
                if is_current:
                    self.restore_volume()
                if on_finish is not None:
                    try:
                        on_finish(completed_naturally)
                    except Exception:
                        pass

        with self._lock:
            self._stop_event = stop_event
            self._is_testing = True
            self._is_ringing = False
            self._active_freq_hz = int(freq_hz)
            thread = threading.Thread(target=_worker, name="alarm-sound-test", daemon=True)
            self._worker = thread
            thread.start()
        return True

    def stop_test(self) -> None:
        """Stop an active sound test early and restore volume."""
        if self.get_status().is_testing:
            self.stop_all(restore_vol=True)

    def start_siren(
        self,
        freq_hz: int,
        on_volume_change: Callable[[int], None] | None = None,
    ) -> bool:
        """Start siren with stepped volume ramp from start_vol to max_vol."""
        self.stop_all(restore_vol=False)
        stop_event = threading.Event()

        start_vol = self._config.start_vol
        max_vol = self._config.max_vol
        step_vol = self._config.step_vol
        step_sec = self._config.step_sec

        def _notify_vol(vol: int) -> None:
            if on_volume_change is not None:
                try:
                    on_volume_change(vol)
                except Exception:
                    pass

        def _worker() -> None:
            try:
                current_vol = start_vol
                self.unmute()
                self.set_volume(current_vol)
                _notify_vol(current_vol)

                proc = self._spawn_speaker_test(freq_hz)
                with self._lock:
                    self._proc = proc

                while not stop_event.is_set():
                    # Restart speaker-test if it exited prematurely while alarm is ringing
                    with self._lock:
                        active_proc = self._proc
                    if self.speaker_test_available and (
                        active_proc is None or active_proc.poll() is not None
                    ):
                        new_proc = self._spawn_speaker_test(freq_hz)
                        with self._lock:
                            self._proc = new_proc

                    if stop_event.wait(timeout=step_sec):
                        break

                    if current_vol < max_vol:
                        current_vol = min(max_vol, current_vol + step_vol)
                        self.set_volume(current_vol)
                        _notify_vol(current_vol)
            finally:
                with self._lock:
                    is_current = self._stop_event is stop_event
                    proc_to_kill = self._proc if is_current else None
                    if is_current:
                        self._proc = None
                        self._is_ringing = False
                        self._active_freq_hz = None
                self._terminate_proc(proc_to_kill)
                if is_current:
                    self.restore_volume()

        with self._lock:
            self._stop_event = stop_event
            self._is_ringing = True
            self._is_testing = False
            self._active_freq_hz = int(freq_hz)
            self._current_vol = start_vol
            thread = threading.Thread(target=_worker, name="alarm-siren", daemon=True)
            self._worker = thread
            thread.start()
        return self.speaker_test_available

    def stop_siren(self) -> None:
        """Stop the ringing siren and reset volume to restore_vol (50%)."""
        self.stop_all(restore_vol=True)

    def cleanup(self) -> None:
        """Idempotent full cleanup: kill speaker-test and reset volume to restore_vol."""
        self.stop_all(restore_vol=True)
