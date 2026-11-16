'use strict';
let status=null,config=null,lastConnection=null,saving=0,configRevision=0;
let refreshPromise=null,lastStatusAt=0,serviceFailures=0;
let configWriteChain=Promise.resolve(),confirmedConfig=null;
const pendingConfigEdits=[];
let configReconcileRequired=false;
const submittingTasks=new Set();
const $=id=>document.getElementById(id);

// This timer only dismisses the notice. It never closes or navigates the page.
let updateNoticeTimer, observedGameVersion = '', shownUpdateNotices = new Set();
try { observedGameVersion = localStorage.getItem('fanxiu.lastGameVersion') || ''; } catch (_) {}
try { shownUpdateNotices = new Set(JSON.parse(sessionStorage.getItem('fanxiu.updateNotices') || '[]')); } catch (_) {}
function dismissUpdateNotice() {
  clearTimeout(updateNoticeTimer);
  $('update-notice').hidden = true;
}
$('dismiss-update').addEventListener('click', dismissUpdateNotice);
function renderUpdateNotice() {
  if (!status.connected) return;
  const version = String(status.state.version || '').trim();
  if (!version) return;
  const updateState = status.state.client_update?.state;
  const hasUpdate = ['required', 'available'].includes(updateState);
  const changed = observedGameVersion && observedGameVersion !== version;
  const firstUnverified = !observedGameVersion && version !== '0.2.20';
  const key = `${version}:${hasUpdate ? updateState : 'connected'}`;
  if ((hasUpdate || changed || firstUnverified) && !shownUpdateNotices.has(key)) {
    $('update-notice-text').textContent = hasUpdate
      ? (status.config.allow_game_restart ? `游戏 ${version} 有更新，助手会按设置通过Steam更新并恢复连接。` : `游戏 ${version} 有更新，当前禁止重开，保留游戏会话并等待。`)
      : `当前游戏版本 ${version}。助手已取消版本限制，继续连接和运行。`;
    clearTimeout(updateNoticeTimer);
    $('update-notice').hidden = false;
    updateNoticeTimer = setTimeout(dismissUpdateNotice, 5000);
    shownUpdateNotices.add(key);
    try { sessionStorage.setItem('fanxiu.updateNotices', JSON.stringify([...shownUpdateNotices])); } catch (_) {}
  }
  observedGameVersion = version;
  try { localStorage.setItem('fanxiu.lastGameVersion', version); } catch (_) {}
}
// The appearance preference is local to the browser, separate from game policy.
const themeModes = ['system', 'light', 'dark'];
let preferredTheme = 'system';
try { preferredTheme = localStorage.getItem('fanxiu-theme') || 'system'; } catch (_) {}
if (!themeModes.includes(preferredTheme)) preferredTheme = 'system';
function applyTheme(value) {
  if (value === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = value;
  $('theme').value = value;
}
applyTheme(preferredTheme);
$('theme').addEventListener('change', event => {
  applyTheme(event.target.value);
  try { localStorage.setItem('fanxiu-theme', event.target.value); } catch (_) {}
});
const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=v=>v==null?'待同步':Number(v).toLocaleString('zh-CN',{maximumFractionDigits:1});
const qualityNames={common:'凡品',fine:'下品',rare:'中品',epic:'上品',legend:'极品',myth:'仙品',perfect:'完美',innate:'先天',treasure:'至宝'};
const statNames={atk:'攻击',hp:'生命',def:'防御',shield:'护盾',mp:'法力',mp_regen_per_sec:'回蓝',crit_chance:'暴击率',crit_damage:'暴伤',attack_speed:'攻速',cdr:'冷却缩减',lifesteal:'吸血',dodge_chance:'闪避',combo_chance:'连击',stun_chance:'眩晕',counter_chance:'反击',resist_stun:'抗晕'};
const groups=[['领取与补给',['collect','harvest','mail','open_pack','furnace_absorb']],['装备与炼器',['equip','upgrade','synth','refine','world_forge','material_synth','resource_pack']],['修炼与成长',['levelup','breakthrough','gongfa_activate','gongfa_slots','gongfa','gongfa_accelerate','pill','alchemy']],['世界探索',['world_sync','world_explore','world_harvest','world_points','world_events','world_prune','home_relocate']],['挑战与挂机',['challenge','realm_challenge','resource_realm','idle_select','gacha']]];
const descriptions={resource_pack:'将盈余可交易原料打成资源包，存在原料损耗。默认关闭，保留可交易物品开启时暂停；开启后不自动拆资源包。',material_synth:'沿强化材料链补齐穿戴装备的用料，保留原料库存。',furnace_absorb:'领取现有炉鼎经验池，修为已满时等待升级。',home_relocate:'按增益评分迁往更好的洞府，保留迁居令；跳过负面与未知特性，占用冲突停止该次迁居。',collect:'定期领取已结算的修为与悟性。',harvest:'领取已到时间的副本挂机掉落。',mail:'领取邮件附件，不删除或发送邮件。',open_pack:'开启装备箱和资源包，遵循交易保护设置。',equip:'按真实属性评分择优换装，保留锁定和保护装备。',upgrade:'强化已穿戴装备，逐种保留所需材料。',synth:'同品质闲置装备合成，支持全部九品质。保留穿戴、锁定、手动保护及各类最佳。',refine:'按成长缺口设置产出偏好，回收过时材料，保留突破、强化与炼丹用料；每次结算后重算。',world_forge:'世界熔炉按原生3倍进度计算，用更少盈余补料；可用时优先使用，结算后重算。',levelup:'修为足够时升级，突破节点转入突破流程。',breakthrough:'修为、材料和成功率全部达标后自动突破。缺料可自动补给，丹药提概率单独设置。',gongfa_activate:'有入门页且五行适配时自动激活功法。',gongfa_slots:'优先指定功法，其余按效果与层数选择主动功法。',gongfa:'按境界层数上限持续修炼，暂停任务可恢复。',gongfa_accelerate:'使用同目标层的多余功法页加速，保留指定页数。',pill:'需要时用突破丹、疗伤丹和增益丹；不自动改变五行。',alchemy:'按已解锁配方炼制当前需要的丹药，避免重复囤积。',world_sync:'同步地图、免费探索次数与待处理事件。',world_explore:'优先免费探索，之后按设置使用流言或窥真镜；游戏优先扣绑定，保护份与保留数量不消耗。',world_harvest:'采集普通洞府、灵草和材料点，失效目标自动退避。',world_points:'灵泉、遗迹、据点奖励自动处理，据点优先高品质。',world_events:'关闭需要赠送资源或社交决策的奇遇，继续探索。',world_prune:'地图满时清理空坐标与过期的玩家标记。',challenge:'挑战下一已解锁关卡，失败后回到成长循环。',realm_challenge:'挑战世界中的突破秘境，沿用原客户端战斗与结算。',idle_select:'跟随最高通关进度，或使用指定已通关地点。',gacha:'使用多余悟性化物获取资源，与世界地图探索分别控制。'};
descriptions.resource_realm='发现资源秘境后按缺口免费入场，由原客户端完成探索、战斗和结算。免费用尽后默认不使用秘境令。';
const basicFields={interval:['操作最小间隔（秒）',2,60],reserve_wuxing:['保留悟性',0,10000000],min_breakthrough_rate:['达到此成功率后突破（%）',0,100],challenge_retry_seconds:['失败后等待（秒）',30,86400],upgrade_level_gap:['落后角色多少级再强化',0,90],upgrade_reserve:['每种强化材料保留数量',0,10000000],equip_min_gain:['换装最低收益（%）',0,100],stop_at_level:['目标等级（0持续运行）',0,1000],idle_stage:['挂机目标（auto或0_2_4）','text'],protected_equipment:['保护装备编号（逗号分隔）','ids'],synth_max_quality:['合成品质上限',qualityNames]};
const taskFields={resource_pack:['resource_pack_size','resource_pack_reserve','resource_pack_batch','resource_pack_materials'],material_synth:['material_synth_reserve','material_synth_batch','material_synth_demand_only'],furnace_absorb:['furnace_min_exp'],home_relocate:['home_priority','home_min_gain','home_reserve'],gacha:['reserve_wuxing'],breakthrough:['min_breakthrough_rate','breakthrough_auto_find','breakthrough_auto_raise','breakthrough_auto_craft','breakthrough_auto_use','breakthrough_material_reserve'],challenge:['challenge_retry_seconds'],upgrade:['upgrade_reserve','upgrade_level_gap'],equip:['equip_use_weights','equip_keep_weapon_type','equip_min_gain','protected_equipment'],synth:['synth_max_quality'],idle_select:['idle_stage'],world_explore:['world_interval','world_daily_limit','world_point_limit','world_use_rumor','world_use_mirror','world_prop_reserve','world_mirror_target'],world_points:['world_relics'],world_prune:['world_prune'],gongfa_slots:['gongfa_preferred'],gongfa_accelerate:['gongfa_accelerate_reserve'],pill:['pill_reserve','pill_timed_buffs'],alchemy:['alchemy_reserve','alchemy_batch'],refine:['refine_reserve','refine_max_items','refine_target_level','refine_preferred_id','refine_recycle_obsolete','refine_obsolete_reserve','refine_surplus_without_demand'],world_forge:['refine_reserve','refine_max_items','refine_target_level','refine_preferred_id','refine_recycle_obsolete','refine_obsolete_reserve','refine_surplus_without_demand'],resource_realm:['resource_realm_use_token','resource_realm_token_reserve'],realm_challenge:['realm_allow_danger','realm_retry_seconds']};
descriptions.equip='默认仅比较固定属性，不看随机词条；任一固定属性下降就保留原装备，保持武器类型，空槽自动补齐。可选启用自定义评分权重。';
descriptions.resource_pack='将盈余可交易原料打成资源包，存在原料损耗，默认关闭。输入被分类品质保留或固定锁定时跳过；开启后不自动拆资源包。';
groups.push(['道侣与社交',['social_sync','partner_practice','partner_social','partner_rescue']],['抓捕与悬赏',['player_capture','player_occupy','bounty_sync','bounty_claim','bounty_publish','slave_escape']],['多人秘境',['multiplayer_realm']]);
Object.assign(descriptions,{
 social_sync:'同步道侣、双修次数和定向邀请状态。',partner_practice:'有道侣且未被捕时完成每日双修。',
 partner_social:'仅邀请或接受指定好友编号，不随机结缘，不发送聊天，不自动解除关系。',
 partner_rescue:'道侣被捕时按配置使用脱身符或战斗解救；消耗仍遵循交易保护。',
 player_capture:'只从地图中的修士目标选择，核对战力、保护期和炉鼎空位；次数按尝试计。',
 player_occupy:'战力达标且洞府评分更高时挑战占领；失败可能被捕，受伤后等待恢复。',
 bounty_sync:'同步原游戏悬赏列表和服务器每日次数。',bounty_claim:'优先按战力门槛挑战怪物清剿，可单独允许玩家悬赏。',
 bounty_publish:'被捕后对当前主人发布一次悬赏，消耗悬赏令；此额外选项默认关闭。',
 slave_escape:'优先使用保护规则允许的脱身符；普通逃脱每次囚禁最多一次，失败可能延长囚禁。',
 multiplayer_realm:'按原游戏开放状态运行。开放后可空载入场、原生探索战斗、指定事件选项、低生命撤离；战斗逃脱仅在原生支持时提供。免费次数优先；钥匙遵守保护；操作由原生票据与结算确认，按角色资格和开放时间执行。'
});
Object.assign(taskFields,{
 social_sync:['social_interval'],partner_practice:['partner_practice_limit'],partner_social:['partner_target','partner_auto_invite','partner_auto_accept'],
 partner_rescue:['partner_rescue_mode','rescue_prop_reserve','pvp_max_injury','pvp_retry_seconds'],
 player_capture:['pvp_assessment','capture_daily_limit','pvp_max_injury','pvp_retry_seconds'],
 player_occupy:['pvp_assessment','occupy_daily_limit','occupy_min_gain','home_priority','pvp_max_injury','pvp_retry_seconds'],
 bounty_sync:['bounty_interval'],bounty_claim:['bounty_allow_players','bounty_assessment','bounty_daily_limit','pvp_max_injury','pvp_retry_seconds'],
 bounty_publish:['bounty_publish_captured','bounty_prop_reserve'],slave_escape:['escape_mode','escape_prop_reserve'],
 multiplayer_realm:['mp_auto_enter','mp_interval','mp_extract_hp','mp_escape_hp','mp_event_option','mp_max_seconds']
});
function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
async function fetchTimed(url,options={},timeout=6000){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
 try{const response=await fetch(url,{...options,signal:controller.signal,cache:'no-store'});const data=await response.json();return {ok:response.ok,status:response.status,json:async()=>data};}
 catch(error){if(error.name==='AbortError')throw Error('本机服务响应超时，正在重新连接。');throw error;}
 finally{clearTimeout(timer);}
}
async function post(path,body={},settle=null){
 const isConfig=['/api/config','/api/lock'].includes(path),payload=typeof body==='function'?body:JSON.stringify(body);
 if(isConfig){saving++;configRevision++;}
 const send=async()=>{
  try{
   if(path==='/api/config'&&configReconcileRequired){const r=await fetchTimed('/api/status');if(!r.ok)throw Error('配置状态尚未恢复，请稍后重试。');confirmedConfig=structuredClone((await r.json()).config);configReconcileRequired=false;}
   const r=await fetchTimed(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':status?.csrf||''},body:typeof payload==='function'?JSON.stringify(payload()):payload},10000);const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');settle?.(d,null);return d;}
  catch(error){
   let actual=null;
   if(path==='/api/config'&&settle){configReconcileRequired=true;try{const r=await fetchTimed('/api/status');if(r.ok){actual={config:(await r.json()).config};configReconcileRequired=false;}}catch(_) {}}
   settle?.(actual,error);throw error;
  }
 };
 try{if(!isConfig)return await send();const queued=configWriteChain.then(send);configWriteChain=queued.catch(()=>{});return await queued;}
 finally{if(isConfig)saving--;}
}
function applyConfigEdit(base,edit){
 if(!edit.path)return structuredClone(edit.value);
 let target=base;for(const part of edit.path.slice(0,-1))target=target[part];
 target[edit.path.at(-1)]=structuredClone(edit.value);return base;
}
function rebuildConfig(){
 config=structuredClone(confirmedConfig);
 for(const edit of pendingConfigEdits)if(edit.path)config=applyConfigEdit(config,edit);
 syncConfigControls();
}
function saveConfigEdit(path,value){
 if(!confirmedConfig)confirmedConfig=structuredClone(config);
 const edit={path,value:structuredClone(value)};pendingConfigEdits.push(edit);
 if(path)config=applyConfigEdit(config,edit);
 return post('/api/config',()=>path?{edit:{path:edit.path,value:edit.value}}:{replace:edit.value},(result,error)=>{
  if(result?.config)confirmedConfig=structuredClone(result.config);
  pendingConfigEdits.splice(pendingConfigEdits.indexOf(edit),1);
  rebuildConfig();
 });
}
function specFor(key){return basicFields[key]||status.fields[key];}
function fieldHTML(key){const s=specFor(key),v=config[key],title=safe(s[0]);let control;
if(s.length===1)control=`<input type="checkbox" data-param="${key}" ${v?'checked':''}>`;
else if(typeof s[1]==='object')control=`<select data-param="${key}">${Object.entries(s[1]).map(([k,n])=>`<option value="${k}" ${v===k?'selected':''}>${safe(n)}</option>`).join('')}</select>`;
else{const numeric=s.length===3,value=Array.isArray(v)?v.join(', '):['equip_min_gain','min_breakthrough_rate','breakthrough_target_rate'].includes(key)?v*100:v;control=`<input data-param="${key}" type="${numeric?'number':'text'}" ${numeric?`min="${s[1]}" max="${key==='breakthrough_target_rate'?100:s[2]}" step="${['interval','equip_min_gain','min_breakthrough_rate','breakthrough_target_rate'].includes(key)?'0.5':'1'}"`:''} value="${safe(value)}">`;}
return `<label class="parameter ${s.length===1?'check-param':''}">${s.length===1?control+title:title+control}</label>`;}
function breakthroughParameters(){
 return `<div class="task-params breakthrough-primary">${['min_breakthrough_rate','breakthrough_auto_find'].map(fieldHTML).join('')}</div><p class="parameter-help">自动找料优先刷有对应掉落的已通关关卡；补齐后恢复原挂机策略。指定关卡时不自动换图。</p><details class="breakthrough-options"><summary>丹药提概率设置</summary><div class="task-params">${['breakthrough_auto_raise','breakthrough_auto_craft','breakthrough_auto_use','breakthrough_material_reserve'].map(fieldHTML).join('')}</div><p class="parameter-help">只在成功率不足时准备同境界突破丹，每次炼制或服用一颗后重新检查。关闭自动提概率，仍保留突破材料并等待目标达标。</p></details>`;
}
function renderTasks(){ $('task-grid').innerHTML=groups.map(([title,keys])=>{const tasks=keys.filter(key=>Object.hasOwn(status.labels,key));return `<section class="function-group" data-group-name="${safe(title)}"><div class="group-title"><div><h3>${title}</h3><small>${tasks.length} 项功能</small></div><button class="collapse secondary" aria-expanded="true">收合</button></div><div class="group-body">${tasks.map(key=>`<article class="function-card ${config.tasks[key]?'on':''}" data-card="${key}"><div class="function-head"><label class="switch"><input type="checkbox" data-task="${key}" aria-label="${safe(status.labels[key])}" ${config.tasks[key]?'checked':''}><span></span></label><strong>${safe(status.labels[key])}</strong><small data-count="${key}" title="本次本机服务启动以来确认的次数">0 次</small><button class="run-now secondary" data-run="${key}">立即执行</button></div><p>${descriptions[key]||''}</p>${key==='breakthrough'?breakthroughParameters():taskFields[key]?.length?`<div class="task-params">${taskFields[key].map(fieldHTML).join('')}</div>`:''}${key==='gacha'?'<p data-gacha-balance></p>':''}${key==='world_explore'?'<p class="task-summary" data-world-explore-status aria-live="polite"></p>':''}${key==='breakthrough'?'<div class="breakthrough-status" data-breakthrough-status aria-live="polite"></div>':''}<div class="task-feedback" data-feedback="${key}"></div></article>`).join('')}</div></section>`;}).join('');
document.querySelectorAll('[data-task]').forEach(el=>el.addEventListener('change',async()=>{const key=el.dataset.task;try{await saveConfigEdit(['tasks',key],el.checked);notice('任务开关已保存。');}catch(e){notice(e.message,true);}}));
document.querySelectorAll('[data-run]').forEach(el=>el.addEventListener('click',async()=>{
 const kind=el.dataset.run,out=document.querySelector(`[data-feedback="${kind}"]`);
 if(submittingTasks.has(kind))return;
 submittingTasks.add(kind);renderTaskControls();
 try{const queued=(status.manual_queue||[]).some(row=>row.kind===kind);const result=await post(queued?'/api/cancel-run':'/api/run',{kind});out.textContent=result.message||'已安排，等待游戏确认。';await refresh();}
 catch(e){out.textContent=e.message;notice(e.message,true);}
 finally{submittingTasks.delete(kind);renderTaskControls();}
}));
document.querySelectorAll('.collapse').forEach(el=>el.addEventListener('click',()=>{const body=el.closest('.function-group').querySelector('.group-body');body.hidden=!body.hidden;el.textContent=body.hidden?'展开':'收合';el.setAttribute('aria-expanded',String(!body.hidden));}));
bindParameters($('task-grid'));applyFilter();}
function readField(el){const key=el.dataset.param,s=specFor(key);if(s.length===1)return el.checked;if(s[1]==='ids'){const values=el.value.split(/[,，\s]+/).filter(Boolean);if(values.some(v=>!/^\d+$/.test(v)))throw Error('编号需为整数，使用逗号分隔');return values.map(Number);}if(s.length===3)return Number(el.value)/(['min_breakthrough_rate','equip_min_gain','breakthrough_target_rate'].includes(key)?100:1);return el.value.trim();}
function syncField(key,keepEditing=false){document.querySelectorAll(`[data-param="${key}"]`).forEach(el=>{if(keepEditing&&el===document.activeElement)return;if(el.type==='checkbox')el.checked=config[key];else el.value=Array.isArray(config[key])?config[key].join(', '):['min_breakthrough_rate','equip_min_gain','breakthrough_target_rate'].includes(key)?config[key]*100:config[key];});}
function bindParameters(root){root.querySelectorAll('[data-param]').forEach(el=>el.addEventListener('change',async()=>{const key=el.dataset.param;try{await saveConfigEdit([key],readField(el));syncField(key);notice('参数已保存，下次执行按新参数复核。');}catch(e){syncField(key);notice(e.message,true);}}));}
function fillSettings(){ $('global-fields').innerHTML=['growth_linked','interval','stop_at_level','allow_game_restart','auto_reconnect','reconnect_delay_seconds','reconnect_max_attempts','auto_steam_update','steam_update_interval'].filter(key=>specFor(key)).map(fieldHTML).join('');bindParameters($('global-fields'));$('weights').innerHTML=Object.entries(config.weights).map(([k,v])=>`<label>${safe(statNames[k]||k)}<input type="number" data-weight="${k}" min="0" max="1000" step="0.05" value="${v}"></label>`).join('');}
function render(){renderUpdateNotice();const s=status.state,c=s.character||{};$('preserve-tradable').checked=config.preserve_tradable;$('protection-state').textContent=config.preserve_tradable?'已开启':'已关闭';
const multiplayerFeedback=document.querySelector('[data-feedback="multiplayer_realm"]');
if(multiplayerFeedback&&(!s.multiplayer?.enabled||s.multiplayer?.suspended))multiplayerFeedback.textContent='原游戏当前暂停或未开放，托管等待开放；没有发送入场请求。';
const socialFeedback=document.querySelector('[data-feedback="partner_social"]');
if(socialFeedback&&!config.partner_target)socialFeedback.textContent='未填写指定好友编号，定向结缘保持等待。';
$('connection').textContent=status.connection?.state==='recovering'?`心跳延迟 · ${status.connection.heartbeat_age_seconds}秒`:status.connected?`已连接 · PID ${status.pid}`:'等待游戏连接';$('connection').classList.toggle('connected',status.connected);$('toggle').disabled=!status.enabled&&(!status.connected||!s.ready||(s.bridge_revision||0)<(status.minimum_bridge_revision||16));$('toggle').textContent=status.enabled?'暂停自动修炼':'开始自动修炼';$('name').textContent=c.name||'尚未连接角色';$('character-detail').textContent=`凡修 ${s.version||''} · ${s.network_blocked?'原客户端正在恢复服务器连接':s.online?'当前客户端会话已连接':'等待游戏恢复会话'}`;$('run-state').textContent=status.enabled?'自动修炼中':status.connected&&!s.ready?(s.login_queue?.active?'原生排队':s.network_blocked?'连接恢复中':s.battle_recovery?.state==='replaying'?'恢复战斗结算':'等待角色'):status.connected?'已暂停':'待连接';$('level').textContent=c.level==null?'待同步':`Lv. ${c.level}`;$('exp').textContent=`${number(c.exp)} / ${number(c.exp_needed)}`;$('wuxing').textContent=number(c.wuxing);$('cleared').textContent=number(s.progress?.cleared_ids?.length);$('success').textContent=number(status.stats.success||0);$('exp-fill').style.width=`${Math.min(100,(c.exp||0)/Math.max(1,c.exp_needed||1)*100)}%`;$('current-task').textContent=status.pending?.label||(status.connected&&(s.bridge_revision||0)<(status.minimum_bridge_revision||16)?'等待自有桥接在空闲时更新':status.reason);const selected=s.idle?.selected;$('idle-place').textContent=selected?`难度 ${selected.difficulty+1} · 第 ${selected.tier+1} 层 · ${selected.stage+1} 关`:'等待已通关关卡';$('next-place').textContent=s.next_dungeon?.name||'等待解锁';
document.querySelectorAll('[data-count]').forEach(el=>el.textContent=el.dataset.count==='gacha'?`本次 ${status.stats.gacha||0} 批`:`已做 ${status.stats[el.dataset.count]||0} 次`);renderTaskControls();
document.querySelectorAll('[data-feedback]').forEach(el=>{const kind=el.dataset.feedback,event=status.events?.find(e=>e.kind===kind&&['success','warning'].includes(e.level));if((status.pending?.kind===kind||status.pending?.parent_kind===kind)){el.textContent=`执行中 · 等待游戏确认 ${number(status.pending_seconds||0)} 秒`;el.classList.remove('failed');}else if(event){el.textContent=event.message.replace((status.labels[kind]||'')+'：','').replace('server busy','服务器繁忙，将按退避策略重试');el.classList.toggle('failed',event.level==='warning');}});
if(lastConnection!==status.connected){notice(status.connected?'已连接当前游戏。开关与参数会自动保存，立即执行同样遵循资源保护和解锁条件。':'等待当前游戏内桥接连接。');lastConnection=status.connected;}
const equipped=c.equip_slots||[],score=e=>Object.entries(config.weights).reduce((v,[k,w])=>v+(e.stats?.[k]||0)*w,0),items=[...(s.equipment||[])].sort((a,b)=>(equipped.includes(b.id)-equipped.includes(a.id))||score(b)-score(a));$('equipment-count').textContent=`${items.length} 件 · ${equipped.filter(id=>id>=0).length} 件穿戴中`;$('equipment-body').innerHTML=items.map(e=>`<tr><td>${safe(e.name)} <small>#${e.id}</small></td><td>${qualityNames[e.quality]||safe(e.quality)}</td><td>${e.level}</td><td>${number(score(e))}</td><td class="${e.locked||config.protected_equipment.includes(e.id)||config.manual_locks.includes('equipment:'+e.id)?'protected':''}">${e.locked?'游戏内锁定':config.manual_locks.includes('equipment:'+e.id)?'固定锁':config.protected_equipment.includes(e.id)?'手动保护':equipped.includes(e.id)?'穿戴中':e.bound!==true?(isTradePreserved({...e,kind:'equipment',trade_category:'equipment'})?'分类保留 · 未绑定':'可用 · 游戏装备'):'背包 · 绑定'}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">等待同步</td></tr>';
if($('maintenance-status'))$('maintenance-status').textContent=status.maintenance?.message||'断线恢复与Steam更新由独立EXE管理；当前通过网页查看游戏状态。';renderExecutionStatus();renderMultiplayerCapabilities();renderGrowth();renderGachaBalance();renderWorldExplorationStatus();renderBreakthroughStatus();renderSynthSummary();renderWorld();renderEvents();renderTaskControls();renderProtection();renderInventory();if(status.app_name){document.title=status.app_name;document.querySelector('.brand>span:last-child').textContent=status.app_name;}}
function renderMultiplayerCapabilities() {
 const card=document.querySelector('[data-card="multiplayer_realm"]');if(!card)return;
 const m=status.state.multiplayer||{};
 const unsupported=m.enabled && m.escape_supported===false;
 card.querySelectorAll('[data-param="mp_escape_hp"]').forEach(el=>{const field=el.closest('.parameter');if(field)field.hidden=unsupported;});
 let summary=card.querySelector('[data-mp-capability]');
 if(!summary){summary=document.createElement('p');summary.dataset.mpCapability='';summary.className='task-summary';card.append(summary);}
 summary.hidden=!unsupported;
 summary.textContent=unsupported?'当前原生版本不提供战斗逃脱。助手等待原生战斗结算，探索中仍按撤离条件处理。':'';
}
function renderExecutionStatus() {
 const detail=status.execution||{title:status.enabled?'自动修炼已开启':'等待运行状态',message:status.reason||'等待同步'};
 $('execution-title').textContent=detail.title;
 $('execution-detail').textContent=detail.message;
 const s=status.state;
 if(!status.connected||!s.ready){$('client-growth').textContent='等待角色就绪后同步成长状态。';return;}
 const parts=[];
 const bonus=Number(s.breakthrough_preparation?.failure_bonus||0);
 if(bonus>0)parts.push(`当前境界突破失败加成 +${percent(bonus)}`);
 const pill=s.native_auto_pill;
 if(pill?.active){const name=(s.pills||[]).find(p=>p.id===pill.pill_id)?.name||`丹药 ${pill.pill_id}`;parts.push(`原生自动服丹：${name}，剩余 ${number(pill.remaining)} 次，自动增益丹暂缓`);}
 else if(pill)parts.push('原生自动服丹：未运行');
 const fashion=s.fashion_collection;
 if(fashion?.known)parts.push(`时装收集 ${number(fashion.activated_count)} 件 · 属性加成 ${number(fashion.percent)}% · 挂机加成 ${number(fashion.idle_exp_percent)}%`);
 $('client-growth').textContent=parts.join('；')||'成长状态等待游戏同步。';
}
function renderWorldExplorationStatus() {
 const el=document.querySelector('[data-world-explore-status]');
 if(!el)return;
 const detail=status.task_details?.world_explore;
 if(!status.connected||!status.state.ready||!detail){el.textContent='等待游戏同步世界探索状态。';return;}
 const stocks=(detail.props||[]).map(p=>`${p.name} ${number(p.count)} 个（绑定${p.bound_count==null?'待同步':number(p.bound_count)}，每次${number(p.cost)}，保留${number(p.reserve)}）`).join(' · ');
 let scheduling='';
 if(detail.ready){
  if(!config.tasks.world_explore)scheduling='自动探索开关已关闭，可立即执行单次。';
  else if(!status.enabled)scheduling='自动修炼已暂停。';
  else if(status.pending?.kind==='world_explore')scheduling='执行中，等待游戏确认。';
  else if(status.pending||status.state.battle||status.state.pending)scheduling='等待当前操作或战斗完成。';
  else scheduling='等待探索间隔与任务调度。';
 }
 el.textContent=`${detail.message}${scheduling} ${stocks}`;
}
function renderGachaBalance() {
  const el = document.querySelector('[data-gacha-balance]');
  if (!el) return;
  const s = status.state;
  if (!status.connected || !s.ready) { el.textContent = '等待游戏同步悟性与化物消耗。'; return; }
  const wuxing = Number(s.character?.wuxing || 0), reserve = config.reserve_wuxing;
  const cost = Math.max(1, Math.trunc(Number(s.gacha_cost || 1)));
  const count = Math.max(0, Math.floor((wuxing - reserve) / cost));
  let reason;
  if (!s.features?.explore) reason = '等待游戏解锁化物';
  else if (!count) reason = wuxing <= reserve ? '已到保留量，等待新增悟性' : '盈余不足一次，等待新增悟性';
  else if (!config.tasks.gacha) reason = '自动化物开关已关闭';
  else if (!status.enabled) reason = '自动修炼已暂停';
  else if (status.pending?.kind === 'gacha') reason = '化物执行中，等待游戏确认';
  else if (s.battle || s.pending > 0 || status.pending) reason = '等待当前操作或战斗完成';
  else reason = `等待调度，当前单批最多${Math.max(1,Number(s.gacha_batch_limit||1))}次${Number(s.character?.level||0)<Number(s.gacha_batch_unlock_level||10)?'（'+number(s.gacha_batch_unlock_level||10)+'级解锁批量）':''}`;
  el.textContent = `悟性 ${number(wuxing)} · 保留 ${number(reserve)} · 每次消耗 ${number(cost)} · 当前可化物 ${number(count)} 次。${reason}。`;
}
function renderWorld(){const s=status.state,w=s.world||{},names={ordinary:'普通洞府',herb:'灵草',material:'材料',empty:'空地',spring:'灵泉',relic:'遗迹',stronghold:'据点',forge:'锻炉',breakthrough_realm:'突破秘境',player:'玩家',cultivator:'修士',robot:'游历修士'};$('world-count').textContent=`${w.point_count||0} / ${Math.min(config.world_point_limit??20,w.max_points??20)} 个有效坐标${w.expired_point_count?' · 另有 '+w.expired_point_count+' 个过期坐标':''}`;$('world-status').innerHTML=`<div>免费探索剩余 <strong>${w.free_remaining??'待同步'}</strong></div><div>今日探索 <strong>${w.daily_count??0}</strong> / ${config.world_daily_limit}</div><div>待处理奇遇 <strong>${w.pending_event?.event_id?'有':'无'}</strong></div>`;$('world-body').innerHTML=(w.points||[]).map(p=>`<tr><td>#${p.marker_id}</td><td>${names[p.type]||safe(p.type)}</td><td>${qualityNames[p.quality]||safe(p.quality)}</td><td>${p.is_current?'当前洞府':p.expired?'已过期（不占探索上限）':p.difficulty?({EASY:'适合挑战',CAUTION:'谨慎挑战',DANGER:'危险'}[p.difficulty]):p.type==='spring'&&s.character?.exp>=s.character?.exp_needed?'修为已满，升级或突破后吸取':p.choices?'等待选择奖励':'可规划'}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">暂无发现的坐标</td></tr>';
$('unlock-status').innerHTML=Object.entries(s.features||{}).map(([k,v])=>`<div><span>${({explore:'世界探索',dungeon:'副本挑战',battle_idle:'副本挂机',equipment:'装备',gongfa:'功法',alchemy:'炼丹',synth:'合成',mail:'邮件',refine:'炼器',furnace:'炉鼎'}[k])||safe(k)}</span><strong>${v?'已解锁':'等待解锁'}</strong></div>`).join('')+`<div><span>境界推进</span><strong>${s.realm_locked?'已到当前版本开放上限':'按实际进度推进'}</strong></div><div><span>多人秘境</span><strong>${safe(s.multiplayer_realm?.status||'等待同步')}</strong></div>`;}
function renderEvents(){const filter=$('log-filter').value,events=(status.events||[]).filter(e=>filter==='all'||e.level===filter);$('log-count').textContent=(status.events||[]).length;$('events').innerHTML=events.map(e=>`<div class="event"><time>${safe(new Date(e.time).toLocaleTimeString('zh-CN',{hour12:false}))}</time><span class="${safe(e.level)}">${{success:'完成',warning:'关注',info:'记录'}[e.level]||'记录'}</span><span>${safe(e.message)}</span></div>`).join('')||'<p class="empty">暂无记录</p>';}
function adoptRemoteConfig(remote) {
  if (saving) return;
  configReconcileRequired=false;
  confirmedConfig = structuredClone(remote);
  config = structuredClone(remote);
  syncConfigControls();
}
function syncConfigControls(){
  document.querySelectorAll('[data-task]').forEach(el => {
    el.checked = !!config.tasks[el.dataset.task];
    el.closest('.function-card').classList.toggle('on', el.checked);
  });
  const keys = new Set([...document.querySelectorAll('[data-param]')].map(el => el.dataset.param));
  keys.forEach(key => syncField(key, true));
  document.querySelectorAll('[data-weight]').forEach(el => {
    if (!el.dataset.dirty && el !== document.activeElement) el.value = config.weights[el.dataset.weight];
  });
}
function renderTaskControls(){
 if(!status)return;
 const s=status.state,busy=!!status.pending||s.battle||s.battle_pending||s.pending>0||status.retry_after_seconds>0;
 document.querySelectorAll('[data-run]').forEach(el=>{
  const kind=el.dataset.run,queued=(status.manual_queue||[]).some(row=>row.kind===kind),own=(status.pending?.kind===kind||status.pending?.parent_kind===kind);
  const reason=!status.connected?'等待游戏连接':!s.ready?'等待角色就绪':(s.bridge_revision||0)<(status.minimum_bridge_revision||16)||kind==='resource_pack'&&(s.bridge_revision||0)<12?'重启游戏加载桥接':'';
  el.disabled=!!reason||own||submittingTasks.has(kind);
  el.textContent=submittingTasks.has(kind)?'提交中':own?'执行中':queued?'取消排队':reason||busy?'排队执行':'立即执行';
  if(reason)el.textContent=reason;
  el.title=reason|| (own?'此任务正在等待游戏确认':queued?'点击取消尚未提交的任务':busy?'可点击排队，当前操作结束后再检查最新条件':'按最新材料、保护和解锁条件执行一次');
  el.setAttribute('aria-label',`${status.labels[kind]}：${el.textContent}`);
  const feedback=document.querySelector(`[data-feedback="${kind}"]`);
  if(queued&&feedback)feedback.textContent=status.retry_after_seconds>0?`服务器繁忙，${Math.ceil(status.retry_after_seconds)}秒后复核排队任务；可点击取消。`:'已排队，当前操作结束后按最新状态复核条件。';
  else if(['world_points','world_events'].includes(kind)&&feedback&&!own)feedback.textContent=status.task_details?.[kind]?.message||'等待游戏同步探索处理状态。';
  else if(status.task_feedback?.[kind]&&feedback&&!own)feedback.textContent=status.task_feedback[kind].replace('server busy','服务器繁忙，等待退避后再执行');
  else if(kind==='resource_pack'&&feedback)feedback.textContent='只使用未被分类品质保留且未固定锁定的可交易原料；受保护的输入会跳过。';
 });
}
function renderSynthSummary(){
 const card=document.querySelector('[data-card="synth"]');if(!card)return;
 let summary=card.querySelector('[data-synth-summary]');
 if(!summary){summary=document.createElement('p');summary.dataset.synthSummary='';summary.className='task-summary';card.append(summary);}
 summary.textContent=status.task_details?.synth?.message||'等待助手同步可合成数量与保护条件。';
}
async function refresh(){
 if(refreshPromise)return refreshPromise;
 refreshPromise=(async()=>{const revision=configRevision;
  try{const r=await fetchTimed('/api/status');if(!r.ok)throw Error('本机服务暂未就绪');const next=await r.json();const recovered=serviceFailures>0;status=next;lastStatusAt=Date.now();serviceFailures=0;
   if(!config){confirmedConfig=structuredClone(status.config);config=structuredClone(status.config);renderTasks();fillSettings();}else if(revision===configRevision){adoptRemoteConfig(status.config);}render();if(recovered)notice('本机服务已恢复连接，开关与参数已保留。');
  }catch(error){serviceFailures++;$('connection').textContent='正在重新连接本机服务';notice('本机服务暂时未响应，正在自动重连；已保存的开关和参数保留。',true);
   if(!lastStatusAt||Date.now()-lastStatusAt>12000){$('toggle').disabled=!status?.enabled;document.querySelectorAll('[data-run]').forEach(el=>{el.disabled=true;el.textContent='等待连接';el.title='本机服务恢复后自动启用';});}
  }
 })();
 try{return await refreshPromise;}finally{refreshPromise=null;}
}
async function pollStatus(){await refresh();setTimeout(pollStatus,1800);}

$('toggle').addEventListener('click',async()=>{try{await post(status.enabled?'/api/stop':'/api/start');await refresh();}catch(e){notice(e.message,true);}});
$('connect').addEventListener('click',async()=>{try{const r=await post('/api/connect');notice(r.message);await refresh();}catch(e){notice(e.message,true);}});
$('save').addEventListener('click',async()=>{try{const weights={};document.querySelectorAll('[data-weight]').forEach(el=>weights[el.dataset.weight]=Number(el.value));await saveConfigEdit(['weights'],weights);document.querySelectorAll('[data-weight]').forEach(el=>{if(Number(el.value)===weights[el.dataset.weight])delete el.dataset.dirty;});notice('全局参数与评分权重已保存；保存期间的新输入保留待提交。');}catch(e){notice(e.message,true);}});
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b===button));document.querySelectorAll('.tab-content').forEach(section=>section.hidden=section.id!==button.dataset.tab);}));
$('weights').addEventListener('input',event=>{if(event.target.matches('[data-weight]'))event.target.dataset.dirty='true';});
$('log-filter').addEventListener('change',renderEvents);
$('export').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(config,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='凡修助手配置.json';a.click();URL.revokeObjectURL(url);});
$('import').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;await saveConfigEdit(null,JSON.parse(await file.text()));await refresh();notice('配置已导入。');}catch(err){notice(err.message,true);}finally{e.target.value='';}});
$('reset').addEventListener('click',async()=>{try{await saveConfigEdit(null,{});await refresh();notice('已恢复默认策略。');}catch(e){notice(e.message,true);}});
$('preserve-tradable').addEventListener('change',async e=>{try{await saveConfigEdit(['preserve_tradable'],e.target.checked);notice(config.preserve_tradable?'分类与品质保留已开启。':'分类与品质保留已关闭，Steam保护与固定锁独立生效。');}catch(err){notice(err.message,true);}render();});

let selectedGroup='all';
function applyFilter(){const q=$('function-search').value.trim().toLowerCase();document.querySelectorAll('.function-group').forEach(group=>{let visible=0;group.querySelectorAll('.function-card').forEach(card=>{const show=(selectedGroup==='all'||group.dataset.groupName===selectedGroup)&&card.textContent.toLowerCase().includes(q);card.hidden=!show;visible+=show;});group.hidden=!visible;});}
$('function-search').addEventListener('input',applyFilter);document.querySelectorAll('[data-group]').forEach(button=>button.addEventListener('click',()=>{selectedGroup=button.dataset.group;document.querySelectorAll('[data-group]').forEach(b=>b.classList.toggle('active',b===button));applyFilter();}));
pollStatus();

$('preserve-steam').addEventListener('change',async e=>{try{await saveConfigEdit(['preserve_steam_tradable'],e.target.checked);notice(config.preserve_steam_tradable?'已开启 Steam 可上架物品保护。':'Steam 保护已关闭，分类保留与固定锁独立生效。');}catch(err){notice(err.message,true);}render();});

function renderBreakthroughStatus() {
 const el=document.querySelector('[data-breakthrough-status]');if(!el)return;
 const d=status.task_details?.breakthrough;
 if(!status.connected||!status.state.ready||!d){el.textContent='等待游戏同步突破条件。';return;}
 const percent=v=>`${Number((Number(v||0)*100).toFixed(1))}%`;
 const current=d.minimum_rate===d.maximum_rate?percent(d.minimum_rate):`${percent(d.minimum_rate)}～${percent(d.maximum_rate)}`;
 if(!d.active){el.textContent=d.message;return;}
 const shortageCount=(d.shortages||[]).filter(r=>r.purpose==='breakthrough').length;
 const conditions=[['修为',d.experience_ready,d.experience_ready?'已满':'修炼中'],['突破材料',d.materials_ready,d.materials_ready?'已备齐':`缺 ${shortageCount} 种`],['成功率',d.rate_ready,`${current} / 目标 ${percent(d.target_rate)}`]];
 const rows=(d.materials||[]).map(r=>`<tr><td>${safe(r.name)}${r.purpose==='pill'?'<small>炼丹原料</small>':''}${r.protected?'<small>含受保护库存</small>':''}</td><td>${number(r.usable)} / ${number(r.need)}</td><td>${r.missing?`缺 ${number(r.missing)}`:'已备齐'}</td></tr>`).join('');
 el.innerHTML=`<div class="breakthrough-conditions">${conditions.map(([label,ok,value])=>`<div class="condition ${ok?'met':'waiting'}"><span>${label}</span><strong>${value}</strong></div>`).join('')}</div><p class="breakthrough-next">${safe(d.message)}</p>${Number(d.failure_bonus)>0?`<p class="parameter-help">本境界失败加成 +${percent(d.failure_bonus)}，已计入当前成功率。</p>`:''}${rows?`<div class="breakthrough-materials"><table><caption>材料清单 · 按保护规则计算可用数量</caption><thead><tr><th scope="col">物品</th><th scope="col">可用 / 需要</th><th scope="col">状态</th></tr></thead><tbody>${rows}</tbody></table></div>`:''}${d.pill_name?`<p class="parameter-help">${safe(d.pill_name)}：需 ${number(d.pills_needed)} 颗，可用 ${number(d.pills_available)} 颗。随机丹药按最低增益判断。</p>`:''}`;
}

function renderGrowth() {
 const d=status.growth;
 if(!$('growth-panel'))return;
 if(!status.connected||!status.state.ready||!d){$('growth-message').textContent=status.connected?(d?.message||status.reason):'等待游戏同步成长需求。';$('growth-phase').textContent=status.state.login_queue?.active?'原生排队':'等待角色';$('growth-steps').innerHTML='';$('growth-supply').textContent='';$('growth-needs').innerHTML='';return;}
 $('growth-message').textContent=d.message;
 $('growth-phase').textContent=({supply:'正在补给',breakthrough:'准备突破',growth:'持续成长',independent:'独立调度'}[d.phase])||'准备中';
 $('growth-steps').innerHTML=(d.steps||[]).map(step=>`<li>${safe(step)}</li>`).join('');
 const source=d.gathering_stage?`补料挂机：${d.gathering_stage.name}。`:'当前无更合适的补料挂机地点。';
 const refining=config.tasks.world_forge&&d.world_forge?.ready?d.world_forge:d.refine;
 $('growth-supply').textContent=`${source} ${refining?.message||''}`;
 const names={breakthrough:'突破与突破丹',upgrade:'穿戴装备强化',alchemy:'成长丹药',material_synth:'强化材料合成'};
 $('growth-needs').innerHTML=(d.requirements||[]).map(r=>`<tr><td>${safe(r.name)}</td><td>${number(r.usable)} / ${number(r.need)}</td><td>${safe(r.owners.map(o=>names[o]||o).join('、'))} · ${r.reason?safe(r.reason):r.missing?`缺 ${number(r.missing)}`:'已备齐'}</td></tr>`).join('')||'<tr><td colspan="3" class="empty">当前没有待补材料，继续升级、换装和修炼。</td></tr>';
 document.querySelectorAll('[data-card="refine"] [data-feedback], [data-card="world_forge"] [data-feedback]').forEach(el=>{
  if(status.pending?.kind!==el.dataset.feedback)el.textContent=d[el.dataset.feedback]?.message||'';
 });
}
