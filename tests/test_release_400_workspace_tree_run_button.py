from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest


def _window(monkeypatch, tmp_path: Path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    import main

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main, "app_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(main, "default_builds_dir", lambda: tmp_path / "builds")
    monkeypatch.setattr(main.AstraStudio, "start_terminal", lambda self: None)
    return app, main, main.AstraStudio()


def _wait_until(app, predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def test_internal_workspace_archives_old_language_examples(monkeypatch, tmp_path: Path):
    import main

    data_dir = tmp_path / "data"
    workspace = data_dir / "workspace"
    workspace.mkdir(parents=True)
    for filename, template in main.LEGACY_INTERNAL_WORKSPACE_EXAMPLES.items():
        (workspace / filename).write_text(template, encoding="utf-8")

    app, _main, window = _window(monkeypatch, tmp_path)

    assert not any((workspace / filename).exists() for filename in main.LEGACY_INTERNAL_WORKSPACE_EXAMPLES)
    backup = data_dir / "legacy_workspace_backup"
    assert {path.name for path in backup.iterdir()} == set(main.LEGACY_INTERNAL_WORKSPACE_EXAMPLES)
    assert {"example.py", "example.cpp", "Main.java", "index.html", "style.css", "script.js"}.issubset(
        {path.name for path in workspace.iterdir()}
    )
    window.close()
    app.processEvents()


def test_project_tree_shows_six_languages_and_neutral_files(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QTreeWidgetItem

    app, _main, window = _window(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    visible = {"app.py", "main.cpp", "Main.java", "app.js", "index.html", "style.css", "README.md", "config.json"}
    hidden = {"old.ts", "old.luau", "old.gd", "old.php", "old.ps1", "Old.cs", "old.sql"}
    for filename in visible | hidden:
        (project / filename).write_text("test", encoding="utf-8")

    parent = QTreeWidgetItem(["root"])
    window._add_path_to_tree(parent, project)
    shown = {
        Path((parent.child(index).data(0, 256) or {})["path"]).name
        for index in range(parent.childCount())
    }
    assert visible.issubset(shown)
    assert hidden.isdisjoint(shown)
    window.close()
    app.processEvents()


def test_project_tree_can_be_resized_wide_and_is_not_auto_hidden(monkeypatch, tmp_path: Path):
    app, _main, window = _window(monkeypatch, tmp_path)
    window.resize(2560, 1400)
    window.show()
    app.processEvents()

    assert window.project_panel.maximumWidth() > 10000
    window.main_splitter.setSizes([1000, 1200])
    app.processEvents()
    assert window.project_panel.width() >= 600

    window.tools_drawer.setVisible(True)
    window.resize(1600, 900)
    window._apply_responsive_layout()
    app.processEvents()
    assert window.project_panel.isVisible()
    assert window.project_panel.width() >= window.project_panel.minimumWidth()
    window.close()
    app.processEvents()


def test_run_button_replaces_play_with_stop_for_compilation_and_restores(monkeypatch, tmp_path: Path):
    app, _main, window = _window(monkeypatch, tmp_path)
    window.show()
    app.processEvents()

    started = window._start_process_task(
        "release_400_compile",
        "Идёт компиляция…",
        sys.executable,
        ["-c", "import time; time.sleep(5)"],
        tmp_path,
        {"mode": "compile", "language": "Python", "run_after": True, "indeterminate": True},
    )
    assert started is not None
    assert _wait_until(app, lambda: window.task_manager.has_active_task())
    assert window.btn_run.text().startswith("■")
    assert window.btn_run.isEnabled()

    window.toggle_run_code()
    assert _wait_until(app, lambda: not window.task_manager.has_active_task())
    assert window.btn_run.text().startswith("▶")
    assert window.btn_run.isEnabled()
    assert not window.btn_stop.isVisible()
    window.close()
    app.processEvents()


def test_release_identity_is_5_0():
    import main

    assert main.APP_VERSION == "Release 5.0"
    assert "Astra 5.0 — красно-синий" in main.SHORTCUT_ICON_OPTIONS
