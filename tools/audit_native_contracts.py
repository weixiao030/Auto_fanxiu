"""Read native signatures privately; report only method names and argument counts."""
import json
import argparse
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.verification import source_fingerprint


def arguments(source, start):
    depth, quoted, escaped, fields, begin = 1, None, False, [], start
    for at in range(start, len(source)):
        ch = source[at]
        if quoted:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quoted:
                quoted = None
            continue
        if ch in ('"', "'"):
            quoted = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
            if depth == 0:
                tail = source[begin:at].strip()
                if tail:
                    fields.append(tail)
                return fields
        elif ch == ',' and depth == 1:
            fields.append(source[begin:at].strip())
            begin = at + 1
    raise ValueError('unterminated argument list')


def _version_key(path: Path):
    match = re.fullmatch(r'recovered-(\d+)\.(\d+)\.(\d+)', path.name)
    return tuple(int(value) for value in match.groups()) if match else (-1, -1, -1)


def _select_native_root(requested: str | None) -> tuple[Path, str]:
    if requested:
        root = Path(requested).resolve()
        if not root.is_dir():
            raise SystemExit(f'找不到新版原生恢复目录: {root}')
    else:
        candidates = [p for p in (ROOT / '.private').glob('recovered-*') if p.is_dir()]
        if not candidates:
            raise SystemExit('未找到 .private/recovered-* 原生恢复目录')
        root = max(candidates, key=_version_key)
    version_file = root / 'scripts/data/client_version.gd'
    version_match = re.search(r'VERSION\s*:\s*=\s*"([^"]+)"', version_file.read_text(encoding='utf-8')) if version_file.is_file() else None
    version = version_match.group(1) if version_match else root.name.removeprefix('recovered-')
    return root, version


def main(argv=None):
    parser = argparse.ArgumentParser(description='核对当前原生恢复目录与桥接 API 签名')
    parser.add_argument('--native-root', help='指定 .private/recovered-* 目录；默认选择最高版本')
    args = parser.parse_args(argv)
    native_root, game_version = _select_native_root(args.native_root)
    native = native_root / 'scripts/autoload/api_client.gd'
    content = native.read_text(encoding='utf-8')
    signatures = {}
    for match in re.finditer(r'^func\s+(\w+)\s*\(', content, re.M):
        fields = arguments(content, match.end())
        signatures[match.group(1)] = (sum('=' not in p for p in fields), len(fields))
    calls, failures = [], []
    for path in (ROOT / 'bridge').glob('*.gd'):
        source = path.read_text(encoding='utf-8')
        for match in re.finditer(r'\bapi\.(\w+)\s*\(', source):
            method = match.group(1)
            if method in ('has_signal', 'has_method', 'get', 'set'):
                continue  # inherited Godot Object methods
            count = len(arguments(source, match.end()))
            limits = signatures.get(method)
            valid = limits is not None and limits[0] <= count <= limits[1]
            row = {'file': path.relative_to(ROOT).as_posix(), 'line': source.count('\n', 0, match.start()) + 1,
                   'method': method, 'arguments': count, 'native_minimum': limits[0] if limits else None,
                   'native_maximum': limits[1] if limits else None, 'valid': valid}
            calls.append(row)
            if not valid:
                failures.append(row)
    result = {'status': 'FAIL' if failures else 'PASS', 'game_version': game_version,
              'native_root': str(native_root),
              'native_api_sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
              'source_fingerprint': source_fingerprint(ROOT), 'call_sites': len(calls),
              'distinct_native_methods': len({r['method'] for r in calls}), 'calls': calls,
              'failures': failures, 'real_game_mutations': 0,
              'scope': 'Static method existence and argument arity; does not prove server semantics.'}
    (ROOT / 'runtime/exe-validation/native-contracts.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'calls'}, ensure_ascii=False))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
