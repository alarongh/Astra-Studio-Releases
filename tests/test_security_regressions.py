from __future__ import annotations

import base64
from pathlib import Path
import os
import subprocess
import sys

import pytest

from core.command_launch import powershell_syntax_arguments, windows_tool_command
from core.file_safety import directory_is_writable, is_project_text_path, write_project_text
from core.project_doctor import _is_writable_directory
from core.project_trust import ProjectTrustStore


@pytest.mark.parametrize("name", [".astral_write_test.tmp", ".astra_doctor_write_test.tmp"])
@pytest.mark.parametrize("linked", [False, True])
def test_write_probes_preserve_existing_files_and_links(tmp_path, name, linked):
    from main import can_write_to_directory

    root = tmp_path / "проект с пробелами"
    root.mkdir()
    victim = tmp_path / "untouched.txt"
    victim.write_text("KEEP", encoding="utf-8")
    old_probe = root / name
    if linked:
        try:
            old_probe.symlink_to(victim)
        except OSError:
            pytest.skip("Host does not permit symlinks")
    else:
        old_probe.write_text("KEEP", encoding="utf-8")
    before = set(root.iterdir())
    assert can_write_to_directory(root)
    assert _is_writable_directory(root)
    assert victim.read_text() == "KEEP"
    assert old_probe.read_text() == "KEEP"
    assert old_probe.is_symlink() == linked
    assert set(root.iterdir()) == before


def test_probe_creation_and_failure_preserve_legacy_file(tmp_path, monkeypatch):
    from main import can_write_to_directory
    import core.file_safety as safety

    root = tmp_path / "new"
    assert not directory_is_writable(root)
    assert can_write_to_directory(root)
    sentinel = root / ".astra_doctor_write_test.tmp"
    sentinel.write_text("KEEP")

    def denied(**_kwargs):
        raise PermissionError("test ACL denial")

    monkeypatch.setattr(safety.tempfile, "TemporaryFile", denied)
    assert not _is_writable_directory(root)
    assert sentinel.read_text() == "KEEP"


def test_bulk_replace_excludes_external_links_and_accepts_explicit_roots(tmp_path):
    root = tmp_path / "project"
    attached = tmp_path / "attached"
    root.mkdir()
    attached.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("KEEP")
    link = root / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Host does not permit symlinks")
    assert not is_project_text_path(link, [root])
    with pytest.raises(OSError):
        write_project_text(link, "CHANGED", "utf-8", [root])
    assert outside.read_text() == "KEEP"
    owned = attached / "file.py"
    owned.write_text("old")
    assert not is_project_text_path(owned, [root])
    write_project_text(owned, "new", "utf-8", [root, attached])
    assert owned.read_text() == "new"
    assert not list(attached.glob(".astra-replace-*"))


def test_atomic_bulk_replace_does_not_change_external_hardlink(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("KEEP")
    target = root / "owned.py"
    try:
        os.link(outside, target)
    except OSError:
        pytest.skip("Host does not permit hardlinks")
    write_project_text(target, "new", "utf-8", [root])
    assert target.read_text() == "new"
    assert outside.read_text() == "KEEP"


def test_bulk_replace_preserves_cp1251_encoding_and_permissions(tmp_path):
    target = tmp_path / "legacy.py"
    target.write_bytes("старый текст".encode("cp1251"))
    target.chmod(0o600)
    write_project_text(target, "новый текст", "cp1251", [tmp_path])
    assert target.read_bytes() == "новый текст".encode("cp1251")
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


def test_project_trust_is_exact_persistent_and_revocable(tmp_path):
    policy = tmp_path / "user-data" / "trusted_projects.json"
    root = tmp_path / "project"
    child = root / "other"
    child.mkdir(parents=True)
    (root / "astral.project.json").write_text('{"trusted": true}')
    store = ProjectTrustStore(policy)
    assert not store.is_trusted(root)
    store.set_trusted(root)
    assert ProjectTrustStore(policy).is_trusted(root)
    assert not store.is_trusted(child)
    store.set_trusted(root, False)
    assert not ProjectTrustStore(policy).is_trusted(root)
    assert not list(policy.parent.glob(".astra-trust-*"))


@pytest.mark.parametrize("content", ["broken", "[]", '{"schema_version":1,"trusted_roots":"all"}'])
def test_malformed_trust_store_fails_closed(tmp_path, content):
    policy = tmp_path / "trust.json"
    policy.write_text(content)
    assert not ProjectTrustStore(policy).is_trusted(tmp_path)


def test_trust_does_not_transfer_to_replacement_symlink_on_reload(tmp_path):
    policy = tmp_path / "trust.json"
    original = tmp_path / "approved"
    unrelated = tmp_path / "unrelated"
    original.mkdir()
    unrelated.mkdir()
    store = ProjectTrustStore(policy)
    store.set_trusted(original)
    original.rename(tmp_path / "old-approved")
    try:
        original.symlink_to(unrelated, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit symlinks")
    for instance in (store, ProjectTrustStore(policy)):
        assert not instance.is_trusted(unrelated)
        assert not instance.is_trusted(original)


def test_python_check_does_not_launch_untrusted_project_interpreter(tmp_path):
    from types import SimpleNamespace
    from main import AstraStudio

    root = tmp_path / "project"
    python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("not executed")
    source = root / "check.py"
    source.write_text("answer = 42")
    launched = []
    window = SimpleNamespace(
        current_editor=lambda: SimpleNamespace(language_name="Python"),
        task_manager=SimpleNamespace(has_active_task=lambda: False),
        _write_current_code_for_execution=lambda: source,
        bottom_tabs=SimpleNamespace(setCurrentIndex=lambda _i: None),
        output_console=SimpleNamespace(clear=lambda: None, appendPlainText=lambda _text: None),
        _python_project_root=lambda _path: root,
        _resolved_project_python_override=lambda _root: None,
        _project_tools_trusted=lambda **_: False,
        _active_python_command=lambda _path: (str(python), []),
        _start_process_task=lambda *args: launched.append(args),
        project_main_folder=root,
    )
    assert AstraStudio.compile_code(window) is False
    assert not launched


def test_project_config_cannot_inherit_trust_by_pointing_at_approved_root(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import main

    data = tmp_path / "user-data"
    internal = data / "workspace"
    internal.mkdir(parents=True)
    foreign = tmp_path / "foreign-project"
    foreign.mkdir()
    config = foreign / "astral.project.json"
    config.write_text('{"mainFolder":"approved-elsewhere"}')
    store = ProjectTrustStore(data / "trust.json")
    monkeypatch.setattr(main, "app_data_dir", lambda: data)
    window = SimpleNamespace(project_main_folder=internal, current_project_config_path=config,
                             _project_trust_store=store)
    assert not main.AstraStudio._project_tools_trusted(window)
    store.set_trusted(foreign)
    assert main.AstraStudio._project_tools_trusted(window)
    external = tmp_path / "external-source"
    external.mkdir()
    assert not main.AstraStudio._project_tools_trusted(window, root=external)


@pytest.mark.parametrize("shadow_package", [False, True])
def test_python_syntax_check_ignores_project_modules_and_pythonpath(tmp_path, shadow_package):
    root = tmp_path / "проект с пробелами"
    root.mkdir()
    marker = tmp_path / "marker"
    payload = f"from pathlib import Path;Path({str(marker)!r}).write_text('bad')"
    if shadow_package:
        (root / "py_compile").mkdir()
        (root / "py_compile" / "__init__.py").write_text("")
        (root / "py_compile" / "__main__.py").write_text(payload)
    else:
        (root / "py_compile.py").write_text(payload)
    source = root / "valid.py"
    source.write_text("answer = 42\n")
    result = subprocess.run([sys.executable, "-I", "-S", "-m", "py_compile", str(source)],
                            cwd=root, env={**os.environ, "PYTHONPATH": str(root)}, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    source.write_text("invalid syntax here !!!\n")
    result = subprocess.run([sys.executable, "-I", "-S", "-m", "py_compile", str(source)],
                            cwd=root, capture_output=True)
    assert result.returncode != 0
    assert b"SyntaxError" in result.stderr


def test_standard_node_shim_bypasses_cmd_and_preserves_arguments(tmp_path, monkeypatch):
    import core.command_launch as launch

    entry = tmp_path / "node_modules" / "prettier" / "bin" / "prettier.cjs"
    entry.parent.mkdir(parents=True)
    entry.write_text("// test")
    shim = tmp_path / "prettier.cmd"
    shim.write_text('@echo off\r\n"%_prog%" "%dp0%\\node_modules\\prettier\\bin\\prettier.cjs" %*\r\n')
    monkeypatch.setattr(launch.shutil, "which", lambda _name: "node.exe")
    args = ["--stdin-filepath", 'проект/a&b%X%!^.js', 'quote"in-data']
    program, actual = windows_tool_command(str(shim), args)
    assert program == "node.exe"
    assert actual == [str(entry.resolve()), *args]


@pytest.mark.parametrize("unsafe", ['name%PATH%.js', 'name!X!.js', 'x"y', 'x\ny', 'x\ry', 'x\0y'])
def test_nonstandard_batch_rejects_unrepresentable_data(tmp_path, unsafe):
    script = tmp_path / "custom.cmd"
    script.write_text("@echo off\n")
    with pytest.raises(ValueError):
        windows_tool_command(str(script), [unsafe])


def test_batch_arguments_are_always_quoted_and_delayed_expansion_disabled(tmp_path):
    from types import SimpleNamespace
    from core.command_launch import configure_process_command
    script = tmp_path / "custom.cmd"
    script.write_text("@echo off\n")
    _program, args = windows_tool_command(str(script), ["a&b.js", "space name", "a^b", "(data)"])
    assert args[:4] == ["/d", "/v:off", "/s", "/c"]
    assert '"a&b.js"' in args[-1]
    assert '"(data)"' in args[-1]
    recorded = {}
    process = SimpleNamespace(setProgram=lambda value: recorded.update(program=value),
                              setArguments=lambda value: recorded.update(args=value),
                              setNativeArguments=lambda value: recorded.update(native=value))
    configure_process_command(process, _program, args, windows=True)
    assert recorded["args"] == []
    assert recorded["native"] == " ".join(args[:4]) + " " + args[4]
    configure_process_command(process, "node.exe", ["literal&data"], windows=True)
    assert recorded["native"] == ""
    assert recorded["args"] == ["literal&data"]


def test_powershell_filename_is_data_and_parser_does_not_execute_source():
    path = "проект/a&b'; Write-Output 'not-code.ps1"
    args = powershell_syntax_arguments(path)
    assert args[:3] == ["-NoProfile", "-NonInteractive", "-EncodedCommand"]
    script = base64.b64decode(args[3]).decode("utf-16-le")
    assert path not in script
    assert base64.b64encode(path.encode()).decode() in script
    assert "::ParseFile(" in script
    assert "[scriptblock]::Create" not in script


def test_new_static_website_template_binds_only_loopback(tmp_path):
    from core.project_templates import create_project_from_template

    result = create_project_from_template(tmp_path / "website", "Website", "static-website", "4.0")
    assert "--bind 127.0.0.1" in result.template.commands["run"]
    assert "-I -m http.server" in result.template.commands["run"]


@pytest.mark.skipif(os.name != "nt", reason="Native Windows cmd argument round trip")
def test_windows_batch_round_trip_does_not_execute_filename_metacharacters(tmp_path):
    import json
    from PySide6.QtCore import QProcess
    from core.command_launch import configure_process_command
    recorder = tmp_path / "record.py"
    output = tmp_path / "args.json"
    recorder.write_text("import json,sys;from pathlib import Path;Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))")
    shim = tmp_path / "record.cmd"
    shim.write_text(f'@echo off\r\n"{sys.executable}" -I "{recorder}" %*\r\n')
    original = ["проект & folder/file.js", "a^b", "(data)", "C:\\trailing\\"]
    program, args = windows_tool_command(str(shim), [str(output), *original])
    process = QProcess()
    configure_process_command(process, program, args)
    process.start()
    assert process.waitForStarted(5000), process.errorString()
    assert process.waitForFinished(10000), process.errorString()
    assert process.exitCode() == 0, bytes(process.readAllStandardError())
    assert json.loads(output.read_text()) == original
