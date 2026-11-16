"""Publish the exact accepted candidate with sanitized, scoped evidence."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.server import MIN_BRIDGE_REVISION
from fanxiu_assistant.flow_evidence import assess_flow
from fanxiu_assistant.task_catalog import TASK_ORDER
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.version import APP_TITLE, EXE_NAME, VERSION


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write(path, content):
    if path.exists():
        backup = ROOT / '.private/backups/growth-publication' / path.relative_to(ROOT)
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(path, backup)
    temporary = path.with_name(path.name + '.publication-tmp')
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--acceptance', required=True, type=Path)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--candidate-dir', type=Path,
                        help='直接只读检查候选包；必须同时使用 --check-only')
    args = parser.parse_args()
    if args.candidate_dir and not args.check_only:
        parser.error('--candidate-dir 仅用于 --check-only，完整门槛通过后再发布')
    require(args.acceptance.name == 'result.json', '需要完整监控结果，不能发布检查点')
    a = read(args.acceptance)
    package = args.candidate_dir.resolve() if args.candidate_dir else ROOT / 'dist'
    info = read(package / 'build-info.json')
    checks = {name: read(ROOT / 'runtime/exe-validation' / file) for name, file in {
        'regression': 'quick-regression.json', 'standalone': 'summary.json', 'interface': 'growth-ui.json', 'native': 'native-contracts.json', 'project': 'project-ui.json'}.items()}
    source = source_fingerprint(ROOT)
    require(info['file'] == EXE_NAME, '候选文件名与当前版本不一致')
    exe = package / EXE_NAME
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    require(a['status'] == 'PASS', '连续实机验收未通过')
    allowed = ('UNVERIFIED_CANDIDATE', 'PASS') if args.candidate_dir else ('PASS',)
    require(info['validation_status'] in allowed, '候选状态不满足当前发布检查')
    require(a['elapsed_seconds'] >= 1800 and not a['failures'], '监控不足30分钟或存在失败')
    require(source == info['source_fingerprint'] == a['source_fingerprint'], '源码与受验版本不同')
    require(digest == info['sha256'] == a['exe_sha256'] == checks['standalone']['exe_sha256'], 'EXE哈希不一致')
    require(VERSION == info['app_version'] == a['app_version'], '应用版本不一致')
    require(info['bridge_revision'] == MIN_BRIDGE_REVISION == a['initial']['revision'] == a['final']['revision'], '桥接版本不一致')
    for name, record in checks.items():
        require(record['status'] == 'PASS' and record['source_fingerprint'] == source, name + '检查不属于本版本')
    require(checks['regression']['positive_task_paths'] == checks['regression']['task_count']
            == checks['interface']['task_cards'] == len(TASK_ORDER), '全任务覆盖不完整')
    first, last = a['initial'], a['final']
    require(last['enabled'] and last['connected'] and last['ready'], '监控结束时未正常运行')
    actions = {k: v-first['stats'].get(k, 0) for k, v in last['stats'].items()
               if k not in ('success', 'failed') and v > first['stats'].get(k, 0)}
    refine = any(actions.get(k, 0) for k in ('refine', 'world_forge'))
    downstream = {k: actions[k] for k in ('alchemy', 'pill', 'breakthrough', 'upgrade', 'material_synth') if actions.get(k)}
    event_path = args.acceptance.parent / 'events.jsonl'
    events = [json.loads(line) for line in event_path.read_text(encoding='utf-8').splitlines() if line.strip()] if event_path.is_file() else []
    flow = assess_flow(events, started=a['started'], finished=a['finished'], revision=MIN_BRIDGE_REVISION)
    release_ready = bool(refine and downstream and flow['causal_chain_proven'])
    limit = ('本候选已确认原生炼化奖励补足缺口，经连续资源交接后实际完成强化或突破；只证明记录中列出的成长链。'
             if release_ready else '动作计数不能证明资源联动；本候选缺少原生奖励、连续投入与实际成长结果的完整记录，仍待实测。')
    public = ('status', 'elapsed_seconds', 'required_seconds', 'samples', 'started', 'finished', 'failures',
              'source_fingerprint', 'exe_sha256', 'app_version', 'game_version', 'inventory_refreshes',
              'protected_equipment_checked', 'tradable_equipment_checked', 'preserved_unbound_item_types_checked', 'fixed_item_types_checked')
    report = {'status': 'PASS' if release_ready else 'STABILITY_PASS_GROWTH_PENDING', 'release_ready': release_ready, 'app_version': VERSION, 'bridge_revision': MIN_BRIDGE_REVISION, 'sha256': digest,
        'source_fingerprint': source, 'acceptance': {k: a[k] for k in public},
        'native_contracts': {k: checks['native'][k] for k in ('status', 'game_version', 'call_sites', 'distinct_native_methods', 'failures', 'scope')},
        'offline': {k: checks['regression'][k] for k in ('python_tests', 'bridge_checks', 'task_count', 'positive_task_paths')},
        'interface': {k: checks['interface'][k] for k in ('status', 'evidence_kind', 'task_cards', 'layouts', 'page_errors', 'post_requests')},
        'project_interface': {k: checks['project'][k] for k in ('status', 'evidence_kind', 'actual_payment_image_configured', 'scope')},
        'standalone': {k: checks['standalone'][k] for k in ('status', 'runs', 'minimal_path_without_python', 'chinese_spaced_path',
            'python_and_tcl_tk_bundled', 'private_runtime_or_game_files', 'clean_vm_tested')},
        'confirmed_actions_during_monitoring': actions,
        'normal_failures_during_monitoring': last['stats'].get('failed', 0)-first['stats'].get('failed', 0),
        'growth_flow': {'refine_observed': bool(refine), 'downstream_actions': downstream, **flow},
        'coverage_limit': f'{len(TASK_ORDER)}项有隔离正向路径；实机只确认操作增量列出的玩法。{limit}'}
    if args.check_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    require(report['release_ready'], '完整成长实机条件未满足：需有原生奖励补足缺口、连续用料及实际强化/突破记录，暂不生成正式发布包')
    report_path = ROOT / 'dist' / f'{APP_TITLE}-验证报告.json'
    write(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    hk = timezone(timedelta(hours=8))
    start, finish = [datetime.fromisoformat(a[k]).astimezone(hk).strftime('%Y-%m-%d %H:%M:%S') for k in ('started', 'finished')]
    validation = f'''# {APP_TITLE} 验证记录

- 对照游戏{a['game_version']}核对{len(TASK_ORDER)}项任务，桥接修订{MIN_BRIDGE_REVISION}；正确规则见`FULL_LOGIC_AUDIT.md`。
- Python {checks['regression']['python_tests']}项、Godot桥接 {checks['regression']['bridge_checks']}项及{len(TASK_ORDER)}项正向路径通过；属于隔离验证。
- {start}至{finish}（香港时间）连续监控{a['elapsed_seconds']}秒、{a['samples']}次采样，验收失败0项，背包刷新{a['inventory_refreshes']}次。
- 新增服务器确认操作：{json.dumps(actions, ensure_ascii=False)}；正常失败/拒绝{report['normal_failures_during_monitoring']}批未计为成功。
- 核对{a['preserved_unbound_item_types_checked']}种受保护未绑定库存、{a['tradable_equipment_checked']}件保护范围装备、{a['protected_equipment_checked']}件固定/游戏锁装备、{a['fixed_item_types_checked']}种固定锁物品，未检测到减少。数量为0的类别只有隔离测试证据。
- 网页43张任务卡、成长需求与自动目标，1440/390像素、浅/深色检查通过，无页面错误和写入请求。
- 独立EXE在PATH无Python、清除Python/Tcl环境的中文空格路径自检2次；没有进行干净虚拟机测试。
- {limit}
- 多人秘境依当前原生开放时间、角色资格和场次状态执行；资源秘境需要真实入口，社交、抓捕、占领、解救与逃脱依赖角色和目标。未满足条件的玩法没有声称实机成功。
- 保留用户物品保护与保留量设置；不为演示耗掉混合受保护镜子。发布EXE与受验候选哈希一致，自动化保持运行。

源码指纹：`{source}`。

EXE SHA256：`{digest}`。
'''
    write(ROOT / 'VALIDATION.md', validation)
    old = (ROOT / 'README.md').read_text(encoding='utf-8')
    readme = f'''# {APP_TITLE} · Auto_fanxiu

连接本机凡修客户端的网页成长助手。{len(TASK_ORDER)}项可配置任务按实时等级、解锁、库存与保护规则调度；原生确认后才计为成功。只监听本机回环地址，不建立第二套游戏登录。

[项目 GitHub](https://github.com/weixiao030/Auto_fanxiu) · [版本发布](https://github.com/weixiao030/Auto_fanxiu/releases) · [全部参数](PARAMETERS.md) · [验证记录](VALIDATION.md)

本轮适配游戏{a['game_version']}、桥接{MIN_BRIDGE_REVISION}，修复化物批量限制、突破失败补偿、永久增益与多人秘境指令确认。新增原生自动服丹协调、时装加成和运行诊断，详见[适配说明](UPDATE_0.2.116.md)。

最终候选连续实机监控{a['elapsed_seconds']}秒通过，发布EXE与受验候选逐字节一致。{limit}未触发的多人秘境完整场次等分支单独记录覆盖边界。

右侧使用Auto_Dps作者赞赏码，可点击放大；窄屏移至内容下方。声明首次提醒、三秒后可记住已读，也可暂时关闭或重新查看。赞赏完全自愿，不影响功能。原创源码免费开源，使用[Apache-2.0](LICENSE)，第三方归属见[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

''' + old[old.index('## 双击使用'):]
    readme = readme.replace('## 双击使用', '![本机网页工作台](docs/images/workbench.png)\n\n## 双击使用', 1)
    readme = re.sub(r'猫头凡修助手0[.]\d+[.]exe', EXE_NAME, readme).replace('42项任务', f'{len(TASK_ORDER)}项任务')
    readme = readme.replace('择优迁居 |', '择优迁居、资源秘境补给 |')
    if '## 成长联动' not in readme:
        readme += '\n## 成长联动\n\n网页显示需求、可用库存、缺口和保护原因。成长用料与各任务自身保留量相加；资源不足时等待，不支出预计随机产出。炼化保留原生排除项、后续需求、固定锁及交易保护；没有盈余时继续领取、挂机和世界补给。\n\n窥真镜可选自动按成长缺口或固定目标，桥接执行前独立重算并服从最新手动目标。资源秘境有真实入口及对应缺口才入场，免费用尽默认不耗秘境令。\n'
    write(ROOT / 'README.md', readme)
    audit = (ROOT / 'FULL_LOGIC_AUDIT.md').read_text(encoding='utf-8')
    audit = audit.replace('最终连续实机监控正在进行；完成前不声明本候选稳定通过。最终结果及实际确认操作以`VALIDATION.md`和发布验证报告为准。',
        f'最终候选连续监控{a["elapsed_seconds"]}秒、{a["samples"]}次采样通过；真实确认范围见`VALIDATION.md`。{limit}')
    write(ROOT / 'FULL_LOGIC_AUDIT.md', audit)
    log = (ROOT / 'MODLOG.md').read_text(encoding='utf-8')
    if not log.startswith(f'# {VERSION} ·'):
        entry = f'''# {VERSION} · 全模块成长联动与执行复核（桥接{MIN_BRIDGE_REVISION}）

- {len(TASK_ORDER)}项任务迁入五个业务模块，统一注册、预算和有限优先调度。
- 突破、强化、普通炼丹、中间材料合成共享预算；普通炼丹只为一个可达配方备料，自身保留量与成长用料相加，旧计划重新核对。
- 定向炼化读取真实候选、排除项及未来需求，组合投入选择最小超额进度，不支出预计产出；原生配置证实过时的材料可回收。
- 探索跨日优先免费；自动镜子目标在执行前重算，旧准备参数不覆盖手动目标；修为满不重复灵泉，资源秘境待播战斗阻塞派发。
- Python {checks['regression']['python_tests']}项、桥接 {checks['regression']['bridge_checks']}项及{len(TASK_ORDER)}项正向路径通过；网页与独立EXE检查通过。
- 最终连续实机{a['elapsed_seconds']}秒，新增确认{sum(actions.values())}批。{limit}

'''
        write(ROOT / 'MODLOG.md', entry + log)
    files = [exe, ROOT/'README.md', ROOT/'VALIDATION.md', ROOT/'FULL_LOGIC_AUDIT.md',
             ROOT/'GROWTH_DESIGN.md', ROOT/'MODLOG.md', ROOT/'UPDATE_0.2.116.md',
             ROOT/'PARAMETERS.md', ROOT/'LICENSE', ROOT/'THIRD_PARTY_NOTICES.md', report_path, ROOT/'dist/build-info.json']
    files += sorted((ROOT/'licenses').glob('*'))
    files += sorted((ROOT/'docs/images').glob('*.png'))
    entries = [(path, path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT/'licenses') or path.is_relative_to(ROOT/'docs') else path.name) for path in files]
    require(all(path.is_file() for path, _ in entries), '发布说明或第三方许可缺失')
    require(len({name for _, name in entries}) == len(entries), '发布包存在重名文件')
    archive = ROOT/'dist'/f'{APP_TITLE}-Windows-x64.zip'
    temporary = archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path, name in entries:
            bundle.write(path, name)
    with zipfile.ZipFile(temporary) as bundle:
        require(set(bundle.namelist()) == {name for _, name in entries}, '发布包不符合白名单')
        require(hashlib.sha256(bundle.read(EXE_NAME)).hexdigest() == digest, '发布包EXE不同于受验文件')
    temporary.replace(archive)
    print(json.dumps({'exe': str(exe), 'zip': str(archive), 'report': str(report_path), 'sha256': digest,
                      'growth_flow': report['growth_flow']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
