"""Persistent user data and bundled assets for the standalone application."""
from pathlib import Path
import os
import shutil
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
SOURCE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
DATA = Path(os.environ['FANXIU_ASSISTANT_DATA_DIR']) if os.environ.get('FANXIU_ASSISTANT_DATA_DIR') else (Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'FanxiuAssistant' if FROZEN else SOURCE)
ROOT = DATA / 'resources' if FROZEN else SOURCE
RUNTIME = DATA / 'runtime'
PRIVATE = DATA / '.private'
BACKUPS = PRIVATE / 'backups'
INVENTORY_ICONS = PRIVATE / 'inventory-icons'


def prepare_resources():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not FROZEN:
        return
    for folder in ('web', 'bridge'):
        for source in (SOURCE / folder).rglob('*'):
            if not source.is_file():
                continue
            target = ROOT / folder / source.relative_to(SOURCE / folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != source.read_bytes():
                if target.exists():
                    backup = BACKUPS / 'previous-resources' / folder / source.relative_to(SOURCE / folder)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                temp = target.with_suffix(target.suffix + '.tmp')
                shutil.copyfile(source, temp)
                temp.replace(target)
