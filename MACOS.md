# macOS build and validation

Use macOS 13 or newer and a supported CPython with the pinned PySide6 and
PyInstaller versions in `requirements.txt`. Build natively on Apple Silicon
(`arm64`) or Intel (`x86_64`); Windows cannot cross-build the `.app`.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-test.txt
.venv/bin/python main.py
.venv/bin/python scripts/build_macos.py --dmg
```

The output is `dist/macos-<arch>/Astra Studio.app` and, with `--dmg`,
`Astra-Studio-4.0-<arch>.dmg` in the same directory. All build resources are
resolved from the script location, so invoking it from another working directory
or a path containing spaces or Cyrillic is supported. The generated spec lives
under ignored `build/`, and includes `assets`, `data/python_libraries.json`, and
the unchanged update-channel configuration and the read-only tool diagnostic
script. No runtime or toolchain is installed
globally by this script.

`--arch arm64`, `--arch x86_64`, and `--arch universal2` are explicit options.
The selected Python and every bundled native dependency must contain the target
architecture. A Homebrew arm64 Python cannot produce an Intel build; use an
Intel Python environment or build on an Intel Mac. `universal2` requires a
universal2 Python **and** universal native dependencies. Do not combine two
PyInstaller apps with `lipo`. macOS 13 is the Qt platform floor, not proof that a
particular build supports that OS. The script reads Mach-O load commands from
Python and QtCore and records their actual minimum in the app's Info.plist.
The local Homebrew CPython 3.14.7 requires **macOS 26**, so an app built with that
interpreter requires macOS 26+. To target macOS 13, use a Python distribution and
all dependency wheels built for 13 or earlier, then validate on macOS 13 hardware.
Other third-party native wheels can impose additional constraints; validate each
architecture on its target hardware.

New profiles use `~/Library/Application Support/AstralStudio`. Existing profiles
in the old `~/AppData/Local/AstralStudio` or `~/.astra_studio` locations remain in
place, preserving settings and the internal workspace. The application never
writes mutable data inside `.app`. Resources use PyInstaller's `_MEIPASS`, and
Finder-launched apps can discover Homebrew tools without executing shell profile
scripts. Bundled Astra does not reuse its own executable as a Python interpreter:
select a project `.venv` or install a separate Python 3 interpreter. JDK bundles
are discovered separately from Apple's `/usr/bin/java` launcher stubs.

Qt's logical `Ctrl` shortcuts map to Command on macOS. Test Command+S/O/N,
Command+Shift+S and Command+Space (the last may be reserved by Spotlight), F5,
editing, save/reopen, Python/C++/JavaScript execution, console input, stop and
immediate rerun. Unix child processes are launched in an owned session, so Stop
and application shutdown can also stop descendants. Explicit project commands
are still user-initiated shell commands.

For automated tests:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

For native validation, launch the built app with `open`, rather than relying only
on offscreen tests. Check resource loading, Retina text, resized splitters,
appearance persistence, and completion at system scales 100/125/150/175/200%.
Mixed-DPI monitor transitions, minimum-OS hardware, and Intel execution need
their own machines; report those as untested unless actually exercised.

The default package is ad-hoc signed by PyInstaller, and the build script verifies
its signature. Distribution signing requires an owner's existing Developer ID
identity (`--codesign-identity`). Notarization and stapling require the owner's
Apple account credentials and are separate release steps. This change does not
publish a release or alter the public update feed. The Windows installer/update
pipeline remains separate; macOS packages currently require manual replacement.

For an isolated acceptance run, set an absolute `ASTRA_DATA_DIR` when launching
the application, for example `ASTRA_DATA_DIR=/tmp/astra-acceptance` followed by
the bundle's `Contents/MacOS/Astra Studio` executable. This selects a separate
settings/workspace directory and does not relocate an existing profile. Relative
override paths are ignored.

Primary references: [Qt supported platforms](https://doc.qt.io/qt-6/supported-platforms.html),
[PyInstaller macOS architectures](https://pyinstaller.org/en/stable/feature-notes.html#macos-multi-arch-support),
[PyInstaller options](https://pyinstaller.org/en/stable/usage.html#macos-specific-options).

The GitHub Actions workflow is configured for Windows/macOS with Python 3.14,
the pinned application/test requirements, compile checks and regression tests.
Qt tests use `offscreen`; the Windows HWND caption test uses the native plugin
in a separate step. Windows also builds the PyInstaller package and checks its
executable and bundled library data. Actions are pinned to reviewed release
commit SHAs, repository permissions are read-only, and checkout credentials are
not persisted. No signing credentials, deployment, release or update-feed writes
are used. CI results require an actual GitHub run; creating this workflow does
not establish a passing CI result.
