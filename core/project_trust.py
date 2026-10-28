"""User-owned authorization for tools that can execute workspace code."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def _root_key(root: Path | str) -> str:
    return os.path.normcase(str(Path(root).resolve()))


class ProjectTrustStore:
    """Exact canonical roots; no trust is imported from project configuration."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._trusted: set[str] = set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema_version") == 1:
                roots = data.get("trusted_roots", [])
                if isinstance(roots, list):
                    # Stored values already identify canonical roots at consent
                    # time. Resolving again could transfer approval to a new
                    # symlink target after a directory is replaced.
                    self._trusted = {os.path.normcase(os.path.normpath(item)) for item in roots
                                     if isinstance(item, str) and Path(item).is_absolute()}
        except (OSError, ValueError, RuntimeError):
            pass

    def is_trusted(self, root: Path | str) -> bool:
        try:
            return _root_key(root) in self._trusted
        except (OSError, ValueError, RuntimeError):
            return False

    def set_trusted(self, root: Path | str, trusted: bool = True) -> None:
        key = _root_key(root)
        updated = self._trusted | {key} if trusted else self._trusted - {key}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".astra-trust-", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({"schema_version": 1, "trusted_roots": sorted(updated)}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self._trusted = updated
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
