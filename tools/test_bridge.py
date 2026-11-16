"""Run the real bridge against in-memory fixtures in an isolated, game-free PCK."""
from pathlib import Path
import subprocess
from build_lab_pack import ROOT, write_pack

lab = ROOT / '.private'
engine = lab / 'bridge-lab-engine.exe'
if not engine.exists():
    raise SystemExit('先运行 python tools/check_bridge.py 准备隔离引擎')
files = {
    'res://project.godot': b'config_version=5\n[application]\nconfig/name="BridgeSafetyFixture"\nrun/main_scene="res://main.tscn"\n',
    'res://main.tscn': b'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://test.gd" id="1"]\n[node name="SafetyTest" type="Node"]\nscript=ExtResource("1")\n',
    'res://test.gd': (ROOT / 'tests/bridge_safety.gd').read_bytes(),
    'res://assistant.gd': (ROOT / 'bridge/assistant.gd').read_bytes(),
    'res://steam_inventory.gd': (ROOT / 'bridge/steam_inventory.gd').read_bytes(),
    'res://inventory.gd': (ROOT / 'bridge/inventory.gd').read_bytes(),
    'res://resource_budget.gd': (ROOT / 'bridge/resource_budget.gd').read_bytes(),
    'res://session_upgrade.gd': (ROOT / 'bridge/session_upgrade.gd').read_bytes(),
    'res://growth_evidence.gd': (ROOT / 'bridge/growth_evidence.gd').read_bytes(),
    'res://fake_main.gd': 'extends Node\nvar auto_pill_ui\nvar _realm_mode\nvar batch_limit=15\nfunc _gacha_batch_count(): return batch_limit\nvar battle_flow = {"in_combat": false}\nvar dungeon_system = {"current_node":null,"current_battle_id":""}\nvar settlements=[]\nvar restored=[]\nvar restore_starts=true\nfunc _finish_external_battle_settlement(answer, _local, _context): settlements.append(answer)\nfunc _on_external_battle_ended(_local, _context): pass\nfunc _on_external_battle_requested(battle, context):\n restored.append([battle,context])\n if restore_starts:\n  battle_flow.in_combat=true\n  battle_flow.battle_state_changed.emit(true)\n'.encode('utf-8'),
    'res://scripts/data/dungeon_node.gd': 'extends RefCounted\nvar difficulty\nvar tier\nvar stage\nfunc _init(d,t,s):\n difficulty=d\n tier=t\n stage=s\n'.encode('utf-8'),
    'res://scripts/systems/refine_system.gd': b'extends RefCounted\nstatic func get_refine_item_info(mid): return {"id":mid,"category":"breakthrough_main" if mid in [1001,1008] else "herb","value":6}\nstatic func get_progress_value(info): return int(info.get("value",0))\nstatic func calculate_level(mats):\n var total=0\n for mid in mats: total += int(mats[mid])*6\n return {"level":int(total/100),"total":total}\nstatic func get_auto_fill_exclusions(): return {"999":true}\nstatic func get_preference_candidates(): return [{"kind":"material","id":1008}]\nstatic func get_valid_preference(p): return p if p.get("kind")=="material" and p.get("id")==1008 else {}\n',
    'res://scripts/systems/equipment_upgrade_system.gd': b'extends RefCounted\nstatic func requirements(_eq): return [{"id": 1, "count": 2}]\n',
    'res://scripts/systems/resource_pack_system.gd': b'extends RefCounted\nstatic func recipes(size): return [{"pack_kind":"herb","pack_resource_id":7001,"id":9001}] if size==4 else []\nstatic func cost(_pack): return 5\nstatic func owned(_pack): return 115\nstatic func remaining(): return 2\n',
    'res://scripts/data/pill_data.gd': b'extends RefCounted\nstatic func get_material_name(_kind,id): return str(id)\nstatic func is_effect_covered(_pill,_buffs): return false\nstatic func get_pill_info(pid): return {"id":pid,"effects":[{"type":"heal_injury"} if pid == 6001 else {"type":"breakthrough_bonus","value":0.05}],"recipes":[{"realm":0,"materials":[{"kind":"material","id":1,"count":3},{"kind":"herb","id":7001,"count":10}]}]}\nstatic func get_recipe_materials(pill,index): return pill.recipes[index].materials if index>=0 and index<pill.recipes.size() else []\n',
    'res://fake_server.gd': b'extends Node\nvar pending_elixirs=[]\n',
    'res://.godot/global_script_class_cache.cfg': b'list=[]\n',
}
pack = lab / 'bridge-safety.pck'
write_pack(pack, files)
result = subprocess.run([str(engine), '--headless', '--main-pack', str(pack)], capture_output=True, timeout=20)
output = (result.stdout + result.stderr).decode('utf-8', errors='replace')
(lab / 'bridge-safety.log').write_text(output, encoding='utf-8')
print(output)
if result.returncode or 'ERROR:' in output or 'SCRIPT ERROR' in output or 'BRIDGE_SAFETY_CHECKS=' not in output:
    raise SystemExit(1)
