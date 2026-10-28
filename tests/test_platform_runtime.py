from __future__ import annotations

from pathlib import Path
import sys

import pytest

from core.platform_runtime import app_data_candidates, bundle_resource_path, existing_app_profile, macos_tool_directories
import core.java_runtime as java_runtime


def test_new_macos_profile_uses_application_support_and_keeps_legacy_profile(tmp_path):
    candidates = app_data_candidates("AstralStudio", platform="darwin", home=tmp_path, environ={})
    assert candidates[0] == tmp_path / "Library" / "Application Support" / "AstralStudio"
    assert existing_app_profile(candidates) is None
    old = tmp_path / "AppData" / "Local" / "AstralStudio"
    old.mkdir(parents=True)
    (old / "settings.json").write_text('{"workspace":"existing"}', encoding="utf-8")
    assert existing_app_profile(candidates) == old
    candidates[0].mkdir(parents=True)
    (candidates[0] / "settings.json").write_text("{}", encoding="utf-8")
    assert existing_app_profile(candidates) == candidates[0]


def test_windows_data_path_and_legacy_profile_are_preserved(tmp_path):
    native = tmp_path / "redirected local data"
    candidates = app_data_candidates("AstralStudio", platform="win32", home=tmp_path, environ={"LOCALAPPDATA": str(native)})
    assert candidates[0] == native / "AstralStudio"
    assert tmp_path / ".astra_studio" in candidates


def test_relative_xdg_path_is_not_resolved_inside_a_user_project(tmp_path):
    candidates = app_data_candidates("AstralStudio", platform="linux", home=tmp_path, environ={"XDG_DATA_HOME": "untrusted-relative"})
    assert candidates[0] == tmp_path / ".local" / "share" / "AstralStudio"


def test_explicit_data_directory_isolated_without_relocating_legacy_profiles(tmp_path, monkeypatch):
    target = tmp_path / "isolated app data"
    candidates = app_data_candidates("AstralStudio", platform="darwin", home=tmp_path,
                                    environ={"ASTRA_DATA_DIR": str(target)})
    assert candidates == (target,)
    candidates = app_data_candidates("AstralStudio", platform="darwin", home=tmp_path,
                                    environ={"ASTRA_DATA_DIR": "relative-project-folder"})
    assert candidates[0] == tmp_path / "Library" / "Application Support" / "AstralStudio"
    import main
    monkeypatch.setenv("ASTRA_DATA_DIR", str(target))
    assert main.documents_root_dir().is_relative_to(target)
    assert main.default_projects_dir().is_relative_to(target)
    assert main.default_builds_dir().is_relative_to(target)


def test_resources_resolve_inside_app_bundle_with_spaces_and_unicode(tmp_path, monkeypatch):
    bundle = tmp_path / "Моя Astra Studio.app" / "Contents" / "Frameworks"
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert bundle_resource_path("data/python_libraries.json", tmp_path / "source") == bundle / "data" / "python_libraries.json"


def test_finder_tool_paths_do_not_include_current_project(tmp_path):
    paths = macos_tool_directories(tmp_path / "user")
    assert Path("/opt/homebrew/bin") in paths
    assert Path("/usr/local/bin") in paths
    assert all(path.is_absolute() for path in paths)
    assert Path.cwd() not in paths


@pytest.mark.skipif(sys.platform == "win32", reason="macOS POSIX executable names")
def test_macos_java_launcher_stubs_do_not_count_as_an_installed_jdk(monkeypatch):
    monkeypatch.setattr(java_runtime.sys, "platform", "darwin")
    runtime = java_runtime.discover_java_runtime(env={}, which=lambda name: "/usr/bin/" + name, search_standard_homes=False)
    assert runtime is None


@pytest.mark.skipif(sys.platform == "win32", reason="macOS JDK bundle paths")
def test_macos_java_bundle_is_found_without_a_shell_profile(tmp_path, monkeypatch):
    home = tmp_path / "jdk-21.jdk" / "Contents" / "Home"
    (home / "bin").mkdir(parents=True)
    for name in ("javac", "java"):
        (home / "bin" / name).write_bytes(b"stub")
    monkeypatch.setattr(java_runtime.sys, "platform", "darwin")
    monkeypatch.setattr(java_runtime, "_macos_java_homes", lambda: iter((home,)))
    runtime = java_runtime.discover_java_runtime(env={}, which=lambda name: "/usr/bin/" + name)
    assert runtime is not None
    assert runtime.home == home
    assert runtime.source == "macOS JDK bundle"


@pytest.mark.skipif(sys.platform == "win32", reason="frozen Unix Python discovery")
def test_bundled_app_uses_external_python3_and_never_relaunches_itself(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    import main
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    app = tmp_path / "Astra Studio.app" / "Contents" / "MacOS" / "Astra Studio"
    python = tmp_path / "external python" / "bin" / "python3"
    monkeypatch.setattr(main.sys, "executable", str(app))
    monkeypatch.setattr(main, "compiler_path", lambda name: str(python) if name == "python3" else str(app))
    assert main.python_command() == (str(python), [])
    monkeypatch.setattr(main, "compiler_path", lambda _name: str(app))
    assert main.python_command() == (None, [])


def test_macos_spec_contains_runtime_data_and_native_bundle_metadata(tmp_path):
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_macos.py"
    spec = importlib.util.spec_from_file_location("astra_build_macos", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.spec_source(tmp_path / "Проект с пробелами", "arm64")
    compile(source, "generated_macos.spec", "exec")
    assert "'data'" in source
    assert "check_tools.py" in source
    assert "NSHighResolutionCapable" in source
    assert "LSMinimumSystemVersion" in source
    assert "target_arch='arm64'" in source
    assert module.minimum_from_load_commands("cmd LC_BUILD_VERSION\nminos 13.0\ncmd LC_BUILD_VERSION\nminos 26.0") == "26.0"
    source = module.spec_source(tmp_path, "arm64", minimum_macos="26.0")
    assert '"LSMinimumSystemVersion": \'26.0\'' in source
