"""Check every bundled Mach-O architecture and minimum OS before distribution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys

MACHO_MAGIC = {bytes.fromhex(value) for value in (
    'feedface', 'cefaedfe', 'feedfacf', 'cffaedfe', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}


def version_parts(value: str) -> tuple[int, ...]:
    return tuple((list(map(int, value.split('.'))) + [0, 0, 0])[:3])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--arch', required=True, choices=('arm64', 'x86_64', 'universal2'))
    parser.add_argument('--target-macos', required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('Run native bundle verification on macOS')
    app = args.app.resolve()
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    assert version_parts(info['LSMinimumSystemVersion']) <= version_parts(args.target_macos)
    assert info['CFBundleShortVersionString'] == '5.0'
    required_arches = {'arm64', 'x86_64'} if args.arch == 'universal2' else {args.arch}
    checked = []
    for path in sorted(app.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as stream:
            if stream.read(4) not in MACHO_MAGIC:
                continue
        arches = set(subprocess.check_output(['lipo', '-archs', str(path)], text=True).split())
        assert required_arches <= arches, f'{path}: architecture {arches}, need {required_arches}'
        commands = subprocess.check_output(['otool', '-l', str(path)], text=True)
        versions = re.findall(r'\bminos\s+(\d+(?:\.\d+)+)', commands)
        versions += re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\d+(?:\.\d+)+)', commands)
        assert versions, f'No minimum macOS metadata: {path}'
        actual = max(versions, key=version_parts)
        assert version_parts(actual) <= version_parts(args.target_macos), f'{path}: needs {actual}, target {args.target_macos}'
        checked.append({'path':path.relative_to(app).as_posix(), 'arch':sorted(arches), 'minimum_macos':actual})
    assert checked, 'No Mach-O binaries found'
    result = {'version':'5.0','architecture':args.arch,'target_macos':args.target_macos,'binaries':checked}
    destination = app.parent / 'compatibility.json'
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(checked)} Mach-O files; {args.arch}; minimum OS <= {args.target_macos}')


if __name__ == '__main__':
    main()
