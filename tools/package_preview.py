"""Package an explicitly labelled prerelease; never promote it to formal dist."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--acceptance', required=True, type=Path)
    parser.add_argument('--candidate-dir', required=True, type=Path)
    args = parser.parse_args()
    candidate = args.candidate_dir.resolve()
    # All existing stability, hash, interface and source checks remain mandatory.
    run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'tools/release_growth.py'),
        '--acceptance', str(args.acceptance.resolve()), '--candidate-dir', str(candidate), '--check-only'],
        cwd=ROOT, check=True, capture_output=True, text=True, encoding='utf8')
    report = json.loads(run.stdout)
    info = json.loads((candidate/'build-info.json').read_text(encoding='utf8'))
    version = report['app_version']
    if not version.replace('.', '').isdigit():
        raise ValueError('invalid version')
    output = ROOT/'.private'/('preview-'+version)
    output.mkdir(parents=True, exist_ok=True)
    report['prerelease'] = True
    report['formal_release_promoted'] = False
    report_file = output/'VALIDATION.json'
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    info.update(validation_status='PRERELEASE_'+report['status'], prerelease=True,
        full_growth_verified=report['release_ready'], formal_release_promoted=False,
        acceptance_seconds=report['acceptance']['elapsed_seconds'], game_version=report['acceptance']['game_version'])
    info_file = output/'build-info.json'
    info_file.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf8')
    exe = candidate/info['file']
    if hashlib.sha256(exe.read_bytes()).hexdigest() != report['sha256']:
        raise ValueError('accepted executable changed')
    docs = ['README.md', 'VALIDATION.md', 'PARAMETERS.md', 'UPDATE_0.2.116.md',
        'FULL_LOGIC_AUDIT.md', 'GROWTH_DESIGN.md', 'MODLOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md']
    entries = [(exe, exe.name), (report_file, report_file.name), (info_file, info_file.name)]
    entries += [(ROOT/name, name) for name in docs]
    entries += [(p, p.relative_to(ROOT).as_posix()) for folder in ('licenses','docs/images') for p in sorted((ROOT/folder).glob('*')) if p.is_file()]
    if len({n for _,n in entries}) != len(entries) or not all(p.is_file() for p,_ in entries):
        raise ValueError('invalid package whitelist')
    archive = output/f'Auto_fanxiu-{version}-preview-Windows-x64.zip'
    temporary = archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path, name in entries:
            bundle.write(path, name)
    with zipfile.ZipFile(temporary) as bundle:
        if set(bundle.namelist()) != {n for _,n in entries}:
            raise ValueError('unexpected archive entries')
        if hashlib.sha256(bundle.read(exe.name)).hexdigest() != report['sha256']:
            raise ValueError('archive executable mismatch')
    temporary.replace(archive)
    checksum = output/'SHA256SUMS.txt'
    checksum.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n'
        for p in (archive, report_file, info_file)), encoding='utf8')
    print(json.dumps({'prerelease': True, 'formal_dist_modified': False, 'zip': str(archive),
        'exe_sha256': report['sha256'], 'status': report['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
