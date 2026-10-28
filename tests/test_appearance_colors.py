from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.appearance import (
    COLOR_ROLES, DEFAULT_BACKGROUND_COLOR, LEGACY_WALLPAPER_COLORS,
    contrast_ratio, editor_theme_with_background, load_appearance_colors,
    normalize_hex_color, readable_text_color, restore_splitter_sizes,
)


@pytest.mark.parametrize("value,expected", [("#abc", "#AABBCC"), (" f0e1d2 ", "#F0E1D2"), ("#000000", "#000000")])
def test_hex_accepts_solid_rgb(value, expected):
    assert normalize_hex_color(value) == expected


@pytest.mark.parametrize("value", [None, 42, "red", "#AABBCCDD", "#12", "#fff; background:url(file)"])
def test_hex_rejects_invalid_or_stylesheet_input(value):
    with pytest.raises(ValueError):
        normalize_hex_color(value)


@pytest.mark.parametrize("preset,color", LEGACY_WALLPAPER_COLORS.items())
def test_every_retired_photo_migrates_to_color(preset, color):
    assert load_appearance_colors({"preset_wallpaper": preset}) == (color, {})


def test_invalid_saved_colors_are_ignored_without_losing_valid_roles():
    assert load_appearance_colors({"background_color": "invalid", "panel_colors": {
        "editor": "#abc", "console": "url(secret)", "unknown": "#000", "background": "#fff",
    }}) == (DEFAULT_BACKGROUND_COLOR, {"editor": "#AABBCC"})


@pytest.mark.parametrize("value", [["wide", 20], [True, 50], [-20, 30], [2**40, 30], [0, 0], [20], None])
def test_corrupt_splitter_settings_do_not_reach_qt(value):
    assert restore_splitter_sizes(value, 2) == []
    assert restore_splitter_sizes([190, 800], 2) == [190, 800]


@pytest.mark.parametrize("background", ["#FFFFFF", "#000000", "#777777", "#E636C2", "#17312B"])
def test_custom_editor_background_keeps_text_and_syntax_readable(background):
    theme = {key: "#89A1CC" for key in ("text", "muted", "keyword", "string", "comment", "number", "function", "class")}
    theme.update(editor="#010203", panel="#020304", panel2="#030405", line="#040506", selection="#050607")
    adjusted = editor_theme_with_background(theme, background)
    for key in ("text", "muted", "keyword", "string", "comment", "number", "function", "class"):
        assert contrast_ratio(adjusted[key], background) >= 4.5
    assert contrast_ratio(readable_text_color(background), background) >= 4.5
    assert theme["editor"] == "#010203"  # no global-theme mutation


@pytest.fixture
def window_factory(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    import main

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main, "app_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(main, "default_builds_dir", lambda: tmp_path / "builds")
    monkeypatch.setattr(main.AstraStudio, "start_terminal", lambda self: None)
    monkeypatch.setattr(main.LspManager, "ensure_server", lambda *args: None)
    windows = []

    def create(settings=None):
        if settings is not None:
            data = tmp_path / "data"
            data.mkdir(exist_ok=True)
            (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        window = main.AstraStudio()
        windows.append(window)
        return window

    yield app, main, create
    for window in windows:
        window.close()
    app.processEvents()


def test_color_roles_persist_reset_and_do_not_delete_user_image(window_factory, tmp_path):
    app, main, create = window_factory
    image = tmp_path / "свой фон.png"
    # A real user-selected image, independent of the removed bundled assets.
    from PySide6.QtGui import QImage, QColor
    picture = QImage(30, 20, QImage.Format.Format_RGB32)
    picture.fill(QColor("#246810"))
    assert picture.save(str(image))
    window = create()
    window.custom_wallpaper_path = str(image)
    window.wallpaper_enabled = True
    window.apply_theme()
    assert window.current_wallpaper_path() == image
    for role in COLOR_ROLES:
        window.color_target_combo.setCurrentIndex(window.color_target_combo.findData(role))
        window.color_hex_edit.setText("#abcdef")
        window.apply_hex_color()
    assert image.exists()
    assert window.custom_wallpaper_path == str(image)
    assert not window.wallpaper_enabled
    saved = json.loads(window.settings_path.read_text(encoding="utf-8"))
    assert saved["background_color"] == "#ABCDEF"
    assert saved["panel_colors"] == {key: "#ABCDEF" for key in COLOR_ROLES if key != "background"}
    restored = create()
    assert restored.background_color == "#ABCDEF"
    assert restored.panel_colors == saved["panel_colors"]
    assert restored.current_editor().theme["editor"] == "#ABCDEF"
    restored.reset_appearance_defaults()
    assert restored.background_color == DEFAULT_BACKGROUND_COLOR
    assert restored.panel_colors == {}
    assert image.exists()
    assert main.ASTRA_WALLPAPERS == {}


def test_migration_preserves_explicit_user_picture(window_factory, tmp_path):
    _app, _main, create = window_factory
    image = tmp_path / "my-wallpaper.png"
    image.write_bytes(b"user file must not be deleted")
    window = create({"preset_wallpaper": "Astra Cyber Ritual", "custom_wallpaper_path": str(image), "wallpaper_enabled": True})
    assert window.current_wallpaper_path() == image
    assert window.background_color == LEGACY_WALLPAPER_COLORS["Astra Cyber Ritual"]
    window.clear_custom_wallpaper()
    assert image.read_bytes() == b"user file must not be deleted"


def test_color_dialog_cancel_and_bad_hex_leave_state_unchanged(window_factory, monkeypatch):
    _app, main, create = window_factory
    from PySide6.QtGui import QColor
    window = create()
    original = window.background_color
    monkeypatch.setattr(main.QColorDialog, "getColor", lambda *args: QColor())
    window.choose_appearance_color()
    window.color_hex_edit.setText("#BADHEX")
    window.apply_hex_color()
    assert window.background_color == original
    monkeypatch.setattr(main.QColorDialog, "getColor", lambda *args: QColor("#22aa44"))
    window.choose_appearance_color()
    assert window.background_color == "#22AA44"


def test_selecting_same_named_images_does_not_overwrite_previous_user_copy(window_factory, monkeypatch, tmp_path):
    _app, main, create = window_factory
    from PySide6.QtGui import QImage, QColor
    originals = []
    for folder, color in (("first", "#112233"), ("second", "#AABBCC")):
        source = tmp_path / folder / "wallpaper.png"
        source.parent.mkdir()
        image = QImage(16, 16, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        assert image.save(str(source))
        originals.append(source)
    selected = iter(originals)
    monkeypatch.setattr(main.QFileDialog, "getOpenFileName", lambda *args: (str(next(selected)), ""))
    window = create()
    window.choose_custom_wallpaper()
    first_copy = Path(window.custom_wallpaper_path)
    first_bytes = first_copy.read_bytes()
    window.choose_custom_wallpaper()
    second_copy = Path(window.custom_wallpaper_path)
    assert second_copy != first_copy
    assert first_copy.read_bytes() == first_bytes == originals[0].read_bytes()
    assert second_copy.read_bytes() == originals[1].read_bytes()


def test_resize_keeps_panels_and_user_splitter_widths(window_factory):
    app, _main, create = window_factory
    window = create()
    window.resize(1100, 720)
    window.show()
    app.processEvents()
    window._show_tools_drawer(2, "Библиотеки")
    app.processEvents()
    assert window.sidebar_shell.isVisible()
    assert window.project_panel.isVisible()
    window.main_splitter.setSizes([350, 520])
    app.processEvents()
    before = window.main_splitter.sizes()
    for _ in range(4):
        window._apply_responsive_layout()
    assert window.main_splitter.sizes() == before
    window.resize(800, 600)
    app.processEvents()
    assert window.sidebar_shell.isVisible()
    assert window.project_panel.isVisible()
    assert window.tools_scroll.widget() is window.tools_stack
    window.change_ui_font_size(22)
    app.processEvents()
    for button in (window.btn_apply_color, window.btn_choose_color, window.btn_close_tools_drawer):
        assert button.minimumHeight() >= button.fontMetrics().height() + 16


def test_hidden_console_pages_do_not_force_navigation_to_minimum_width(window_factory):
    app, _main, create = window_factory
    window = create()
    window.resize(1200, 800)
    window.show()
    app.processEvents()
    # Even when a hidden Git/Test page contains long action rows, the visible
    # editor must honor a user widening navigation, rather than squeezing it.
    assert window.bottom_tabs.minimumSizeHint().width() < 400
    window.root_splitter.setSizes([240, 0, 900])
    window.main_splitter.setSizes([300, 600])
    app.processEvents()
    assert window.sidebar_shell.width() >= 200
    assert window.project_scroll.width() >= 250


@pytest.mark.parametrize("scale", ["1", "1.25", "1.5", "1.75", "2"])
def test_real_qt_scaling_keeps_settings_controls_reachable(scale):
    pytest.importorskip("PySide6")
    # Qt reads scale factors when QApplication is created, so each case must
    # use a fresh process instead of changing a variable on an existing app.
    code = r'''
import tempfile, os
from pathlib import Path
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
import main
app = QApplication([])
root = Path(tempfile.mkdtemp(prefix="astra-scale-test-"))
main.app_data_dir = lambda: root / "data"
main.default_builds_dir = lambda: root / "builds"
main.AstraStudio.start_terminal = lambda self: None
main.LspManager.ensure_server = lambda *args: None
window = main.AstraStudio()
window.resize(900, 650)
window.show()
window.change_ui_font_size(22)
window.open_settings_page()
app.processEvents()
assert abs(window.devicePixelRatioF() - float(os.environ["QT_SCALE_FACTOR"])) < 0.05
assert window.width() == 900
assert window.settings_scroll.horizontalScrollBar().maximum() == 0
for control in (window.color_target_combo, window.color_hex_edit, window.btn_choose_color):
    window.settings_scroll.ensureWidgetVisible(control)
    app.processEvents()
    point = control.mapTo(window.settings_scroll.viewport(), QPoint())
    assert point.x() >= 0
    assert point.x() + control.width() <= window.settings_scroll.viewport().width()
    assert control.height() > 0
window.close()
app.processEvents()
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
