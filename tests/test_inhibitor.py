"""Unit tests for alarm_tui.inhibitor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from alarm_tui.inhibitor import SleepInhibitor


def test_inhibitor_graceful_when_binary_missing() -> None:
    with patch("alarm_tui.inhibitor.shutil.which", return_value=None):
        inhibitor = SleepInhibitor()
        assert inhibitor.available is False
        assert inhibitor.active is False
        assert inhibitor.acquire() is False
        assert inhibitor.active is False
        inhibitor.release()  # must not raise


def test_inhibitor_acquire_and_release() -> None:
    fake_proc = MagicMock()
    fake_proc.pid = 424242
    fake_proc.poll.return_value = None

    with (
        patch("alarm_tui.inhibitor.shutil.which", return_value="/usr/bin/systemd-inhibit"),
        patch("alarm_tui.inhibitor.subprocess.Popen", return_value=fake_proc) as mock_popen,
        patch("alarm_tui.inhibitor.os.killpg") as mock_killpg,
    ):
        inhibitor = SleepInhibitor()
        assert inhibitor.available is True
        assert inhibitor.acquire() is True
        assert inhibitor.active is True

        # Second acquire is a no-op while active
        assert inhibitor.acquire() is True
        assert mock_popen.call_count == 1

        args = mock_popen.call_args[0][0]
        assert args[0] == "/usr/bin/systemd-inhibit"
        assert "--what=sleep:idle" in args
        assert "--who=alarm-tui" in args
        assert "--why=Alarm active" in args
        assert "--mode=block" in args
        assert args[-2:] == ["sleep", "infinity"]

        inhibitor.release()
        assert mock_killpg.called
        assert inhibitor.active is False
