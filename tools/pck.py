"""Read-only Godot PCK inventory and selective extraction for the local install."""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path


def inventory(path: Path):
    with path.open('rb') as f:
        f.seek(-12, 2)
        size, magic = struct.unpack('<Q4s', f.read(12))
        if magic != b'GDPC':
            raise ValueError('No appended PCK footer')
        start = path.stat().st_size - 12 - size
        f.seek(start)
        magic, version, major, minor, patch, flags = struct.unpack('<4s5I', f.read(24))
        if magic != b'GDPC' or version != 4 or flags & 1:
            raise ValueError(f'Unsupported or encrypted PCK: {version=} {flags=}')
        base, directory = struct.unpack('<QQ', f.read(16))
        f.seek(start + directory)
        count, = struct.unpack('<I', f.read(4))
        entries = []
        for _ in range(count):
            n, = struct.unpack('<I', f.read(4))
            name = f.read(n).rstrip(b'\0').decode('utf-8')
            offset, length = struct.unpack('<QQ', f.read(16))
            digest = f.read(16).hex()
            entry_flags, = struct.unpack('<I', f.read(4))
            entries.append(dict(path=name, offset=start+base+offset, size=length,
                                md5=digest, flags=entry_flags))
    return dict(version=version, engine=f'{major}.{minor}.{patch}', start=start,
                base=base, directory=directory, entries=entries)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('game', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    info = inventory(args.game)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'inventory.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    extracted = 0
    with args.game.open('rb') as f:
        for entry in info['entries']:
            name = entry['path'].removeprefix('res://')
            if not name.endswith(('.gd', '.gdc', '.remap', '.cfg', '.godot', '.csv', '.json')) and name != 'project.binary':
                continue
            dest = (args.output / name).resolve()
            if args.output.resolve() not in dest.parents:
                raise ValueError('Unsafe resource path')
            if entry['flags'] & 1:
                raise ValueError('Encrypted resource')
            f.seek(entry['offset'])
            data = f.read(entry['size'])
            import hashlib
            if hashlib.md5(data).hexdigest() != entry['md5']:
                raise ValueError(f'PCK digest mismatch: {name}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            extracted += 1
    print(json.dumps(dict(engine=info['engine'], entries=len(info['entries']), extracted=extracted), ensure_ascii=False))


if __name__ == '__main__':
    main()
