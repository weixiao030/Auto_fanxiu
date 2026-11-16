"""Exercise the actual late-load updater without any game or network resources."""
from pathlib import Path
import subprocess
import shutil
from build_lab_pack import ROOT, write_pack

lab = ROOT / '.private'
files = {
    'res://project.godot': b'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
    'res://main.tscn': b'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://test.gd" id="1"]\n[node name="Test" type="Node"]\nscript=ExtResource("1")\n',
    'res://.godot/global_script_class_cache.cfg': b'list=[]\n',
    'res://test.gd': (ROOT / 'tests/bridge_session_upgrade.gd').read_bytes(),
    'res://session_upgrade.gd': (ROOT / 'bridge/session_upgrade.gd').read_bytes(),
    'res://resource_budget.gd': (ROOT / 'bridge/resource_budget.gd').read_bytes(),
}
engine_dir = lab / 'session-engine'; engine_dir.mkdir(exist_ok=True)
engine = engine_dir / 'session-lab.exe'
if not engine.exists(): shutil.copy2(lab / 'bridge-lab-engine.exe', engine)
for dll in lab.glob('*.dll'):
    if not (engine_dir / dll.name).exists(): shutil.copy2(dll, engine_dir / dll.name)
pack = engine_dir / 'bridge-session.pck'; write_pack(pack, files)
run = subprocess.run([str(engine), '--headless', '--main-pack', str(pack)], capture_output=True, timeout=20, cwd=engine_dir)
output = (run.stdout + run.stderr).decode('utf-8', errors='replace')
(lab / 'bridge-session.log').write_text(output, encoding='utf-8')
print(output)
if run.returncode or 'SCRIPT ERROR' in output or 'FAILURES=[]' not in output:
    raise SystemExit(1)
