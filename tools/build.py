#!/usr/bin/python3
"""Build a clean source distribution using an explicit file allowlist."""
import os
from pathlib import Path
import tarfile
import tempfile

root=Path(__file__).resolve().parents[1]
target=root.parent/(root.name+'.tar.gz')
files=[root/name for name in ('app_info.py','capture.py','classic_ui.py','workspace.py','workflows.py',
    'panel.py','customize.py','storage.py','ocr.py','install.py','README.txt','README.md','LICENSE')]
files+=sorted((root/'tests').glob('*.py'))+[root/'tests/README.txt']+sorted((root/'tools').glob('*.py'))
files+=[root/'vendor/COPYRIGHT-gi-cairo']+sorted((root/'vendor/gi').glob('*.so'))
files += sorted((root/'docs/images').glob('*.png'))
fd,name=tempfile.mkstemp(prefix='.lw-build-',suffix='.tar.gz',dir=target.parent)
os.close(fd)
try:
    with tarfile.open(name,'w:gz') as archive:
        for file in files:
            if not file.is_file() or file.is_symlink():raise RuntimeError('Missing/unsafe distribution file: '+str(file))
            archive.add(file,arcname=str(Path(root.name)/file.relative_to(root)),recursive=False)
    os.replace(name,target)
finally:Path(name).unlink(missing_ok=True)
print(target)
