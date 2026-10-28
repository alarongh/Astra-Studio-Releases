"""Stop only processes belonging to an Astra-owned process session on Unix."""
from __future__ import annotations

import os
import signal

from PySide6.QtCore import QProcess, QTimer


def configure_process_group(process: QProcess) -> None:
    if os.name != "nt":
        process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        process._astra_process_group = True


def signal_process(process: QProcess, *, force: bool = False) -> None:
    if process.state() == QProcess.ProcessState.NotRunning:
        return
    pid = int(process.processId())
    if os.name != "nt" and getattr(process, "_astra_process_group", False) and pid > 0:
        try:
            os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
            return
        except ProcessLookupError:
            return
        except OSError:
            # If the session could not be created, still stop its owned leader.
            pass
    if force:
        process.kill()
    else:
        process.terminate()


def request_process_stop(process: QProcess, delay_ms: int = 1200) -> None:
    """Capture this process/PID; a delayed kill must never target a later run."""
    pid = int(process.processId())
    owns_group = os.name != "nt" and getattr(process, "_astra_process_group", False) and pid > 0
    signal_process(process)

    def force_original_process() -> None:
        try:
            if owns_group:
                # A shell may already have exited while a descendant ignores
                # SIGTERM. Its session still needs to be stopped as a group.
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return
            if process.state() != QProcess.ProcessState.NotRunning and (pid == 0 or int(process.processId()) == pid):
                signal_process(process, force=True)
        except RuntimeError:
            # Its QObject parent may already have destroyed it during shutdown.
            pass

    QTimer.singleShot(delay_ms, force_original_process)


def stop_process_and_wait(process: QProcess, timeout_ms: int = 1200) -> None:
    pid = int(process.processId())
    owns_group = os.name != "nt" and getattr(process, "_astra_process_group", False) and pid > 0
    signal_process(process)
    finished = process.waitForFinished(max(0, int(timeout_ms)))
    if owns_group:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif not finished:
        process.kill()
    if not finished:
        process.waitForFinished(max(0, int(timeout_ms)))
