from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from core.process_control import configure_process_group, request_process_stop, stop_process_and_wait


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(False)
    yield app


def _spin_until(predicate, timeout=4.0):
    app = QApplication.instance()
    assert app is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def _start_sleep_process():
    process = QProcess()
    configure_process_group(process)
    process.start(sys.executable, ["-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"])
    assert process.waitForStarted(3000)
    return process


def test_stop_timer_does_not_kill_an_immediate_replacement_run():
    from main import AstraStudio
    first = _start_sleep_process()
    second = None
    owner = SimpleNamespace(
        run_process=first,
        output_console=SimpleNamespace(appendPlainText=lambda _text: None),
        status_pill=SimpleNamespace(setText=lambda _text: None),
    )
    try:
        AstraStudio.stop_run_process(owner)
        assert _spin_until(lambda: first.state() == QProcess.ProcessState.NotRunning)
        second = _start_sleep_process()
        owner.run_process = second
        deadline = time.monotonic() + 1.4
        _spin_until(lambda: time.monotonic() >= deadline, timeout=2.0)
        assert second.state() == QProcess.ProcessState.Running
    finally:
        for process in (first, second):
            if process is not None and process.state() != QProcess.ProcessState.NotRunning:
                stop_process_and_wait(process)


def test_late_signals_from_old_run_do_not_change_current_run_state():
    from main import AstraStudio
    old, current = QProcess(), QProcess()
    # No console/status API is provided: an obsolete signal must return before
    # attempting to touch UI or drain the new process's streams.
    owner = SimpleNamespace(run_process=current)
    AstraStudio._read_run_stdout(owner, old)
    AstraStudio._read_run_stderr(owner, old)
    AstraStudio._run_process_start_failed(owner, "old program", old)
    AstraStudio._run_process_finished(owner, 1, QProcess.ExitStatus.CrashExit, old)
    assert owner.run_process is current


@pytest.mark.skipif(os.name == "nt", reason="Unix process session cancellation")
def test_stop_kills_descendant_that_ignores_term_even_after_parent_exits(tmp_path: Path):
    child_ready = tmp_path / "child.pid"
    heartbeat = tmp_path / "heartbeat"
    child_code = (
        "import os,signal,sys,time,pathlib\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "while True:\n"
        " pathlib.Path(sys.argv[2]).write_text(str(time.monotonic_ns()))\n"
        " time.sleep(0.02)\n"
    )
    parent_code = (
        "import pathlib,subprocess,sys,time; "
        f"p=subprocess.Popen([sys.executable,'-c',{child_code!r},{str(child_ready)!r},{str(heartbeat)!r}]); "
        "print(p.pid,flush=True); time.sleep(30)"
    )
    process = QProcess()
    configure_process_group(process)
    process.start(sys.executable, ["-u", "-c", parent_code])
    assert process.waitForStarted(3000)
    parent_pid = int(process.processId())
    child_pid = None
    try:
        assert _spin_until(lambda: child_ready.is_file() and heartbeat.is_file())
        child_pid = int(child_ready.read_text())
        initial_heartbeat = heartbeat.read_text()
        assert _spin_until(lambda: heartbeat.read_text() != initial_heartbeat)
        request_process_stop(process, delay_ms=100)
        assert _spin_until(lambda: process.state() == QProcess.ProcessState.NotRunning)

        deadline = time.monotonic() + 0.3
        assert _spin_until(lambda: time.monotonic() >= deadline)
        stopped_heartbeat = heartbeat.read_text()
        deadline = time.monotonic() + 0.15
        assert _spin_until(lambda: time.monotonic() >= deadline)
        assert heartbeat.read_text() == stopped_heartbeat
    finally:
        try:
            os.killpg(parent_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.waitForFinished(1500)


@pytest.mark.parametrize("deletion_order", ["child-first", "parent-first"])
def test_finished_run_callbacks_allow_deferred_qobject_destruction(tmp_path: Path, deletion_order):
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "run_lifetime.py"
    script.write_text(textwrap.dedent('''
        import gc,sys
        from pathlib import Path
        from types import SimpleNamespace
        sys.path.insert(0,sys.argv[1])
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtWidgets import QApplication,QWidget,QPlainTextEdit,QLabel
        from main import AstraStudio
        app=QApplication([])
        app.setQuitOnLastWindowClosed(False)
        class Owner(QWidget):
            _start_process=AstraStudio._start_process
            _read_run_stdout=AstraStudio._read_run_stdout
            _read_run_stderr=AstraStudio._read_run_stderr
            _run_process_finished=AstraStudio._run_process_finished
            _run_process_start_failed=AstraStudio._run_process_start_failed
            _append_to_output=AstraStudio._append_to_output
            def __init__(self):
                super().__init__()
                self.run_process=None
                self.last_run_language='JavaScript'
                self.last_run_source_path=None
                self.output_console=QPlainTextEdit(self)
                self.status_pill=QLabel(self)
            def _set_run_button_running(self,running): pass
            def _safe_command_preview(self,program,arguments): return program
            def statusBar(self): return SimpleNamespace(showMessage=lambda *args:None)
        for index in range(30):
            owner=Owner()
            owner._start_process(sys.executable,['-u','-c','print("final-output",flush=True)'],Path(sys.argv[1]))
            process=owner.run_process
            assert process.waitForStarted(5000)
            assert process.waitForFinished(5000)
            assert 'final-output' in owner.output_console.toPlainText()
            if sys.argv[2]=='child-first': process.deleteLater()
            else: owner.deleteLater()
            del owner,process
            gc.collect()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            app.processEvents()
            gc.collect()
        print('lifetime-ok',flush=True)
    '''), encoding="utf-8")
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    completed = subprocess.run(
        [sys.executable, "-X", "faulthandler", str(script), str(root), deletion_order],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "lifetime-ok" in completed.stdout
