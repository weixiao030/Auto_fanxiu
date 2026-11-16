"""Parse the bridge with a separate Godot engine and no game/login resources."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
from build_lab_pack import write_pack, ROOT

lab = ROOT / '.private'
lab.mkdir(exist_ok=True)
engine = lab / 'bridge-lab-engine.exe'
# The validation engine is a separate Godot-compatible executable, never run.exe.
# Reuse the private local cache or copy an explicitly configured test engine.
configured = os.environ.get('FANXIU_TEST_ENGINE')
if configured:
    source = Path(configured).expanduser().resolve()
    if not source.is_file() or source.name.lower() == 'run.exe':
        raise SystemExit('FANXIU_TEST_ENGINE 必须是独立测试引擎文件，不能是游戏 run.exe')
    if source != engine.resolve():
        shutil.copy2(source, engine)
    companion = source.parent / 'GodotMonoDecompNativeAOT.dll'
    if companion.is_file() and companion.resolve() != (lab / companion.name).resolve():
        shutil.copy2(companion, lab / companion.name)
elif not engine.is_file():
    raise SystemExit('请将独立 Godot 4.7+ 测试引擎绝对路径设为 FANXIU_TEST_ENGINE，或放到 .private/bridge-lab-engine.exe；不使用游戏程序')
(lab / 'release-manifest.json').write_text('{"version":"0.2.18"}', encoding='utf-8')
(lab / 'override.cfg').write_text('[autoload]\nExternalAssistant="*' + (ROOT / 'bridge/loader.gd').as_posix() + '"\n', encoding='utf-8')
write_pack(lab / 'bridge-lab.pck', {
    'res://project.godot': b'config_version=5\n[application]\nconfig/name="AssistantSyntaxLab"\nrun/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
    'res://main.tscn': b'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://assistant.gd" id="1"]\n[node name="AssistantSyntaxLab" type="Node"]\nscript=ExtResource("1")\n',
    'res://assistant.gd': (ROOT / 'bridge/assistant.gd').read_bytes(),
    'res://steam_inventory.gd': (ROOT / 'bridge/steam_inventory.gd').read_bytes(),
    'res://inventory.gd': (ROOT / 'bridge/inventory.gd').read_bytes(),
    'res://resource_budget.gd': (ROOT / 'bridge/resource_budget.gd').read_bytes(),
    'res://session_upgrade.gd': (ROOT / 'bridge/session_upgrade.gd').read_bytes(),
    'res://growth_evidence.gd': (ROOT / 'bridge/growth_evidence.gd').read_bytes(),
    'res://.godot/global_script_class_cache.cfg': b'list=[]\n',
})
result = subprocess.run([str(engine), '--headless', '--main-pack', str(lab / 'bridge-lab.pck'), '--quit-after', '3'], capture_output=True, timeout=20)
output = (result.stdout + result.stderr).decode('utf-8', errors='replace')
(lab / 'bridge-validation.log').write_text(output, encoding='utf-8')
print(output)
if result.returncode or 'SCRIPT ERROR' in output or 'Parse Error' in output:
    print(f'Engine exit: {result.returncode}')
    raise SystemExit(1)
count = output.count('No game singletons; validation only.')
print(f'Isolated validation passed; bridge instances: {count}')
if count != 2:
    raise SystemExit('External override/autoload did not load as expected')
(lab / 'release-manifest.json').write_text('{"version":"future"}', encoding='utf-8')
result = subprocess.run([str(engine), '--headless', '--main-pack', str(lab / 'bridge-lab.pck'), '--quit-after', '3'], capture_output=True, timeout=20)
output = (result.stdout + result.stderr).decode('utf-8', errors='replace')
if result.returncode or 'SCRIPT ERROR' in output or 'Parse Error' in output or output.count('No game singletons; validation only.') != 2:
    print(output)
    raise SystemExit('Future game version did not load the bridge')
print('Future version autoload passed; no version allowlist.')
