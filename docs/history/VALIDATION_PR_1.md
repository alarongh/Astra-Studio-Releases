# Astra Studio 4.0 implementation and validation

Validation date: 2026-10-28. Work is in `codex/astra-4-audit-macos`.

## Source provenance

The upstream main branch contained the older 3.20 source at
`a354eb5fd1a58d461a5b0e6aa39f35b876b4b026`. Implementation uses the official
4.0 source release, imported separately in commit
`3e603e6d20c4dd3c104e0daef3d188626f91b24f` before remediation changes.
The release archive `Astra_Studio_Release_4_0_FINAL_SOURCE.zip` has SHA-256
`4c4398eb3fbd8645c79af079efa5f32cc9617d3af861237cf8c62371eb50f5db`;
it matched both the release asset digest and published checksums. All 293
manifest entries verified. Extraction rejected traversal and symbolic links;
generated Python/test caches were excluded from the import.

## Changes

### Interface and appearance

- Qt logical sizes, font metrics, wrapping and scrollable settings/bottom-tab
  pages keep controls reachable at larger fonts and scaled displays. Resizing
  does not reset the user's splitter positions or hide the project sidebar.
- Solid palettes and validated HEX/custom color selection cover the workspace,
  panels, editor, console, project panel and settings, with readable foregrounds.
  Colors persist and can be reset.
- Nine bundled photo wallpapers were removed and their saved selections migrate
  to solid colors. User-supplied images remain supported and are copied with
  unique names; user files are not deleted by the migration.
- Editor line numbers use the editor font even when UI font sizes differ.

### Completion

- Built-in completion remains available offline for Python, Java, C++,
  JavaScript, HTML and CSS. Ready language servers contribute asynchronously
  through the same nonmodal popup, including explicit manual completion.
- UTF-16 LSP positions are converted correctly, stale document/cursor responses
  are discarded, context filtering handles comments/strings, and validated
  insert/replace edits and additional import edits apply atomically.
- Deferred deletion and callback ownership in stdio/TCP LSP clients were fixed
  after reproducing a native teardown crash. Tests exercise actual QObject
  garbage collection and DeferredDelete lifecycles.

### Environments and tools

- Project dependency checks are asynchronous, bounded and cancellable, with
  separate missing/error/timeout states. They use the selected project/source
  root and do not silently mutate global Python when a project environment is
  absent or its interpreter is missing.
- Environment creation preserves partial environments and existing project
  files. Repeated successful checks do not reinstall dependencies. Isolated
  Python probes avoid executing project shadow modules.
- Tool diagnostics on macOS/Linux are read-only. Windows update checking lists
  available upgrades rather than performing a WinGet upgrade.

### macOS and process lifetime

- Native data/resource paths, Finder tool discovery, external Python selection,
  JDK discovery, Command shortcuts, Unix process sessions and descendant stopping
  support macOS without replacing the Windows paths.
- Process callbacks use weak references and validate QObject lifetime. Regression
  tests cover parent/process destruction in either order after reproducing a
  second native teardown crash.
- `scripts/build_macos.py` creates a native `.app` and optional `.dmg`, includes
  the read-only diagnostic script and resources, verifies the ad-hoc signature,
  and records the actual Python/Qt minimum OS. See [MACOS.md](../../MACOS.md).
- An absolute `ASTRA_DATA_DIR` permits isolated acceptance testing without
  relocating an existing user profile.

### Security remediation

Seven findings from the scoped security review were addressed:

| Boundary | Result |
| --- | --- |
| Automatic project LSP execution | Per-user trust in canonical roots gates startup/restart/background checks; project config origin and attached source root also require trust. |
| Python checker shadowing | Isolated checker invocation; a project-selected interpreter cannot run before trust is granted. |
| Windows batch arguments | Standard npm shims run through Node directly; legacy batch arguments are validated/quoted and passed through QProcess native arguments. |
| PowerShell filename parsing | Fixed parser script uses EncodedCommand; filenames travel as base64 data. |
| Fixed-name write probes | Exclusive temporary files preserve existing files and symlinks. |
| Static preview exposure | Preview server binds to loopback. |
| Replace All outside project | Symlink/outside-root exclusions, rechecks and atomic replacement preserve external targets and file encoding/permissions. |

Trust records do not follow a later symlink substitution. Explicit project
commands remain user actions; opening an untrusted project is not consent to
execute its tools. The review found no embedded secrets in the inspected scope.
This is partial security coverage, not a claim that the entire application has
no vulnerabilities. The canonical scan is
`5c812aba-5095-4860-9036-c08a8686f2a4`; its registration predates the 4.0 import,
so its recorded repository head differs from the verified source snapshot used
for analysis. The original scan findings are not claimed automatically closed
in the scan service by this patch.

## Executed validation

Host: Apple Silicon, macOS 26.6.2, isolated CPython 3.14.7 environment,
PySide6 6.11.2 and PyInstaller 6.22.2. No global packages were installed.

| Check | Observed result |
| --- | --- |
| Full regression suite on final implementation | 453 passed, 7 skipped, 88 subtests passed; 17.50 seconds |
| Python compile checks and git whitespace checks | Passed |
| UI scale subprocess probes | DPR 1, 1.25, 1.5, 1.75 and 2 matched the requested Qt scale; 900×650 logical window, UI font 22, settings content fit the viewport |
| Appearance checks | Custom panel colors, editor/UI font differences, reset and persistence exercised |
| Dependency safety | Actual asynchronous Qt checks repeated without pip mutation; failure/cancellation and partial-environment cases covered |
| Resolved dependency vulnerability audit | 43 installed packages audited; no known vulnerabilities reported at check time |
| Native macOS package | `.app` and `.dmg` built; deep/strict signature verification passed |
| Native Cocoa acceptance | Saved a Python file using Command+S, ran it, entered stdin `42`, observed its result and exit 0, ran again, stopped the waiting process, then quit Astra with exit 0 |
| Lifecycle regressions | Real subprocess/Qt object deletion and deferred cleanup passed for process and LSP owners |

The test registry lists the 460 collected test IDs. Skips are explicit platform
conditions, not evidence of a successful native Windows run. Static analysis
warnings were inspected; subprocess usage alone is not treated as a confirmed
vulnerability. Passing dependency auditing is time-dependent and cannot establish
absence of undisclosed vulnerabilities.

## Remaining platform validation and distribution limits

- Windows native command/PowerShell roundtrips, HWND behavior, WinGet and the
  installer/updater require Windows. The workflow includes Windows tests/build,
  but a configured workflow is not a completed CI run.
- Intel/universal2 builds, older macOS hardware, physical mixed-DPI monitor
  transitions and real external language-server/toolchain combinations were not
  exhaustively exercised on this Apple Silicon host.
- This particular artifact requires **macOS 26.0+ on arm64**, because its bundled
  Homebrew Python requires 26.0. Qt's lower platform floor does not change that.
  Producing a macOS 13 artifact requires a compatible interpreter/dependencies
  and validation on that target.
- The package is ad-hoc signed, not Developer ID signed or notarized. Those are
  owner-controlled distribution steps. No release was published, no PR merged,
  and the public update feed/configuration were not changed.

CI actions are pinned to release commit SHAs, permissions are read-only and
checkout credentials are not persisted. The workflow has no release/deployment
secrets or update-feed writes.
