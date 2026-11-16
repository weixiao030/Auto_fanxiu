"""Publish the exact tested executable with evidence and explicit coverage limits."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.version import EXE_NAME, APP_TITLE, VERSION


def write(path,text):
    if path.exists():
        backup=ROOT/'.private/backups/publication'/path.relative_to(ROOT)
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,backup)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(text,encoding='utf-8');temporary.replace(path)


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--acceptance',type=Path,required=True)
    args=parser.parse_args()
    acceptance_path=args.acceptance if args.acceptance.is_file() else args.acceptance/'result.json'
    acceptance=read(acceptance_path);dist=ROOT/'dist';info=read(dist/'build-info.json')
    source=source_fingerprint(ROOT);exe=dist/EXE_NAME
    paths={
        'standalone_exe':'runtime/exe-validation/summary.json',
        'regression':'runtime/exe-validation/quick-regression.json',
        'full_controls':'runtime/exe-validation/full-controls-audit.json',
        'fixed_lock_ui':'runtime/exe-validation/fixed-lock-ui.json',
        'steam_ui':'runtime/exe-validation/steam-ui.json',
        'stability_ui':'runtime/exe-validation/stability-ui.json',
        'all_features_ui':'runtime/exe-validation/all-features-ui.json',
        'update_notice_ui':'runtime/exe-validation/update-notice-ui.json',
        'theme_ui':'runtime/exe-validation/theme-ui.json',
        'configuration_ui':'runtime/ui-config-gacha-verification.json',
        'live_ui':'runtime/exe-validation/live-steam-ui.json',
        'real_task_controls':'.private/live-audit/full-live.json',
        'takeover':'.private/live-audit/takeover-final.json',
        'final_launch':'runtime/exe-validation/final-launch.json',
    }
    evidence={name:read(ROOT/path) for name,path in paths.items()}
    assert info['validation_status']=='PASS' and info['file']==EXE_NAME and info['app_version']==VERSION
    assert acceptance['status']=='PASS' and acceptance['elapsed_seconds']>=1800 and not acceptance['failures']
    assert source==info['source_fingerprint']==acceptance['source_fingerprint']
    assert digest(exe)==info['sha256']==acceptance['exe_sha256']==evidence['standalone_exe']['exe_sha256']==evidence['final_launch']['exe_sha256']
    for name,record in evidence.items():
        assert record.get('status')=='PASS',name
        assert record.get('source_fingerprint')==source,name
    assert evidence['real_task_controls']['attempted_controls']==42
    assert evidence['final_launch']['auto_enabled'] and evidence['final_launch']['connected']
    assert evidence['final_launch']['app_version']==VERSION
    initial,final=acceptance['initial'],acceptance['final']
    added={key:value-initial['stats'].get(key,0) for key,value in final['stats'].items()}
    confirmed={k:v for k,v in added.items() if k not in ('success','failed') and v>0}
    read_errors=sum('read_error' in json.loads(line) for line in (acceptance_path.parent/'samples.jsonl').read_text(encoding='utf-8').splitlines())
    hk=timezone(timedelta(hours=8))
    start=datetime.fromisoformat(acceptance['started']).astimezone(hk).strftime('%Y-%m-%d %H:%M:%S')
    end=datetime.fromisoformat(acceptance['finished']).astimezone(hk).strftime('%Y-%m-%d %H:%M:%S')
    limits=[
        '42项入口已逐项真实触发；条件不足、服务器拒绝及未开放模式不能计为玩法成功。',
        '多人秘境当前未开放；定向结缘、抓捕、占领、解救、被捕分支没有所有成功路径的实机证据。',
        '无需另装Python/Node；仍需Windows10/11 x64及Steam凡修。未在干净虚拟机或所有电脑逐一测试。',
        '未来游戏接口变化仍可能需要适配；服务器强制更新由Steam正常处理。',
    ]
    report={'status':'PASS','app_name':APP_TITLE,'exe_sha256':info['sha256'],'source_fingerprint':source,
        'bridge_revision':info['bridge_revision'],'live_monitoring':acceptance,'local_http_read_errors':read_errors,
        'confirmed_task_deltas':confirmed,'rejected_batch_delta':added.get('failed',0),'evidence':evidence,
        'network_changes':'No proxy, environment proxy, route or accelerator configuration changes; loopback direct, Steam uses existing settings.',
        'limits':limits}
    write(dist/'验证报告.json',json.dumps(report,ensure_ascii=False,indent=2))
    regression=evidence['regression'];live=evidence['live_ui'];real=evidence['real_task_controls']
    text=f'''# {APP_TITLE} 交付验证

本版包含两套独立物品保护、Steam真实库存标记、背包固定锁、九品质与五种排序、按钮下参数、连接自适应和新版助手自动接替。桥接修订{info['bridge_revision']}，本次游戏{acceptance['game_version']}。

## 最终候选三十分钟真实监控

香港时间 **{start} 至 {end}**，连续 **{acceptance['elapsed_seconds']}秒**，{acceptance['samples']}个样本；本机读取错误{read_errors}次，增加{added.get('success',0)}批游戏确认成功操作。验收失败条件列表为空。发布EXE是同一候选的逐字节复制，源码指纹、EXE哈希和验收一致。

- 游戏PID稳定，自动化始终开启；没有检测到脚本错误或操作长期未确认。
- 检查{acceptance['protected_equipment_checked']}件锁定/手动保护装备、{acceptance.get('fixed_item_types_checked',0)}种当前固定锁物品和{acceptance.get('preserved_unbound_item_types_checked',0)}种受保护未绑定库存，未发现减少。
- 背包产生{acceptance.get('inventory_refreshes',0)}个刷新快照。
- 实际确认任务增量：`{json.dumps(confirmed,ensure_ascii=False)}`。
- 服务器拒绝或正常战败批次增量{added.get('failed',0)}，均未计为成功；没有把正常拒绝包装成成功结果。
- 早期候选的中断或源码变化记录没有合并或折算到本轮1800秒。

## 功能与前端证据

- {regression['python_tests']}项Python回归、{regression['bridge_checks']}项桥接隔离检查及42项计划器正向条件路径通过；隔离测试不等于全游戏实机成功。
- 对本版42个入口逐项真实触发。确认成功：`{', '.join(real['confirmed_success']) or '无'}`；等待条件：{len(real['waiting_conditions'])}项；游戏拒绝：{len(real['game_rejected'])}项。完整逐项结果在验证报告中，缺条件没有绕过。
- 固定锁真实回调阻断测试通过，临时测试锁已解除，用户自己的固定锁保留。最终监控期间不手动派任务、不改变参数。
- 42张任务卡及排队/取消、6种工坊参数位置、九品质、两总开关并集、分类展开、五种排序/方向/记忆、三主题、390/1440px布局、跨页配置和编辑稳定性通过。
- 游戏更新提示约5秒自动关闭，也可手动或键盘关闭；只关闭提示，不关闭网页，不拦截未知版本按钮。
- 本版真实EXE网页读取{live['inventory_items']}种背包物品，检查{live['unique_pngs_checked']}张唯一PNG；Steam匹配{live['actual_steam_rows']}种。图片来自本机已安装游戏，不随包分发。
- 新版等待旧助手结算后安全接替，再按需只正常重开当前凡修加载桥接17；没有重启Steam、结束其他游戏或修改代理。
- 独立EXE在中文带空格路径自检两次，子进程最小Windows PATH找不到Python，清除Python/Tcl变量后仍通过。内置Python及Tcl/Tk，网页/桥接资源逐文件匹配，没有捆绑游戏文件、恢复源码、账户资料、配置或配对密钥。

## Steam与物品保护

默认 **只保护Steam可交易物品开启**、**按分类品质保留关闭**。分类模式预选消耗品、功法、时装的全部九品质；两模式都开启时取并集。固定锁和游戏锁始终优先。突破最低60%，悟性保留0，背包默认60秒刷新，固定属性换装默认开启，权重评分默认关闭。

只读使用游戏已初始化的GodotSteam库存与定义目录；没有二次登录，也不调用Steam消费、转移、交易或生成接口。本次目录947定义：消耗品557、功法338、时装34、突破稀有材料6、丹药12，没有装备类。服务器装备实例不冒充Steam定义。功法按编号/层数映射，时装按实例对应的配置编号映射；已验证时装实例2对应Steam定义6“阵法传人”。未知映射保守保留。Steam总量与背包匹配种数分别显示，新增掉落根据定义目录立即保护。

## 运行与覆盖边界

本机通信直连回环，恢复监听时保留控制器及已提交任务；不改系统代理、代理环境变量、路由或加速器。Steam沿用现有网络设置。连接恢复等待原会话，必要时只正常重开当前凡修，不退出Steam。

'''+'\n'.join('- '+line for line in limits)+f'''

自动化在交付时保持开启，运行版本{VERSION}与分发包哈希一致。

EXE SHA256：`{info['sha256']}`。
'''
    write(ROOT/'VALIDATION.md',text);write(dist/'验证说明.md',text)
    write(dist/'使用说明.txt',(ROOT/'README.md').read_text(encoding='utf-8'))
    log=ROOT/'MODLOG.md';marker=f'## {APP_TITLE} · Steam保护与三十分钟验收';old=log.read_text(encoding='utf-8')
    if marker not in old:
        write(log,old+f'\n\n{marker}\n\nSteam SDK只读目录/库存、功法及时装映射，两保护总开关并集，固定锁、九品质和五种排序，旧助手安全接替、就绪自动运行。{regression["python_tests"]}项Python及{regression["bridge_checks"]}项桥接检查通过，最终同一候选连续{acceptance["elapsed_seconds"]}秒监控。SHA256：`{info["sha256"]}`。未开放或缺条件分支不计实机成功。\n')
    names=[EXE_NAME,'使用说明.txt','验证说明.md','验证报告.json','build-info.json']
    write(dist/'SHA256SUMS.txt','\n'.join(digest(dist/name)+'  '+name for name in names)+'\n')
    archive=dist/f'{APP_TITLE}-Windows-x64.zip';temporary=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as zipped:
        for name in [*names,'SHA256SUMS.txt']:zipped.write(dist/name,name)
    with zipfile.ZipFile(temporary) as zipped:
        assert zipped.testzip() is None and set(zipped.namelist())==set([*names,'SHA256SUMS.txt'])
    temporary.replace(archive)
    print(json.dumps({'status':'PASS','exe':str(exe),'zip':str(archive),'zip_sha256':digest(archive),'monitoring_seconds':acceptance['elapsed_seconds']},ensure_ascii=False))

if __name__=='__main__':main()
