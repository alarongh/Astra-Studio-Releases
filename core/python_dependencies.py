"""Small, GUI-independent contracts for Python dependency checks.

Checking an interpreter is different from proving a package is absent. A failed
or incomplete probe must never become an instruction to install everything.
"""
from __future__ import annotations

import json
from typing import Iterable


MUTATING_PIP_ACTIONS = frozenset({"install", "uninstall", "download", "wheel"})


def normalized_import_names(names: Iterable[str]) -> list[str]:
    result: list[str] = []
    for name in names:
        module = str(name or "").split(".", 1)[0].strip()
        if module.isidentifier() and module not in result:
            result.append(module)
    return result


IMPORT_PROBE_CODE = '''import importlib.util, json, sys
modules = json.loads(sys.argv[1])
result = {}
for module in modules:
    try:
        result[module] = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError) as exc:
        raise RuntimeError("Cannot inspect " + module) from exc
print(json.dumps({"schema_version": 1, "available": result}, ensure_ascii=False))
'''


def parse_import_probe(output: str, names: Iterable[str]) -> dict[str, bool]:
    """Accept a complete probe response; tolerate interpreter startup notices."""
    expected = normalized_import_names(names)
    if len(output) > 128 * 1024:
        raise ValueError("Python dependency probe output is too large")
    lines = output.strip().splitlines()
    if not lines:
        raise ValueError("Python dependency probe returned no response")
    try:
        payload = json.loads(lines[-1])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Python dependency probe returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported Python dependency probe response")
    available = payload.get("available")
    if not isinstance(available, dict) or set(available) != set(expected):
        raise ValueError("Python dependency probe response is incomplete")
    if any(type(value) is not bool for value in available.values()):
        raise ValueError("Python dependency probe returned invalid package statuses")
    return {name: available[name] for name in expected}
