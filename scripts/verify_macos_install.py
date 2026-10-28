"""Mount a DMG, copy its app to a clean path, and check native startup."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dmg',type=Path)
    args=parser.parse_args()
    result=subprocess.check_output(['hdiutil','attach','-readonly','-nobrowse','-plist',str(args.dmg.resolve())])
    mounted=plistlib.loads(result)
    mount=next(Path(item['mount-point']) for item in mounted['system-entities'] if 'mount-point' in item)
    try:
        with tempfile.TemporaryDirectory(prefix='astra-clean-install-') as temporary:
            root=Path(temporary)
            app=root/'Applications with spaces'/'Astra Studio.app'
            shutil.copytree(mount/'Astra Studio.app',app,symlinks=True)
            subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
            executable=app/'Contents/MacOS/Astra Studio'
            env=dict(os.environ, ASTRA_DATA_DIR=str(root/'clean profile'), QT_QPA_PLATFORM='cocoa')
            with (root/'startup.log').open('wb') as log:
                process=subprocess.Popen([str(executable)],env=env,cwd=root,stdout=log,stderr=log)
                try:
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        pass
                    else:
                        raise RuntimeError(f'App exited during startup: {process.returncode}; '+(root/'startup.log').read_text(errors='replace'))
                    # Settings may be written only on a normal window close;
                    # this bounded startup probe terminates the process below.
                    assert (root/'clean profile'/'workspace'/'example.py').is_file(), 'First-launch workspace was not created'
                    print('PASS: DMG mounted, app copied, signature valid, native Cocoa startup and clean profile verified')
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
    finally:
        subprocess.run(['hdiutil','detach',str(mount)],check=True)


if __name__=='__main__':
    main()
