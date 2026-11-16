"""Test the frozen HTTP/defaults with no Python on PATH and inspect its payload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0,str(ROOT))
from fanxiu_assistant.verification import source_fingerprint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,required=True)
    args=parser.parse_args()
    exe=args.exe.resolve()
    report_dir=ROOT/'runtime/exe-validation'
    report_dir.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    for name in ('PYTHONHOME','PYTHONPATH','TCL_LIBRARY','TK_LIBRARY','FANXIU_ASSISTANT_DATA_DIR'):
        env.pop(name,None)
    env['PATH']=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot']
    assert shutil.which('python',path=env['PATH']) is None
    out=[]
    for index in range(2):
        folder=report_dir/('中文 路径 '+str(index))
        folder.mkdir(exist_ok=True)
        target=folder/'凡修 助手.exe'
        shutil.copy2(exe,target)
        report=folder/'自检报告.json'
        result=subprocess.run([str(target),'--self-test',str(report)],cwd=folder,env=env,
                              timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
        data=json.loads(report.read_text(encoding='utf-8'))
        assert result.returncode==0 and data['status']=='PASS' and data['frozen'] is True
        out.append(data)
    archive=CArchiveReader(str(exe))
    names=list(archive.toc)
    for forbidden in ('.private/','bridge.key','config.json','capture-actions.json','run.exe','recovered-0.'):
        assert not any(forbidden in n.replace('\\','/') for n in names),forbidden
    for required in ('python310.dll','_tcl_data','_tk_data'):
        assert any(required in n for n in names),required
    for folder in ('web','bridge'):
        for source in (ROOT/folder).glob('*'):
            if source.is_file():
                key=str(source.relative_to(ROOT)).replace('/','\\')
                assert archive.extract(key)==source.read_bytes(),str(source)
    summary={'status':'PASS','exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
             'source_fingerprint':source_fingerprint(ROOT),'runs':len(out),'minimal_path_without_python':True,
             'cleared_python_and_tcl_env':True,'chinese_spaced_path':True,
             'frozen_http_and_defaults':out,'archive_entries':len(names),
             'python_and_tcl_tk_bundled':True,'private_runtime_or_game_files':False,
             'bundled_resources_match_accepted_sources':True,'clean_vm_tested':False}
    (report_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
