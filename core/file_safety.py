"""Small filesystem operations that must not overwrite project-supplied files."""
from __future__ import annotations

from pathlib import Path
import os
import stat
import tempfile
from typing import Iterable


def directory_is_writable(directory: Path | str, *, create: bool = False) -> bool:
    path = Path(directory)
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        # TemporaryFile creates an exclusive, unpredictable file. In particular,
        # never follow or remove the old fixed probe name supplied by a project.
        with tempfile.TemporaryFile(dir=path, prefix=".astra-write-") as probe:
            probe.write(b"ok")
            probe.flush()
        return True
    except OSError:
        return False


def is_project_text_path(path: Path | str, roots: Iterable[Path | str]) -> bool:
    """Bulk project operations do not follow project-supplied file links."""
    candidate = Path(path)
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return False
        resolved = candidate.resolve(strict=True)
        return any(resolved.is_relative_to(Path(root).resolve(strict=True)) for root in roots)
    except (OSError, ValueError, RuntimeError):
        return False


def write_project_text(path: Path | str, text: str, encoding: str, roots: Iterable[Path | str]) -> None:
    """Replace a validated project file without truncating linked inodes."""
    candidate = Path(path)
    roots = tuple(roots)
    if not is_project_text_path(candidate, roots):
        raise OSError("Путь файла больше не принадлежит проекту или является ссылкой")
    temporary = None
    try:
        mode = stat.S_IMODE(candidate.stat().st_mode)
        with tempfile.NamedTemporaryFile(mode="w", encoding=encoding, dir=candidate.parent,
                                         prefix=".astra-replace-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        if not is_project_text_path(candidate, roots):
            raise OSError("Путь файла изменился во время замены")
        os.replace(temporary, candidate)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
