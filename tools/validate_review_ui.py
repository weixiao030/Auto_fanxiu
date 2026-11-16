"""Browser regression against an isolated local service; no game connection or login."""
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
from unittest.mock import patch

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from fanxiu_assistant import server
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.version import VERSION


class SlowConfigHandler(server.Handler):
    def do_POST(self):
        if self.path=='/api/config':time.sleep(.12)
        super().do_POST()


def main():
    errors,checks,requests=[],[],[]
    output=ROOT/'runtime/exe-validation';output.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory() as temp,ExitStack() as stack:
        runtime=Path(temp)/'runtime';icons=Path(temp)/'.private/inventory-icons'
        stack.enter_context(patch.object(server,'RUNTIME',runtime))
        stack.enter_context(patch.object(server,'INVENTORY_ICONS',icons))
        c=server.Controller()
        c.state={'ready':False,'online':False,'bridge_revision':server.MIN_BRIDGE_REVISION,
                 'login_queue':{'active':True,'ahead_count':214,'next_poll_seconds':23}}
        c.pid=42;c.last_seen=time.monotonic()
        c.planner.config['manual_locks']=['material:7']
        http=ThreadingHTTPServer(('127.0.0.1',0),SlowConfigHandler);http.controller=c;http.daemon_threads=True
        thread=Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1100})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda req:requests.append(req.post_data_json) if req.method=='POST' and req.url.endswith('/api/config') else None)
                page.goto(f'http://127.0.0.1:{http.server_port}',wait_until='networkidle')
                page.wait_for_function('() => config!==null && confirmedConfig!==null')
                assert page.locator('.function-card').count()==43
                assert '214' in page.locator('#growth-message').inner_text()
                assert '不是入场预计' in page.locator('#growth-message').inner_text()
                assert page.locator('#run-state').inner_text()=='原生排队'
                checks.append('43项任务与真实等待文案的隔离页面')
                def settled():
                    page.wait_for_function('() => saving===0 && pendingConfigEdits.length===0')
                    page.evaluate('refresh()')
                # One invalid field must not poison a later edit to another field.
                page.evaluate("""() => {
                  const a=document.querySelector('[data-param="interval"]');a.value='0';a.dispatchEvent(new Event('change'));
                  const b=document.querySelector('[data-param="reserve_wuxing"]');b.value='123';b.dispatchEvent(new Event('change'));
                }""")
                settled()
                assert c.planner.config['interval']==3 and c.planner.config['reserve_wuxing']==123
                assert requests[-1]['edit']=={'path':['reserve_wuxing'],'value':123}
                checks.append('无效参数后不同字段仍保存且不夹带失败值')
                page.evaluate("""() => {const a=document.querySelector('[data-param="interval"]');for(const value of ['0','2.5']){a.value=value;a.dispatchEvent(new Event('change'));}}""")
                settled()
                assert c.planner.config['interval']==2.5
                assert page.locator('[data-param="interval"]').input_value()=='2.5'
                checks.append('同字段连续修改后旧失败不回滚新值')
                page.evaluate("""() => {
                  for(const [id,value] of [['preserve-steam',false],['preserve-tradable',true]]){const e=document.getElementById(id);e.checked=value;e.dispatchEvent(new Event('change'));}
                  const e=document.querySelector('[data-trade-category="equipment"]');e.checked=true;e.dispatchEvent(new Event('change',{bubbles:true}));
                }""")
                settled()
                assert not c.planner.config['preserve_steam_tradable'] and c.planner.config['preserve_tradable']
                assert c.planner.config['trade_rules']['equipment']['enabled']
                checks.append('两个总开关与分类编辑串行保存且互不覆盖')
                page.evaluate("""() => {document.getElementById('reset').click();const a=document.querySelector('[data-param="interval"]');a.value='7';a.dispatchEvent(new Event('change'));}""")
                settled()
                assert c.planner.config['interval']==7 and c.planner.config['preserve_steam_tradable']
                assert not c.planner.config['preserve_tradable']
                assert c.planner.config['manual_locks']==['material:7']
                checks.append('重置与后续编辑排序，固定锁继续保留')
                # A suspended tab retains an old local base while a second tab changes protection.
                other=browser.new_page()
                other.goto(f'http://127.0.0.1:{http.server_port}',wait_until='networkidle')
                other.wait_for_function('() => config!==null')
                stale=page.evaluate('() => structuredClone(confirmedConfig)')
                other.evaluate("saveConfigEdit(['preserve_steam_tradable'],false)")
                page.evaluate("old => {confirmedConfig=old; return saveConfigEdit(['interval'],8);}",stale)
                assert not c.planner.config['preserve_steam_tradable']
                assert c.planner.config['interval']==8
                other.evaluate("saveConfigEdit(['preserve_steam_tradable'],true)")
                page.evaluate("old => {confirmedConfig=old; return saveConfigEdit(['reserve_wuxing'],456);}",dict(stale,preserve_steam_tradable=False))
                assert c.planner.config['preserve_steam_tradable']
                assert c.planner.config['reserve_wuxing']==456
                other.close()
                checks.append('两个网页持有旧配置时，各自字段修改不会覆盖另一页的Steam保护')

                # Saving an old weight must not clear a newer unsaved input.
                page.evaluate("""() => {
                  const a=document.querySelector('[data-weight="atk"]');a.value='2';a.dispatchEvent(new Event('input',{bubbles:true}));
                  document.getElementById('save').click();a.value='3';a.dispatchEvent(new Event('input',{bubbles:true}));
                }""")
                settled()
                assert c.planner.config['weights']['atk']==2
                assert page.locator('[data-weight="atk"]').input_value()=='3'
                assert page.locator('[data-weight="atk"]').get_attribute('data-dirty')=='true'
                checks.append('保存权重期间继续输入，不丢弃更新的未提交值')
                # Simulate a lost response after the server has actually saved.
                lost=[False]
                def lose_once(route):
                    if not lost[0]:
                        lost[0]=True;route.fetch();route.abort('failed')
                    else:route.continue_()
                page.route('**/api/config',lose_once)
                page.evaluate("""() => {
                  const a=document.querySelector('[data-param="interval"]');a.value='9';a.dispatchEvent(new Event('change'));
                  const b=document.querySelector('[data-param="reserve_wuxing"]');b.value='789';b.dispatchEvent(new Event('change'));
                }""")
                settled()
                assert c.planner.config['interval']==9 and c.planner.config['reserve_wuxing']==789
                assert page.locator('[data-param="interval"]').input_value()=='9'
                checks.append('服务端已保存但响应丢失时先对账，再提交后续编辑')
                # The first reconciliation can fail too; no later full write may use a stale base.
                lost[0]=False
                failed_read=[False]
                def fail_first_reconciliation(route):
                    if lost[0] and not failed_read[0]:failed_read[0]=True;route.abort('failed')
                    else:route.continue_()
                page.route('**/api/status',fail_first_reconciliation)
                page.evaluate("""() => {
                  const a=document.querySelector('[data-param="interval"]');a.value='13';a.dispatchEvent(new Event('change'));
                  const b=document.querySelector('[data-param="reserve_wuxing"]');b.value='999';b.dispatchEvent(new Event('change'));
                }""")
                settled()
                assert failed_read[0] and c.planner.config['interval']==13 and c.planner.config['reserve_wuxing']==999
                checks.append('响应与首次对账均失败时，后续写入先重新读取配置')
                page.locator('#growth-panel').screenshot(path=str(output/'review-ui-waiting.png'))
                with c.lock:
                    c.last_seen=time.monotonic()
                    c.planner.config.update(refine_preferred_id=1008,refine_obsolete_reserve=2)
                    c.planner.config['tasks']={k:k in ('refine','world_forge') for k in c.planner.config['tasks']}
                    c.state={'ready':True,'online':True,'tutorial_finished':True,'bridge_revision':server.MIN_BRIDGE_REVISION,
                        'character':{'level':25,'equip_slots':[],'exp':0,'exp_needed':100},'features':{'refine':True},
                        'idle':{'selected':{'difficulty':0,'tier':0,'stage':0}},'world':{'points':[{'marker_id':14,'type':'forge'}]},
                        'owned_items':{'material:1001':25},'bound_items':{'material:1001':25},
                        'refine_candidates':[{'kind':'material','id':1008,'name':'目标材料'}],
                        'refine_forge_multiplier':3,'refine_inputs':[{'id':1001,'kind':'material','category':'breakthrough_main',
                            'value':6,'count':25,'obsolete':True,'bound_only_safe':True}],
                        'protection_policy':c.planner.protection_policy()}
                page.evaluate('refresh()')
                assert '3倍进度' in page.locator('#growth-supply').inner_text()
                assert '投入6件' in page.locator('[data-card="world_forge"] [data-feedback]').inner_text()
                assert '投入17件' in page.locator('[data-card="refine"] [data-feedback]').inner_text()
                checks.append('世界熔炉3倍进度与普通炼化分别显示真实投入，成长面板优先熔炉')
                with c.lock:
                    c.planner.config['world_point_limit']=3
                    c.state['features']['explore']=True
                    c.state['world'].update(point_count=2,max_points=20,expired_point_count=1,free_remaining=1,
                        points=[{'marker_id':14,'type':'forge'}, {'marker_id':15,'type':'empty'},
                                {'marker_id':16,'type':'player','expired':True}])
                page.evaluate('refresh()')
                assert page.locator('#world-count').inner_text()=='2 / 3 个有效坐标 · 另有 1 个过期坐标'
                assert '已过期（不占探索上限）' in page.locator('#world-body').inner_text()
                checks.append('世界地图按有效坐标和用户上限显示，过期玩家单独标注')
                layouts=[]
                for width in (1440,390):
                    page.set_viewport_size({'width':width,'height':1100})
                    for theme in ('light','dark'):
                        page.locator('#theme').select_option(theme)
                        for tab in ('overview','world'):
                            page.locator('[data-tab="'+tab+'"]').click()
                            dimensions=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
                            assert dimensions['scroll']<=width+1,dimensions
                            layouts.append(dict(theme=theme,tab=tab,**dimensions))
                page.locator('#world').screenshot(path=str(output/'review-ui-world.png'))
                page.locator('[data-tab="overview"]').click()
                page.locator('#growth-panel').screenshot(path=str(output/'review-ui-forge.png'))
                assert not errors,errors
                browser.close()
        finally:
            http.shutdown();http.server_close();thread.join(3)
    report={'status':'PASS','app_version':VERSION,'source_fingerprint':source_fingerprint(ROOT),
            'scope':'isolated real HTTP service and headless browser; synthetic queue, forge and map states; no game attached',
            'checks':checks,'config_posts':len(requests),'layouts':layouts,'page_errors':errors,'real_game_mutations':0}
    (output/'review-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
