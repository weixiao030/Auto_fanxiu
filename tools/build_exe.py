"""Build a candidate; publish after acceptance or an explicit user waiver and checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import re
import runpy

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.server import MIN_BRIDGE_REVISION


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_functional_waiver(record, info, source, checks):
    if (not isinstance(record, dict) or record.get('user_requested_skip_monitoring') is not True
            or not isinstance(record.get('request'), str) or not record['request'].strip()):
        raise ValueError('需要记录用户明确免重新监控的指令')
    if record.get('app_version') != info['app_version'] or record.get('source_fingerprint') != source:
        raise ValueError('功能验收指令必须绑定当前版本与源码')
    for name in ('quick-regression', 'summary', 'native-contracts', 'project-ui', 'growth-ui', 'review-ui'):
        check = checks.get(name, {})
        if check.get('status') != 'PASS' or check.get('source_fingerprint') != source:
            raise ValueError('当前候选检查尚未通过：' + name)
    if checks['summary'].get('exe_sha256') != info['sha256']:
        raise ValueError('独立EXE检查与候选不一致')
    regression = checks['quick-regression']
    if regression.get('positive_task_paths', 0) != regression.get('task_count') or not regression.get('task_count'):
        raise ValueError('任务正向路径覆盖不完整')
    if checks['native-contracts'].get('failures'):
        raise ValueError('原生接口核对失败')


def main():
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--candidate',action='store_true')
    modes.add_argument('--acceptance',type=Path)
    modes.add_argument('--user-waiver',type=Path)
    parser.add_argument('--candidate-dir',type=Path,default=ROOT/'.private/release-candidate')
    parser.add_argument('--functional-acceptance',type=Path,help='绑定当前候选的维护者功能验收指令')
    args=parser.parse_args()
    if args.functional_acceptance and not args.acceptance:
        parser.error('--functional-acceptance 仅用于已有完整稳定性验收的候选晋级')
    candidate=args.candidate_dir.resolve()
    if args.candidate:
        version_path=ROOT/'fanxiu_assistant/version.py'
        version=runpy.run_path(str(version_path))
        published=[int(m.group(1)) for path in (ROOT/'dist').glob('*.exe') if (m:=re.fullmatch(re.escape(version['APP_NAME'])+r'0[.](\d+)[.]exe',path.name))]
        # Every built version advances, even when an earlier build was superseded.
        number=max([int(version['VERSION'].split('.')[1]),*published])+1
        text=version_path.read_text(encoding='utf-8')
        text=re.sub(r"VERSION = '[^']+'",f"VERSION = '0.{number}'",text)
        backup=ROOT/'.private/backups/version-before-build.py';backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(version_path,backup)
        temp=version_path.with_suffix('.py.tmp');temp.write_text(text,encoding='utf-8');temp.replace(version_path)
    version=runpy.run_path(str(ROOT/'fanxiu_assistant/version.py'))
    name=version['EXE_NAME']
    source=source_fingerprint(ROOT)
    if args.candidate:
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
            '--name',version['APP_TITLE'],'--distpath',str(candidate),'--workpath',str(ROOT/'.private/exe-build'),
            '--specpath',str(ROOT/'.private'),'--add-data',str(ROOT/'web')+';web',
            *[arg for p in sorted((ROOT/'bridge').glob('*.gd')) for arg in ('--add-data',str(p)+';bridge')],
            '--hidden-import','tkinter',
            '--hidden-import','tkinter.filedialog',str(ROOT/'desktop_entry.py')],cwd=ROOT,check=True)
        exe=candidate/name
        info={'file':name,'bytes':exe.stat().st_size,'sha256':sha256(exe),
              'source_fingerprint':source,'validation_status':'UNVERIFIED_CANDIDATE',
              'version_gate':False,'previously_tested_game_versions':['0.2.18','0.2.20'],'bridge_revision':MIN_BRIDGE_REVISION, 'app_version':version['VERSION'],
              'platform':'Windows 10/11 x64','requires_python_install':False,'bundled_user_data':False}
        (candidate/'build-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(info,ensure_ascii=False))
        return
    if args.user_waiver:
        record=json.loads(args.user_waiver.read_text(encoding='utf-8'))
        info=json.loads((candidate/'build-info.json').read_text(encoding='utf-8'))
        checks={key:json.loads((ROOT/'runtime/exe-validation'/f'{key}.json').read_text(encoding='utf-8'))
                for key in ('quick-regression', 'summary', 'native-contracts', 'project-ui', 'growth-ui', 'review-ui')}
        try:
            validate_functional_waiver(record, info, source, checks)
        except ValueError as error:
            raise SystemExit(str(error))
        if info['source_fingerprint']!=source or info['sha256']!=sha256(candidate/name):
            raise SystemExit('候选文件与源码不一致')
        dist=ROOT/'dist';dist.mkdir(exist_ok=True)
        target=dist/name;temporary=target.with_suffix('.exe.tmp')
        shutil.copy2(candidate/name,temporary);temporary.replace(target)
        assert sha256(target)==info['sha256']
        info.update(validation_status='CHECKS_PASS_MONITORING_WAIVED',
                    monitoring_waiver=record,monitoring_rerun=False,full_growth_verified=False,
                    acceptance_basis="functional_checks_with_user_waived_additional_live_wait")
        (dist/'build-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(info,ensure_ascii=False))
        return
    report=(args.acceptance if args.acceptance.is_file() else args.acceptance/'result.json').resolve()
    if report.name!='result.json':raise SystemExit('发布需要完整验收result.json，不能使用进行中检查点')
    result=json.loads(report.read_text(encoding='utf-8'))
    if result.get('status')!='PASS' or result.get('elapsed_seconds',0)<1800 or result.get('failures'):
        raise SystemExit('必须先通过至少30分钟的真实连续验收，才能发布')
    info=json.loads((candidate/'build-info.json').read_text(encoding='utf-8'))
    if (result.get('source_fingerprint')!=source or info.get('source_fingerprint')!=source
            or info.get('sha256')!=sha256(candidate/name) or result.get('exe_sha256')!=info['sha256']
            or result.get('app_version')!=info['app_version'] or result.get('initial',{}).get('revision')!=info['bridge_revision']):
        raise SystemExit('候选EXE、当前源码与实机验收不一致，需要重新构建和验收')
    preflight=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/release_growth.py'),
        '--acceptance',str(report),'--candidate-dir',str(candidate),'--check-only',
        *(['--functional-acceptance',str(args.functional_acceptance.resolve())] if args.functional_acceptance else [])],
        cwd=ROOT,check=True,capture_output=True,text=True,encoding='utf-8')
    verified=json.loads(preflight.stdout)
    if not verified.get('release_ready'):
        raise SystemExit('发布验收尚未满足，保持现有dist不变')
    dist=ROOT/'dist';dist.mkdir(exist_ok=True)
    target=dist/name;temporary=target.with_suffix('.exe.tmp')
    shutil.copy2(candidate/name,temporary);temporary.replace(target)
    assert sha256(target)==info['sha256']
    info.update(validation_status='PASS',acceptance=str(report.relative_to(ROOT)),
                acceptance_seconds=result['elapsed_seconds'],game_version=result.get('game_version'),
                acceptance_basis=verified['acceptance_basis'],full_growth_verified=verified['full_growth_verified'],
                growth_chain_required=verified['growth_chain_required'],functional_acceptance=verified['functional_acceptance'])
    (dist/'build-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False))


if __name__=='__main__':main()
