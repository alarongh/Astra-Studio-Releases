# macOS: установка Astra Studio 5.0

## Выбор пакета

Для Intel Mac с **macOS 11.7.10** выберите `Astra-Studio-5.0-x86_64-legacy-macOS11.0.dmg`. В него входит Python 3.12 и Qt/PySide6 6.6.3.1, чей wheel рассчитан на macOS 11+. Для Intel с macOS 15+ и Apple Silicon с macOS 15+ предусмотрены отдельные `standard` пакеты на текущих зависимостях.

Сверьте SHA-256, откройте DMG и перетащите `Astra Studio.app` в `Applications`. Запускайте скопированное приложение. Отдельная установка Python/pip/Homebrew для самой IDE не нужна. Интерпретаторы и компиляторы пользовательских программ устанавливаются отдельно.

Перед заменой существующей Astra закройте её и сохраните прежнюю `.app`. Профиль находится в `~/Library/Application Support/AstralStudio` и не удаляется заменой `.app`.

Проверка минимальной macOS охватывает **все** Mach-O файлы пакета, а не только Info.plist или QtCore. Проверяется наличие нужной архитектуры и отсутствие требований выше заявленного минимума. Это проверка бинарной совместимости; выполнение на физическом Mac с 11.7.10 остаётся отдельной приёмкой.

Пакеты подписываются ad-hoc. Developer ID и notarization требуют учётной записи/сертификата издателя; без них macOS может запросить подтверждение запуска. Сборка не отключает Gatekeeper, не удаляет quarantine и не меняет настройки безопасности.

## Сборка для Intel Big Sur

На Intel Mac используйте CPython 3.12 и отдельное окружение:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-macos-intel-legacy.txt -r requirements-test.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build_macos.py --arch x86_64 --variant legacy --target-macos 11.0 --dmg
```

`--target-macos` запрещает выпуск пакета, если фактические библиотеки требуют более новую ОС. Не меняйте Info.plist вручную для обхода этого ограничения. Для macOS 10.x совместимость не заявлена.

Официальные требования: [PySide6 6.6.3.1](https://pypi.org/project/PySide6/6.6.3.1/), [Qt 6.11](https://doc.qt.io/qt-6.11/supported-platforms.html).

## Современные сборки

Use macOS 15 or newer and a supported CPython with the pinned PySide6 and
PyInstaller versions in `requirements.txt`. Build natively on Apple Silicon
(`arm64`) or Intel (`x86_64`); Windows cannot cross-build the `.app`.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-test.txt
.venv/bin/python main.py
.venv/bin/python scripts/build_macos.py --dmg
```

The output is `dist/macos-<arch>-standard/Astra Studio.app` and, with `--dmg`,
`Astra-Studio-5.0-<arch>-standard-macOS<minimum>.dmg` in the same directory. All build resources are
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
Apple account credentials and are separate release steps. The Windows JSON update feed is not a macOS installer. The Windows installer/update
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
