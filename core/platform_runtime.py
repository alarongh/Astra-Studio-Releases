"""Platform paths without shell startup files or project-controlled PATH entries."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Mapping


def app_data_candidates(
    app_dir_name: str,
    *,
    platform: str | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    env = os.environ if environ is None else environ
    # Explicit launch-time override supports portable installations and isolated
    # acceptance runs. Never interpret a relative value inside a foreign project.
    override = env.get("ASTRA_DATA_DIR")
    if override and Path(override).is_absolute():
        return (Path(override),)
    legacy = home / "AppData" / "Local" / app_dir_name
    if platform == "win32":
        native = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / app_dir_name
    elif platform == "darwin":
        native = home / "Library" / "Application Support" / app_dir_name
    else:
        configured = Path(env.get("XDG_DATA_HOME") or home / ".local" / "share")
        native = (configured if configured.is_absolute() else home / ".local" / "share") / app_dir_name
    return tuple(dict.fromkeys((native, legacy, home / ".astra_studio")))


def existing_app_profile(candidates: tuple[Path, ...]) -> Path | None:
    """Keep an existing installation's settings and workspace together in place."""
    return next((path for path in candidates if (path / "settings.json").is_file()), None)


def macos_tool_directories(home: Path | None = None) -> tuple[Path, ...]:
    """Finder does not inherit PATH changes made by Homebrew shell profiles."""
    home = Path.home() if home is None else Path(home)
    return (
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        home / ".local" / "bin",
        home / ".cargo" / "bin",
    )


def bundle_resource_path(relative_path: str, source_root: Path) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    return (Path(bundle_root) if bundle_root else Path(source_root)) / relative_path
