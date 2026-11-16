"""Bind acceptance to the exact distributable sources, excluding private/user data."""
import hashlib
from pathlib import Path


def source_fingerprint(root):
    root=Path(root)
    files=sorted([*root.joinpath('fanxiu_assistant').rglob('*.py'),*root.joinpath('bridge').glob('*.gd'),
                  *root.joinpath('web').glob('*'),root/'desktop_entry.py'])
    digest=hashlib.sha256()
    for path in files:
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode('utf-8')+b'\0')
            digest.update(path.read_bytes())
    return digest.hexdigest()
