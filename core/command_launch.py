"""Keep automatic tool arguments separate from shell program text."""
from __future__ import annotations

import base64
import ntpath
import os
from pathlib import Path
import re
import shutil


def configure_process_command(process, program: str, arguments: list[str], *, windows: bool | None = None) -> None:
    """cmd.exe needs its native command line, not CommandLineToArgvW quoting."""
    windows = os.name == "nt" if windows is None else windows
    args = [str(value) for value in arguments]
    process.setProgram(str(program))
    if windows:
        process.setNativeArguments("")
        if ntpath.basename(str(program)).casefold() in {"cmd", "cmd.exe"}:
            for index, value in enumerate(args):
                if value.casefold() == "/c" and len(args) == index + 2:
                    process.setArguments([])
                    process.setNativeArguments(" ".join(args[:index + 1]) + " " + args[index + 1])
                    return
    process.setArguments(args)


def windows_tool_command(program: str, arguments: list[str]) -> tuple[str, list[str]]:
    """Bypass standard npm batch shims; constrain legacy batch fallbacks.

    Call only for Windows .cmd/.bat launchers. Explicit user-authored shell
    commands use the IDE's separate Run Project path.
    """
    script = Path(program)
    args = [str(value) for value in arguments]
    try:
        body = script.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        body = ""
    # npm's Windows shim forwards %* to one quoted JavaScript entry point.
    entries = set(re.findall(r'"%dp0%[\\/]([^"\r\n]+\.(?:js|cjs|mjs))"', body, re.IGNORECASE))
    if "%*" in body and len(entries) == 1:
        entry = script.parent / next(iter(entries)).replace("\\", "/")
        adjacent_node = script.parent / "node.exe"
        node = str(adjacent_node) if adjacent_node.is_file() else shutil.which("node.exe") or shutil.which("node")
        if node and entry.is_file():
            return node, [str(entry.resolve()), *args]

    # cmd expands percent variables even inside quotes, and quotes/newlines
    # cannot be represented generically across arbitrary batch script bodies.
    # Fail explicitly for those inputs rather than executing altered commands.
    values = [str(program), *args]
    if any(any(char in value for char in '\0\r\n"%!') for value in values):
        raise ValueError("Этот .cmd/.bat не поддерживает аргументы с кавычками, %, ! или переводом строки. Используй прямой EXE/Node-инструмент.")

    def quote(value: str) -> str:
        # Always quote, including paths without spaces containing & or |.
        trailing = len(value) - len(value.rstrip("\\"))
        return '"' + value + "\\" * trailing + '"'

    command = '"' + " ".join(quote(value) for value in values) + '"'
    return os.environ.get("COMSPEC", "cmd.exe"), ["/d", "/v:off", "/s", "/c", command]


def powershell_syntax_arguments(path: Path | str) -> list[str]:
    """Parse a file without making its name part of PowerShell syntax."""
    encoded_path = base64.b64encode(str(path).encode("utf-8")).decode("ascii")
    script = (
        "$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded_path + "'));"
        "$tokens=$null;$errors=$null;"
        "$null=[System.Management.Automation.Language.Parser]::ParseFile($p,[ref]$tokens,[ref]$errors);"
        "if($errors.Count){$errors|ForEach-Object{[Console]::Error.WriteLine($_.Message)};exit 1};"
        "Write-Output 'PowerShell syntax OK'"
    )
    encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script]
