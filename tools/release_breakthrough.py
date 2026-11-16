"""Publish only the exact candidate that passed this version's live acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.version import APP_TITLE, EXE_NAME, VERSION


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, text):
    if path.exists():
        backup = ROOT / '.private/backups/breakthrough-publication' / path.relative_to(ROOT)
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(path, backup)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--acceptance', type=Path, required=True)
    args = parser.parse_args()
    acceptance = read(args.acceptance)
    info = read(ROOT / 'dist/build-info.json')
    checks = {name:read(ROOT / 'runtime/exe-validation' / file) for name,file in {
        'offline_regression':'quick-regression.json', 'interface':'breakthrough-ui.json',
        'standalone':'summary.json', 'live_interface':'breakthrough-live-ui.json', 'current_planning':'current-planning-audit.json', 'game_contracts':'game-0.2.30-audit.json',
    }.items()}
    fingerprint = source_fingerprint(ROOT)
    exe = ROOT / 'dist' / EXE_NAME
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    assert info['validation_status'] == acceptance['status'] == 'PASS'
    assert acceptance['elapsed_seconds'] >= 1800 and not acceptance['failures']
    assert info['source_fingerprint'] == acceptance['source_fingerprint'] == fingerprint
    assert info['sha256'] == acceptance['exe_sha256'] == digest
    assert info['app_version'] == VERSION == acceptance['app_version']
    for name, record in checks.items():
        assert record['status'] == 'PASS' and record['source_fingerprint'] == fingerprint, name
    assert checks['standalone']['exe_sha256'] == digest
    assert checks['offline_regression']['positive_task_paths'] == checks['offline_regression']['task_count'] == 42
    initial, final = acceptance['initial'], acceptance['final']
    actions = {k:v-initial['stats'].get(k,0) for k,v in final['stats'].items() if k not in ('success','failed') and v>initial['stats'].get(k,0)}
    # Keep the full local acceptance evidence outside the distributable. No player inventory in ZIP.
    public_acceptance = {key:acceptance[key] for key in ('status','elapsed_seconds','required_seconds','samples','started','finished','failures','source_fingerprint','exe_sha256','app_version','game_version','inventory_refreshes','protected_equipment_checked','tradable_equipment_checked','preserved_unbound_item_types_checked','fixed_item_types_checked')}
    report = {'status':'PASS','app_version':VERSION,'sha256':digest,'source_fingerprint':fingerprint,
              'acceptance':public_acceptance,'checks':checks,'confirmed_actions_during_monitoring':actions,
              'coverage_limit':'42项任务均有隔离正向条件测试；实机只确认监控记录列出的可用玩法。未开放、无目标或缺材料的玩法不算实机执行通过。'}
    report_path = ROOT / 'dist' / f'{APP_TITLE}-验证报告.json'
    write(report_path,json.dumps(report,ensure_ascii=False,indent=2))
    validation = f'''# {APP_TITLE} 验证记录

本次源码指纹：`{fingerprint}`。

- Python 回归 {checks['offline_regression']['python_tests']} 项，桥接隔离检查 {checks['offline_regression']['bridge_checks']} 项通过；42 项任务都有正向条件路径。这些是隔离测试。
- 本版最终候选实机连续监控 {acceptance['elapsed_seconds']} 秒，采样 {acceptance['samples']} 次，无验收失败。游戏版本 {acceptance.get('game_version')}，桥接修订 {info['bridge_revision']}。
- 监控期间服务器确认的操作：{json.dumps(actions,ensure_ascii=False)}。
- 三个突破条件、单一目标、材料缺口、丹药折叠设置、42 个按钮、浅深色与移动布局通过前端检查。
- EXE 两次在 PATH 无 Python、清除 Python/Tcl 环境变量、中文带空格路径下自检通过；运行时已内置。没有独立干净虚拟机的实测，不能承诺所有 Windows 版本。
- 实机监控检查 {acceptance['preserved_unbound_item_types_checked']} 种受保护未绑定库存、{acceptance['tradable_equipment_checked']} 件分类保护装备、{acceptance['protected_equipment_checked']} 件游戏锁定/手动保护装备、{acceptance['fixed_item_types_checked']} 种固定锁物品。数量为0的类别没有本轮实机保护触发证据；固定锁阻断另有隔离测试。未检测到受保护库存减少。
- {'本轮没有材料齐全后成功突破的实机结果；补齐后执行与概率不足等待已通过隔离状态序列测试。' if not actions.get('breakthrough') else '本轮已有游戏确认的成功突破，次数见操作增量。'}

42 项任务的隔离测试不代表全部后期玩法都已在当前账号实机完成。未开放、没有指定对象或条件不足的玩法保持等待，不记为成功。不绕过服务器开放条件，不保证未来所有游戏版本都兼容。

SHA256：`{digest}`。
'''
    write(ROOT / 'VALIDATION.md', validation)
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    marker = readme.index('## 双击使用')
    readme = f'''# {APP_TITLE}

本版修复自动突破在错误掉落池刷材料、关闭丹药设置后不显示或预留突破材料、手动执行丢失其他任务保护规则、普通模式下战败被误报成结算未确认的问题。突破卡统一为一个成功率目标，显示修为、材料和概率三个条件，丹药准备单独展开。

最终候选已完成 {acceptance['elapsed_seconds']} 秒实机连续监控；详细范围和限制见 `VALIDATION.md`。

'''+readme[marker:]
    readme = readme.replace('| 境界突破最低成功率 | **60%**（关闭联动时使用） |','| 境界突破目标成功率 | **60%**，只有一个目标；旧配置保留原实际目标 |')
    readme = readme.replace('| 突破概率联动目标 | **100%**，可调；开启联动时达目标才突破 |\n','')
    readme = readme.replace('| 自动提升概率 / 找料 / 炼丹 / 服丹 | **全部开启**，四项子开关位于突破按钮下 |','| 自动找料 / 用丹药提概率 / 炼丹 / 服丹 | 默认开启，丹药设置单独展开；按需可关闭 |')
    catalogue = acceptance.get('steam_initial', {}).get('definitions')
    if catalogue:
        readme = readme.replace('当前0.2.20的947个定义目录没有装备类', f"本次游戏{acceptance.get('game_version')}的{catalogue}个定义目录没有装备类")
    readme = readme.replace('多人秘境在游戏0.2.20配置中为关闭且暂停。', f"多人秘境在本次游戏{acceptance.get('game_version')}配置中为关闭且暂停。")
    readme = readme.replace('猫头凡修助手0.x.exe', EXE_NAME)
    readme += '\n## 自动突破说明\n\n修为满、可用材料齐全、当前成功率下限达到目标后才会提交原生突破。自动找料在自动挂机模式下优先选择有对应缺料掉落的已通关关卡，补齐后恢复最高关卡；指定关卡时不自动换图。随机掉落不保证固定时间补齐。普通炼丹和炼器会预留突破本体材料，关闭丹药提概率也不会撤掉这份预留。只有成功率不足且相应开关开启，才炼制或使用当前境界突破丹。每次只处理一颗，等待游戏确认后重算。\n'
    write(ROOT / 'README.md', readme)
    archive = ROOT / 'dist' / f'{APP_TITLE}-Windows-x64.zip'
    with zipfile.ZipFile(archive.with_suffix('.zip.tmp'), 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in [exe, ROOT/'README.md', ROOT/'VALIDATION.md', report_path, ROOT/'dist/build-info.json']:
            bundle.write(path, path.name)
    archive.with_suffix('.zip.tmp').replace(archive)
    print(json.dumps({'exe':str(exe),'zip':str(archive),'sha256':digest},ensure_ascii=False))


if __name__ == '__main__':
    main()
