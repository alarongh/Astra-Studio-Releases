from __future__ import annotations

import ast
import json
import keyword
import os
import shutil
from pathlib import Path
import subprocess
import sys
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import pytest

from core.python_dependencies import (
    IMPORT_PROBE_CODE, MUTATING_PIP_ACTIONS, normalized_import_names, parse_import_probe,
)
from core.python_environment import detect_project_environment
from core.python_library_registry import extract_python_imports, is_standard_module


ROOT = Path(__file__).resolve().parents[1]


def load_methods(*names, **extra):
    """Exercise actual controller functions without creating a real user project."""
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AstraStudio")
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(methods) == len(names)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *methods], type_ignores=[])
    namespace = dict(
        Path=Path, json=json, keyword=keyword,
        detect_project_environment=detect_project_environment,
        python_command=lambda: ("/global/python", []),
        normalized_import_names=normalized_import_names, parse_import_probe=parse_import_probe,
        IMPORT_PROBE_CODE=IMPORT_PROBE_CODE, MUTATING_PIP_ACTIONS=MUTATING_PIP_ACTIONS,
        extract_python_imports=extract_python_imports, is_standard_module=is_standard_module,
    )
    namespace.update(extra)
    exec(compile(ast.fix_missing_locations(module), "<controller-under-test>", "exec"), namespace)
    return namespace


def controller(root):
    names = ("_resolved_project_python_override", "_active_python_command", "_python_package_manager_command", "_quality_python_executable")
    namespace = load_methods(*names)
    result = SimpleNamespace(project_main_folder=root, project_python_interpreter="", _python_project_root=lambda *_: root)
    for name in names:
        setattr(result, name, MethodType(namespace[name], result))
    return result


def local_python(root):
    path = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    return path


@pytest.mark.parametrize("action", ["install", "uninstall", "download", "wheel"])
def test_clean_project_cannot_mutate_global_python(tmp_path, action):
    ui = controller(tmp_path)
    assert ui._python_package_manager_command([action, "requests"]) == (None, [])
    assert ui._quality_python_executable(tmp_path / "main.py") is None


def test_missing_selected_interpreter_does_not_fall_back_even_with_venv(tmp_path):
    local_python(tmp_path)
    ui = controller(tmp_path)
    ui.project_python_interpreter = "deleted environment/bin/python"
    assert ui._active_python_command() == (None, [])
    assert ui._python_package_manager_command(["install", "requests"]) == (None, [])


def test_read_only_global_inspection_is_still_available(tmp_path):
    ui = controller(tmp_path)
    program, arguments = ui._python_package_manager_command(["list"])
    assert program
    assert "list" in arguments


def test_project_install_preserves_unicode_and_space_paths_as_one_argument(tmp_path):
    root = tmp_path / "Проект с пробелом"
    root.mkdir()
    python = local_python(root)
    ui = controller(root)
    program, arguments = ui._python_package_manager_command(["install", "requests>=2"])
    if "--python" in arguments:
        assert arguments[arguments.index("--python") + 1] == str(python)
    else:
        assert program == str(python)
        assert "-I" in arguments
    assert arguments[-1] == "requests>=2"
    assert ui._quality_python_executable(root / "main.py") == str(python)


def test_pip_fallback_runs_isolated_from_project_modules(tmp_path):
    python = local_python(tmp_path)
    ui = controller(tmp_path)
    with patch("core.python_environment.shutil.which", return_value=None):
        program, arguments = ui._python_package_manager_command(["install", "rich"])
    assert program == str(python)
    assert arguments == ["-I", "-m", "pip", "install", "rich"]


def test_partial_environment_recovery_preserves_files_and_second_click_does_not_reinstall(tmp_path):
    if not shutil.which("uv"):
        pytest.skip("uv recovery command is checked when uv is available")
    root = tmp_path / "Частичный проект с пробелами"
    (root / ".venv").mkdir(parents=True)
    preserved = root / ".venv" / "user-note.txt"
    preserved.write_text("keep me", encoding="utf-8")
    calls = []
    namespace = load_methods(
        "create_project_python_environment",
        python_command=lambda: (sys.executable, []), can_write_to_directory=lambda _: True,
        QMessageBox=SimpleNamespace(warning=lambda *_: None, information=lambda *_: None),
    )
    ui = SimpleNamespace(
        _project_tools_trusted=lambda **_: True,
        _python_project_root=lambda *_: root, _resolved_project_python_override=lambda *_: None,
        _refresh_python_environment_status=lambda: None,
        bottom_tabs=SimpleNamespace(setCurrentIndex=lambda _: None),
        output_console=SimpleNamespace(appendPlainText=lambda _: None),
        _safe_command_preview=lambda program, args: " ".join([program, *args]),
        _start_process_task=lambda *args: calls.append(args) or object(),
    )
    create = MethodType(namespace["create_project_python_environment"], ui)
    assert create()
    program, arguments = calls[0][2:4]
    assert "--allow-existing" in arguments
    assert "--no-python-downloads" in arguments
    assert "--clear" not in arguments and "--seed" not in arguments
    completed = subprocess.run(
        [program, *arguments], cwd=root, capture_output=True, text=True, timeout=15,
        env=dict(os.environ, UV_CACHE_DIR=str(tmp_path / "uv-cache"), UV_OFFLINE="1"),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert preserved.read_text(encoding="utf-8") == "keep me"
    assert detect_project_environment(root).python_executable
    assert create() is False
    assert len(calls) == 1


def test_explicit_interpreter_is_used_without_shell_interpolation(tmp_path):
    python = tmp_path / "Python выбранный"
    python.write_bytes(b"")
    ui = controller(tmp_path)
    ui.project_python_interpreter = python.name
    program, arguments = ui._python_package_manager_command(["install", "rich"])
    assert program
    assert str(python) in [program, *arguments]


def test_probe_handles_real_present_and_missing_packages_without_installing(tmp_path):
    missing = "astra_missing_dependency_83468723"
    completed = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE_CODE, json.dumps(["json", missing])],
        cwd=tmp_path, capture_output=True, text=True, timeout=8, check=True,
    )
    assert parse_import_probe(completed.stdout, ["json", missing]) == {"json": True, missing: False}


@pytest.mark.parametrize("output", ["", "network error", '{}', '{"schema_version":1,"available":{}}', '{"schema_version":1,"available":{"json":"false"}}'])
def test_probe_failure_is_never_interpreted_as_missing(output):
    with pytest.raises(ValueError):
        parse_import_probe(output, ["json"])


def test_probe_preserves_explicit_absence_and_tolerates_startup_notice():
    assert parse_import_probe('startup notice\n{"schema_version":1,"available":{"json":false}}', ["json"]) == {"json": False}
    assert normalized_import_names(["json.decoder", "json", "a-b", "", "urllib.request"]) == ["json", "urllib"]


def preflight_controller(tmp_path):
    names = (
        "_ensure_python_imports_before_run", "_missing_python_imports_from_code",
        "_python_project_root", "_project_root_for_source", "_find_upwards",
        "_python_dependency_key",
    )
    namespace = load_methods(*names)
    probes, installs = [], []
    editor = SimpleNamespace(toPlainText=lambda: "import requests\n")
    ui = SimpleNamespace(
        project_main_folder=tmp_path,
        python_auto_install_enabled=True, python_install_always_ask=False,
        _project_tools_trusted=lambda **_: True,
        python_unknown_auto_install_enabled=False, ignored_missing_modules=set(),
        _active_python_command=lambda *_: ("python", []),
        _local_python_module_exists=lambda *_: False, current_editor=lambda: editor,
        _start_python_import_probe=lambda *a: probes.append(a),
        _run_pip_for_records=lambda *a, **kw: installs.append((a, kw)),
        _python_package_record=lambda name: {"import": name, "package": name, "safe": True},
        output_console=SimpleNamespace(appendPlainText=lambda *_: None),
    )
    for name in names:
        setattr(ui, name, MethodType(namespace[name], ui))
    return ui, probes, installs


def test_run_preflight_is_async_and_never_installs_before_probe(tmp_path):
    ui, probes, installs = preflight_controller(tmp_path)
    source = tmp_path / "main.py"
    assert ui._ensure_python_imports_before_run("import requests\n", source) is False
    assert len(probes) == 1
    assert not installs
    ui._python_import_preflight = {"key": ui._python_dependency_key(source), "path": str(source), "source_code": "import requests\n", "status": {"requests": True}}
    assert ui._ensure_python_imports_before_run("import requests\n", source) is True
    assert len(probes) == 1
    assert not installs
    assert ui._python_import_preflight is None


def test_real_missing_dependency_installs_in_the_probed_source_context(tmp_path):
    ui, probes, installs = preflight_controller(tmp_path)
    source = tmp_path / "Подпроект" / "main.py"
    ui._python_import_preflight = {"key": ui._python_dependency_key(source), "path": str(source), "source_code": "import requests\n", "status": {"requests": False}}
    assert ui._ensure_python_imports_before_run("import requests\n", source) is False
    assert not probes
    assert len(installs) == 1
    assert installs[0][1]["source_path"] == source


def test_explicit_run_of_untrusted_project_skips_automatic_dependency_execution(tmp_path):
    ui, probes, installs = preflight_controller(tmp_path)
    ui._project_tools_trusted = lambda **_: False
    assert ui._ensure_python_imports_before_run("import requests\n", tmp_path / "main.py") is True
    assert not probes
    assert not installs


@pytest.mark.parametrize("operation,confirm", [("preflight", False), ("probe", True), ("install", True), ("create_environment", True)])
def test_attached_project_dependency_actions_use_source_root_trust(tmp_path, operation, confirm):
    primary = tmp_path / "trusted primary"
    attached = tmp_path / "Недоверенный attached"
    primary.mkdir()
    (attached / "src").mkdir(parents=True)
    (attached / "pyproject.toml").write_text('[project]\nname="attached"\n', encoding="utf-8")
    source = attached / "src" / "main.py"
    ui, probes, installs = preflight_controller(primary)
    trust_calls = []

    def trusted(*, confirm=False, root=None):
        trust_calls.append((confirm, root))
        return root == primary

    ui._project_tools_trusted = trusted
    ui.task_manager = SimpleNamespace(has_active_task=lambda: False)
    if operation == "preflight":
        # Explicit Run can proceed, but automatic dependency tools are skipped.
        assert ui._ensure_python_imports_before_run("import requests\n", source) is True
    else:
        names = {
            "probe": "_start_python_import_probe",
            "install": "_ensure_package_install_environment",
            "create_environment": "create_project_python_environment",
        }
        method = load_methods(names[operation])[names[operation]]
        if operation == "probe":
            assert method(ui, ["requests"], "libraries", source) is False
        elif operation == "install":
            assert method(ui, source_path=source) is False
        else:
            assert method(ui, source_path=source) is False
    assert trust_calls == [(confirm, attached.resolve())]
    assert not probes and not installs


def test_timeout_cancels_only_the_current_probe_and_does_not_retry():
    namespace = load_methods("_expire_python_import_probe")
    cancelled, output = [], []
    ui = SimpleNamespace(active_task_context={"task_id": "probe_2"}, output_console=SimpleNamespace(appendPlainText=output.append), task_manager=SimpleNamespace(has_active_task=lambda: True, cancel_current_task=lambda: cancelled.append(True)))
    namespace["_expire_python_import_probe"](ui, "probe_1")
    assert not cancelled
    namespace["_expire_python_import_probe"](ui, "probe_2")
    assert cancelled == [True]
    assert "не переустанавливались" in output[0]


def test_probe_output_is_bounded_before_process_exit():
    namespace = load_methods("_on_task_output")
    cancelled, messages = [], []
    ui = SimpleNamespace(
        active_task_context={"task_id": "probe", "mode": "python_import_probe"},
        task_manager=SimpleNamespace(cancel_current_task=lambda: cancelled.append(True)),
        output_console=SimpleNamespace(appendPlainText=messages.append),
    )
    namespace["_on_task_output"](ui, "probe", "x" * 200_000, "stdout")
    namespace["_on_task_output"](ui, "probe", "y" * 200_000, "stdout")
    assert len("".join(ui.active_task_context["stdout_chunks"])) == 128 * 1024
    assert cancelled == [True]
    assert len(messages) == 1


def test_windows_update_check_is_read_only():
    namespace = load_methods("check_tool_updates")
    calls = []
    namespace["check_tool_updates"](SimpleNamespace(_start_installer_diagnostic_task=lambda *args: calls.append(args)))
    script = calls[0][2]
    assert "list --id $item.Id --exact --upgrade-available" in script
    assert "& $winget.Source upgrade" not in script


def test_real_async_probe_keeps_event_loop_responsive_without_cwd_module_execution(tmp_path):
    from PySide6.QtCore import QEventLoop, QTimer
    from core.task_manager import TaskManager, ProcessTaskSpec

    root = tmp_path / "Проект с пробелами"
    root.mkdir()
    (root / "project_only_module.py").write_text("VALUE = 42\n", encoding="utf-8")
    marker = root / "executed.txt"
    (root / "json.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n", encoding="utf-8")
    names = ("_start_python_import_probe", "_on_task_output", "_expire_python_import_probe", "_stop_python_import_probe_timer")
    namespace = load_methods(*names, QTimer=QTimer)
    # A deliberately slow interpreter probe models a cold disk/interpreter.
    namespace["IMPORT_PROBE_CODE"] = "import time; time.sleep(0.15)\n" + IMPORT_PROBE_CODE
    manager = TaskManager()
    loop = QEventLoop()
    ticks, finished = [], []
    ui = SimpleNamespace(
        _project_tools_trusted=lambda **_: True,
        project_main_folder=root,
        _active_python_command=lambda *_: (sys.executable, []),
        _python_project_root=lambda *_: root,
        _python_dependency_key=lambda *_: (str(root), sys.executable, ()),
        task_manager=manager, active_task_context={},
        _append_task_text=lambda *_: None,
    )
    for name in names:
        setattr(ui, name, MethodType(namespace[name], ui))

    def start_task(task_id, title, program, arguments, workdir, context):
        ui.active_task_context = dict(context, task_id=task_id)
        return manager.start_process(ProcessTaskSpec(task_id, title, program, arguments, str(workdir)))

    ui._start_process_task = start_task
    manager.taskOutput.connect(ui._on_task_output)

    def done(task_id, exit_code, cancelled):
        finished.append((exit_code, cancelled, "".join(ui.active_task_context.get("stdout_chunks") or [])))
        ui._stop_python_import_probe_timer(ui.active_task_context)
        ui.active_task_context = {}
        loop.quit()

    manager.taskFinished.connect(done)
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(5000)
    assert ui._start_python_import_probe(["json", "project_only_module"], "libraries")
    loop.exec()
    timer.stop()
    deadline.stop()
    manager.cancel_and_wait()
    assert finished and finished[0][:2] == (0, False)
    assert parse_import_probe(finished[0][2], ["json", "project_only_module"]) == {"json": True, "project_only_module": False}
    assert not marker.exists()
    assert len(ticks) >= 3


def test_window_runs_installed_dependency_twice_without_reinstallation(monkeypatch, tmp_path):
    from PySide6.QtCore import QEventLoop, QTimer, QProcess
    from PySide6.QtWidgets import QApplication
    import main

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main, "app_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(main, "default_builds_dir", lambda: tmp_path / "builds")
    monkeypatch.setattr(main.AstraStudio, "start_terminal", lambda self: None)
    monkeypatch.setattr(main.LspManager, "ensure_server", lambda *args: None)
    window = main.AstraStudio()
    try:
        window.project_python_interpreter = sys.executable
        source = window.workspace_dir / "dependency_probe_test.py"
        source.write_text('import PySide6\nprint("dependency-run-ok")\n', encoding="utf-8")
        window.open_file(source)
        started = []
        window.task_manager.taskStarted.connect(lambda task_id, title: started.append(task_id))
        for _ in range(2):
            loop = QEventLoop()
            timer = QTimer()
            timer.setInterval(15)

            def check_finished():
                if "dependency-run-ok" in window.output_console.toPlainText() and not window.task_manager.has_active_task() and window.run_process is not None and window.run_process.state() == QProcess.ProcessState.NotRunning:
                    loop.quit()

            timer.timeout.connect(check_finished)
            deadline = QTimer()
            deadline.setSingleShot(True)
            deadline.timeout.connect(loop.quit)
            timer.start()
            deadline.start(8000)
            window.run_code()
            loop.exec()
            timer.stop()
            deadline.stop()
            assert "dependency-run-ok" in window.output_console.toPlainText()
            assert window.run_process is not None and window.run_process.exitCode() == 0
        assert len([task for task in started if task.startswith("python_import_probe_")]) == 2
        assert not any(task.startswith("pip_") for task in started)
    finally:
        window.close()
        app.processEvents()
