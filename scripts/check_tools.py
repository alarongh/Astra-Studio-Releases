"""Read-only tool diagnostics for macOS/Linux, run outside the GUI thread."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def probe(label: str, names: tuple[str, ...], arguments: list[str]) -> bool:
    program = next((path for name in names if (path := shutil.which(name))), None)
    if not program:
        print(f"✕ {label}: не найден", flush=True)
        return False
    try:
        result = subprocess.run(
            [program, *arguments], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠ {label}: {program} — {exc}", flush=True)
        return False
    output = (result.stdout or result.stderr).strip().splitlines()
    version = output[0][:200] if output else "нет вывода"
    marker = "✓" if result.returncode == 0 else "⚠"
    print(f"{marker} {label}: {program} | {version} | код {result.returncode}", flush=True)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--updates", action="store_true")
    args = parser.parse_args()
    checks = (
        ("Python", ("python3", "python"), ["-c", "import sys; print(sys.version.split()[0]); assert 40 + 2 == 42"]),
        ("C++", ("clang++", "g++"), ["--version"]),
        ("Java compiler", ("javac",), ["-version"]),
        ("Java runtime", ("java",), ["-version"]),
        ("Node.js", ("node",), ["--version"]),
        ("npm", ("npm",), ["--version"]),
        ("Git", ("git",), ["--version"]),
        ("uv", ("uv",), ["--version"]),
    )
    print("Проверка инструментов: отсутствующие необязательные компоненты не устанавливаются.", flush=True)
    for index, (label, names, arguments) in enumerate(checks, 1):
        probe(label, names, arguments)
        print(f"ASTRA_PROGRESS:{int(index * 85 / len(checks))}", flush=True)
    if args.updates:
        if sys.platform == "darwin" and shutil.which("brew"):
            environment = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_ANALYTICS="1")
            print("Проверка Homebrew по существующему локальному каталогу (без установки/обновления).", flush=True)
            try:
                result = subprocess.run(
                    [shutil.which("brew"), "outdated", "--quiet"], capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=30,
                    env=environment, check=False,
                )
                print(result.stdout.strip() or "В локальном каталоге Homebrew обновления не найдены.", flush=True)
                if result.returncode:
                    print(result.stderr.strip() or "Homebrew не завершил проверку.", flush=True)
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(f"Проверка Homebrew недоступна: {exc}. Повторите позже.", flush=True)
        else:
            print("Для свежих обновлений используйте пакетный менеджер ОС; Astra не меняет глобальные окружения.", flush=True)
    print("ASTRA_PROGRESS:100", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
