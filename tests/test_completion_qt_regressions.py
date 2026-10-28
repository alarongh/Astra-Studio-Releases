from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from core.language_completion import text_offset_to_utf16
from main import ACCENTS, DEFAULT_ACCENT, DEFAULT_THEME, THEMES, AstraStudio, CodeEditor


@pytest.fixture
def editor():
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    theme = dict(THEMES[DEFAULT_THEME], accent=ACCENTS[DEFAULT_ACCENT])
    widget = CodeEditor(theme, "Python")
    widget.completion_show_snippets = False
    widget.resize(480, 320)
    widget.show()
    widget.setFocus()
    app.processEvents()
    yield widget
    widget._hide_builtin_completion()
    widget.close()
    widget.deleteLater()
    app.processEvents()


def _position(editor, text, offset=None):
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text_offset_to_utf16(text, len(text) if offset is None else offset))
    editor.setTextCursor(cursor)


def _choose(editor, label):
    return next(display for display, item in editor._builtin_completion_items.items() if item.label == label)


def test_qt_builtin_unicode_edits_keep_newline_and_undo_as_one_action(editor):
    text = 'name = "😀"\npri\nnext_line = 1'
    _position(editor, text, text.index("pri") + 3)
    editor._refresh_builtin_completion(force=True, request_lsp=False)
    assert editor._insert_builtin_completion(_choose(editor, "print"))
    assert editor.toPlainText() == 'name = "😀"\nprint()\nnext_line = 1'
    assert editor.textCursor().position() == text_offset_to_utf16(editor.toPlainText(), editor.toPlainText().index("print(") + 6)
    editor.undo()
    assert editor.toPlainText() == text


def test_qt_builtin_rejects_stale_ranges_before_debounce_refresh(editor):
    _position(editor, "pri")
    editor._refresh_builtin_completion(force=True, request_lsp=False)
    display = _choose(editor, "print")
    editor.textCursor().insertText("x")
    assert not editor._insert_builtin_completion(display)
    assert editor.toPlainText() == "prix"


def test_builtin_completion_does_not_edit_old_position_after_cursor_move(editor):
    _position(editor, "pri")
    editor._refresh_builtin_completion(force=True, request_lsp=False)
    display = _choose(editor, "print")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    editor.setTextCursor(cursor)
    assert not editor._insert_builtin_completion(display)
    assert editor.toPlainText() == "pri"


def test_manual_completion_keeps_offline_popup_when_no_lsp_is_available(editor):
    _position(editor, "p")
    requests = []
    window = SimpleNamespace(current_editor=lambda: editor, _request_lsp_feature=lambda feature: requests.append(feature) or False)
    AstraStudio.request_lsp_completion(window)
    assert "print" in {item.label for item in editor._builtin_completion_items.values()}
    assert requests == ["completion"]


def test_ready_lsp_is_requested_for_unknown_offline_member_context(editor):
    _position(editor, "project_object.")
    requests = []
    editor._astra_completion_callback = lambda: requests.append("completion")
    editor._refresh_builtin_completion(force=True)
    assert requests == ["completion"]


def test_automatic_lsp_is_not_requested_inside_comments(editor):
    _position(editor, "# project_object.")
    requests = []
    editor._astra_completion_callback = lambda: requests.append("completion")
    editor._refresh_builtin_completion(force=True)
    assert requests == []


def test_lsp_dependency_import_is_applied_atomically_without_modal_menu(editor):
    text = 'name = "😀"\nPathtail'
    _position(editor, text, text.index("Pathtail") + 2)
    response = [{
        "label": "Path",
        "textEdit": {"newText": "Path", "insert": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 2}}, "replace": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 8}}},
        "additionalTextEdits": [{"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}, "newText": "from pathlib import Path\n"}],
    }]
    window = SimpleNamespace(current_editor=lambda: editor)
    AstraStudio._show_lsp_completion(window, response)
    assert editor._builtin_completer.popup().isVisible()
    assert editor._insert_builtin_completion(_choose(editor, "Path"))
    assert editor.toPlainText() == 'from pathlib import Path\nname = "😀"\nPath'
    editor.undo()
    assert editor.toPlainText() == text


def test_lsp_token_rejects_unsynchronized_text_changes(editor):
    editor.file_path = Path("/tmp/astra-completion-only-test.py")
    _position(editor, "pri")
    document = SimpleNamespace(version=4, text="pr")
    window = SimpleNamespace(current_editor=lambda: editor, lsp_manager=SimpleNamespace(documents=SimpleNamespace(get=lambda path: document)))
    token = {"path": str(editor.file_path), "version": 4}
    assert not AstraStudio._token_matches_current_document(window, token)
    document.text = "pri"
    assert AstraStudio._token_matches_current_document(window, token)


def test_lsp_filter_text_can_differ_from_label_and_enter_accepts_first_row(editor):
    _position(editor, "lam")
    window = SimpleNamespace(current_editor=lambda: editor)
    AstraStudio._show_lsp_completion(window, [{"label": "λ lambda", "filterText": "lambda", "insertText": "lambda"}])
    assert editor._builtin_completer.popup().currentIndex().isValid()
    assert editor._accept_current_builtin_completion()
    assert editor.toPlainText() == "lambda"


def test_lsp_response_does_not_reopen_popup_after_escape_or_cursor_move(editor):
    _position(editor, "pri")
    editor._refresh_builtin_completion(force=True, request_lsp=False)
    shown = []
    window = SimpleNamespace(
        current_editor=lambda: editor,
        _token_matches_current_document=lambda token, strict_version: True,
        _show_lsp_completion=lambda result: shown.append(result),
    )
    token = {"line": 0, "character": 3, "completion_generation": 0}
    escape = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    assert editor._handle_builtin_completion_key(escape)
    AstraStudio._on_lsp_interactive_result(window, "Python", "completion", token, [], None)
    assert shown == []
    token["completion_generation"] = editor._astra_completion_generation
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    editor.setTextCursor(cursor)
    AstraStudio._on_lsp_interactive_result(window, "Python", "completion", token, [], None)
    assert shown == []


def test_lsp_response_for_old_language_does_not_show_suggestions(editor):
    _position(editor, "pri")
    shown = []
    window = SimpleNamespace(
        current_editor=lambda: editor,
        _token_matches_current_document=lambda token, strict_version: True,
        _show_lsp_completion=lambda result: shown.append(result),
    )
    token = {"line": 0, "character": 3, "completion_generation": 0}
    AstraStudio._on_lsp_interactive_result(window, "Java", "completion", token, [], None)
    assert shown == []


def test_escape_cancels_pending_completion_before_popup_appears(editor):
    _position(editor, "pri")
    editor._hide_builtin_completion()
    escape = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    editor.keyPressEvent(escape)
    assert editor._astra_completion_generation == 1
    assert not editor._builtin_completion_timer.isActive()


@pytest.mark.parametrize("font_size,width", [(8, 240), (12, 360), (22, 480), (32, 480)])
def test_completion_popup_uses_editor_font_and_fits_narrow_viewport(editor, font_size, width):
    editor.resize(width, 320)
    editor.font_point_size = font_size
    editor.apply_editor_font_settings()
    _position(editor, "pri")
    editor._refresh_builtin_completion(force=True, request_lsp=False)
    popup = editor._builtin_completer.popup()
    assert popup.font().pointSize() == font_size
    assert popup.minimumWidth() <= editor.viewport().width()
    assert popup.maximumWidth() <= editor.viewport().width()


def test_untrusted_project_lsp_never_resolves_or_starts_tools(editor, tmp_path, monkeypatch):
    from core.lsp_transport import LspManager
    manager = LspManager(project_root=tmp_path, launch_guard=lambda: False)
    def unexpected_resolution(*args):
        raise AssertionError("Untrusted project tool discovery must not run")
    monkeypatch.setattr(manager.registry, "resolve", unexpected_resolution)
    path = tmp_path / "sample.py"
    manager.open_document("Python", path, "pri")
    manager.change_document("Python", path, "print")
    manager.save_document("Python", path, "print")
    assert manager.ensure_server("Python") is None
    assert manager.request_feature("Python", "completion", path) is None
    assert not manager.restart_server("Python")
    assert manager.connections == {}


def test_project_lsp_guard_fails_closed_when_policy_raises(editor, tmp_path, monkeypatch):
    from core.lsp_transport import LspManager
    def broken_policy():
        raise OSError("Unreadable trust store")
    manager = LspManager(project_root=tmp_path, launch_guard=broken_policy)
    monkeypatch.setattr(manager.registry, "resolve", lambda *args: pytest.fail("Unexpected tool resolution"))
    assert manager.ensure_server("Python") is None
    assert not manager.restart_server("Python")


@pytest.mark.parametrize("transport", ["stdio", "external_tcp"])
def test_pending_lsp_restart_cannot_start_after_root_switch(editor, tmp_path, transport):
    from core.lsp_servers import ResolvedLspServer
    from core.lsp_transport import LspManager
    manager = LspManager(project_root=tmp_path, launch_guard=lambda: True)
    server = ResolvedLspServer("Python", "python", "must-not-be-executed", (), transport=transport, port=6008)
    connection = manager._make_connection(server)
    manager._wire_connection(connection)
    connection._set_state(connection.RESTARTING)
    connection._restart_timer.start(60_000)
    manager.connections["Python"] = connection
    manager.set_project_root(tmp_path / "other")
    assert not connection._restart_timer.isActive()
    connection.start()
    assert connection.state == connection.STOPPED
    assert not connection.is_running()
