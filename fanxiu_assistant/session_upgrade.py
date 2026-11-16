"""Stage an immutable copy of our scripts; a local bridge swaps only when idle."""
import hashlib
import json
from pathlib import Path
import shutil


def stage_bridge(folder):
    folder = Path(folder)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(folder.glob('*.gd'))}
    required = {'assistant.gd', 'resource_budget.gd', 'session_upgrade.gd'}
    if not required <= files.keys():
        raise RuntimeError('桥接更新文件不完整；保留现有游戏与桥接')
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:24]
    target = folder / '_revisions' / digest
    target.mkdir(parents=True, exist_ok=True)
    for name, expected in files.items():
        path = target / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('不可变桥接目录校验失败；未激活更新')
        if not path.exists():
            temporary = path.with_suffix('.gd.tmp')
            shutil.copy2(folder / name, temporary)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise RuntimeError('桥接文件复制校验失败；未激活更新')
            temporary.replace(path)
    manifest = {'schema': 1, 'target': f'_revisions/{digest}/assistant.gd', 'files': files}
    path = folder / 'session-upgrade.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8')) == manifest:
        return manifest
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    return manifest
