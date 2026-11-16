'use strict';
const tradeCategories={equipment:'装备',material:'材料',consumable:'消耗品',gongfa:'功法',fashion:'时装'};
let inventorySignature='',inventoryRequested=0,inventoryRequestBusy=false;
const lockingItems=new Set();
let inventorySort='quality',inventoryDirection='desc';
try{
 const saved=localStorage.getItem('fanxiu.inventorySort'),direction=localStorage.getItem('fanxiu.inventoryDirection');
 if(['quality','level','count','name','native'].includes(saved))inventorySort=saved;
 if(['asc','desc'].includes(direction))inventoryDirection=direction;
}catch(_){}
function compareInventory(a,b){
 const direction=inventoryDirection==='asc'?1:-1;
 if(inventorySort==='native')return 0;
 if(inventorySort==='name')return direction*String(a.name).localeCompare(String(b.name),'zh-CN',{numeric:true})||a.key.localeCompare(b.key,'en',{numeric:true});
 const value=item=>inventorySort==='quality'?(Object.hasOwn(qualityNames,item.quality)?Object.keys(qualityNames).indexOf(item.quality):null):inventorySort==='level'?(Number(item.level)>0?Number(item.level):null):Number(item.count)||0;
 const left=value(a),right=value(b);
 // Unavailable levels and unidentified qualities stay last in either direction.
 if(left===null&&right!==null)return 1;if(left!==null&&right===null)return -1;
 return direction*((left??0)-(right??0))||a.key.localeCompare(b.key,'en',{numeric:true});
}
function saveInventorySort(){
 try{localStorage.setItem('fanxiu.inventorySort',inventorySort);localStorage.setItem('fanxiu.inventoryDirection',inventoryDirection);}catch(_){}
 renderInventory();
}

function initializeProtection(){
 $('trade-categories').innerHTML=Object.entries(tradeCategories).map(([key,name])=>`<div class="trade-category"><label><input type="checkbox" data-trade-category="${key}"><strong>${name}</strong></label><details><summary>保留品质 <span data-trade-summary="${key}"></span></summary><div class="quality-options">${Object.entries(qualityNames).map(([q,label])=>`<label><input type="checkbox" data-trade-quality="${q}" data-category="${key}">${label}</label>`).join('')}</div></details></div>`).join('');
 for(const [key,name] of Object.entries(tradeCategories))$('inventory-category').add(new Option(name,key));
 for(const [key,name] of Object.entries(qualityNames))$('inventory-quality').add(new Option(name,key));
 $('inventory-sort').value=inventorySort;
 $('inventory-sort').addEventListener('change',event=>{inventorySort=event.target.value;saveInventorySort();});
 $('inventory-sort-direction').addEventListener('click',()=>{inventoryDirection=inventoryDirection==='asc'?'desc':'asc';saveInventorySort();});
 $('trade-categories').addEventListener('change',async event=>{
  const input=event.target,key=input.dataset.tradeCategory||input.dataset.category;
  if(!key||!config)return;
  const field=input.dataset.tradeCategory?'enabled':'qualities';
  let value=input.checked;
  if(field==='qualities'){const selected=new Set(config.trade_rules[key].qualities);if(input.checked)selected.add(input.dataset.tradeQuality);else selected.delete(input.dataset.tradeQuality);value=Object.keys(qualityNames).filter(q=>selected.has(q));}
  try{await saveConfigEdit(['trade_rules',key,field],value);notice('分类与品质已保存，所有物品操作会按新规则复核。');}
  catch(error){notice(error.message,true);}
  renderProtection();render();
 });
 $('view-steam').addEventListener('click',()=>{$('inventory-steam').value='owned';document.querySelector('[data-tab="fixed-lock"]').click();renderInventory();});
 $('trade-expand').addEventListener('click',()=>{const open=$('trade-rules').hidden;$('trade-rules').hidden=!open;$('trade-expand').setAttribute('aria-expanded',String(open));});
 ['inventory-search','inventory-category','inventory-quality','inventory-locked-only','inventory-steam'].forEach(id=>$(id).addEventListener(id==='inventory-search'?'input':'change',renderInventory));
 $('inventory-refresh').addEventListener('click',async()=>{
  if(inventoryRequestBusy)return;inventoryRequestBusy=true;renderInventory();
  try{const result=await post('/api/inventory/refresh');inventoryRequested=result.generation;notice(result.message);await refresh();}
  catch(error){notice(error.message,true);}finally{inventoryRequestBusy=false;renderInventory();}
 });
 $('inventory-grid').addEventListener('click',async event=>{
  const button=event.target.closest('[data-item-lock]');if(!button||!config)return;
  const key=button.dataset.itemLock;if(lockingItems.has(key))return;
  const value=!config.manual_locks.includes(key);lockingItems.add(key);button.disabled=true;button.textContent='保存中';
  try{
   const result=await post('/api/lock',{key,locked:value});
   config.manual_locks=value?[...new Set([...config.manual_locks,key])]:config.manual_locks.filter(x=>x!==key);
   notice(result.message);renderInventory();await refresh();
  }catch(error){notice(error.message,true);}
  finally{lockingItems.delete(key);inventorySignature='';renderInventory();const replacement=[...document.querySelectorAll('[data-item-lock]')].find(el=>el.dataset.itemLock===key);replacement?.focus({preventScroll:true});}
 });
}
function renderProtection(){
 if(!config)return;
 const names=[];
 for(const [key,name] of Object.entries(tradeCategories)){
  const rule=config.trade_rules[key];if(rule.enabled&&rule.qualities.length)names.push(`${name}${rule.qualities.length===9?'全品质':rule.qualities.length+'种品质'}`);
  const control=document.querySelector(`[data-trade-category="${key}"]`);control.checked=rule.enabled;
  document.querySelector(`[data-trade-summary="${key}"]`).textContent=rule.qualities.length===9?'全部':`${rule.qualities.length} / 9`;
  document.querySelectorAll(`[data-trade-quality][data-category="${key}"]`).forEach(el=>{el.checked=rule.qualities.includes(el.dataset.tradeQuality);});
 }
 $('protection-detail').textContent=`${config.preserve_tradable?'当前保留':'预选范围'}：${names.join('、')||'未选择分类或品质'}。${config.preserve_tradable?'':'开启此总开关后生效。'}`;
 $('preserve-steam').checked=config.preserve_steam_tradable;
 $('steam-protection-state').textContent=config.preserve_steam_tradable?'已开启':'已关闭';
 const steam=status?.state?.steam_inventory||{};
 $('steam-inventory-status').textContent=steam.complete?`${steam.stacks} 个 Steam 堆叠 · ${number(steam.quantity)} 件 · 背包匹配 ${(status.state.inventory_view?.items||[]).filter(row=>row.steam_tradable_count>0).length} 种 · ${steam.updated_at?new Date(steam.updated_at*1000).toLocaleTimeString('zh-CN',{hour12:false}):''}${steam.refreshing?' · 同步中':''}${steam.catalogue_ready?'':' · 定义识别中'}`:(steam.message||'等待 Steam 库存同步');
 if(!$('inventory-parameters').children.length){$('inventory-parameters').innerHTML=['inventory_auto_refresh','inventory_refresh_seconds'].map(fieldHTML).join('');bindParameters($('inventory-parameters'));}
 document.querySelectorAll('[data-param="equip_min_gain"]').forEach(el=>{el.disabled=!config.equip_use_weights;el.title=config.equip_use_weights?'仅用于权重评分换装':'启用权重评分后使用此参数';});
 document.querySelectorAll('[data-weight]').forEach(el=>el.disabled=!config.equip_use_weights);
}
function isFixedLocked(item){return config.manual_locks.includes(item.key)||config.manual_locks.includes(`${item.kind}:${item.id}`);}
function isTradePreserved(item){
 const steam=config.preserve_steam_tradable&&item.kind!=='equipment'&&(item.steam_trade_known!==true||item.steam_tradable===true);
 const rule=config.trade_rules[item.trade_category];
 return steam||config.preserve_tradable&&rule?.enabled&&rule.qualities.length>0&&(!Object.hasOwn(qualityNames,item.quality)||rule.qualities.includes(item.quality));
}
function renderInventory(){
 if(!status||!config)return;
 const view=status.state.inventory_view||{},rows=[...(view.items||[])],present=new Set(rows.map(x=>x.key));
 for(const key of config.manual_locks)if(!present.has(key)){const [kind,id]=key.split(':');rows.push({key,kind,id:Number(id),trade_category:kind==='pill'?'consumable':kind==='herb'?'material':kind,name:`暂不在背包 · ${key}`,count:0,bound_count:0,quality:'',absent:true});}
 const supported=(status.state.bridge_revision||0)>=(status.minimum_bridge_revision||16),waiting=inventoryRequestBusy||(inventoryRequested>0&&(view.generation||0)<inventoryRequested);
 $('inventory-refresh').disabled=!status.connected||!supported||inventoryRequestBusy;
 $('inventory-refresh').textContent=waiting?'正在读取背包…':'手动更新背包';
 $('inventory-updated').textContent=view.updated_at?`上次更新 ${new Date(view.updated_at*1000).toLocaleTimeString('zh-CN',{hour12:false})}${waiting?' · 等待新快照':''}`:'等待游戏读取';
 const query=$('inventory-search').value.trim().toLowerCase(),category=$('inventory-category').value,quality=$('inventory-quality').value,only=$('inventory-locked-only').checked,steamFilter=$('inventory-steam').value;
 const steamMatch=item=>steamFilter==='all'||steamFilter==='owned'&&item.steam_tradable_count>0||steamFilter==='capable'&&item.steam_tradable===true||steamFilter==='internal'&&item.steam_trade_known===true&&item.steam_tradable!==true||steamFilter==='unknown'&&item.steam_trade_known!==true;
 const filtered=rows.filter(item=>steamMatch(item)&&(!query||`${item.name} ${item.key}`.toLowerCase().includes(query))&&(category==='all'||item.trade_category===category)&&(quality==='all'||item.quality===quality)&&(!only||isFixedLocked(item)||item.game_locked||item.kind==='equipment'&&config.protected_equipment.includes(item.id))).sort(compareInventory);
 $('inventory-sort-direction').textContent=inventoryDirection==='asc'?'升序':'降序';
 $('inventory-sort-direction').disabled=inventorySort==='native';
 $('inventory-sort-direction').title=inventorySort==='native'?'按游戏背包原顺序排列':inventorySort==='level'?'等级从低到高或从高到低；没有等级的物品置后':inventorySort==='quality'?'凡品至至宝；未知品质置后':inventorySort==='count'?'按当前库存总数量排列':'按名称本地化顺序排列';
 $('inventory-sort-direction').setAttribute('aria-label',`当前${inventoryDirection==='asc'?'升序':'降序'}，点击切换排序方向`);
 $('inventory-count').textContent=`${(view.items||[]).length} 种物品 · ${config.manual_locks.length} 条固定锁`;
 $('inventory-message').hidden=filtered.length>0;
 $('inventory-message').textContent=!supported?'重启游戏加载新版连接后读取背包。':!status.connected?'游戏连接正在恢复，已保存的固定锁继续保留。':!view.complete?'正在等待读取当前角色背包。':rows.length?'没有符合筛选条件的物品。':'当前背包没有可显示的物品。';
 const signature=JSON.stringify([view.updated_at,view.generation,config.manual_locks,config.protected_equipment,config.preserve_steam_tradable,config.preserve_tradable,config.trade_rules,steamFilter,query,category,quality,only,inventorySort,inventoryDirection,[...lockingItems]]);
 if(signature===inventorySignature)return;inventorySignature=signature;
 $('inventory-grid').innerHTML=filtered.map(item=>{
  const fixed=isFixedLocked(item),legacy=item.kind==='equipment'&&config.protected_equipment.includes(item.id),parentLock=fixed&&!config.manual_locks.includes(item.key);
  const bound=Number(item.bound_count)||0,count=Number(item.count)||0;
  const protectedText=item.game_locked?'游戏内锁定':legacy?'旧编号保护':fixed?'固定锁已生效':isTradePreserved(item)&&bound<count?(config.preserve_steam_tradable&&(item.steam_tradable||item.steam_trade_known!==true)?'Steam 保护':'分类保留范围'):'按任务规则使用';
  const steamText=item.absent?'':item.steam_tradable_count>0?`Steam 库存 ${number(item.steam_tradable_count)} 件`:item.steam_trade_known!==true?'Steam 属性待识别':item.steam_tradable?'Steam 可上架类型 · 当前无未绑定库存':'普通游戏物品';
  const icon=/^[a-f0-9]{64}\.png$/.test(item.icon||'')?`<img src="/icons/${item.icon}" alt="" loading="lazy" width="56" height="56">`:'<span class="item-placeholder" aria-label="暂无可用图标">图</span>';
  return `<article class="inventory-item ${fixed||item.game_locked||legacy?'locked':''}"><div class="item-art">${icon}</div><div class="item-info"><h3>${safe(item.name)}</h3><p>${safe(qualityNames[item.quality]||'品质待识别')} · ${safe(tradeCategories[item.trade_category]||item.kind)}${item.level?' · Lv. '+Number(item.level):''}</p><p>${item.absent?'锁定记录保留':`数量 ${number(count)} · 绑定 ${number(bound)}${item.equipped?' · 穿戴中':''}`}</p><p class="steam-item-info">${safe(steamText)}</p><small>${safe(item.key)}</small></div><div class="item-action"><span class="${fixed||item.game_locked||legacy?'protected':''}">${protectedText}</span><button class="${fixed?'primary':'secondary'}" data-item-lock="${safe(item.key)}" aria-pressed="${fixed}" aria-label="${safe(item.name)}：${fixed?'解除固定锁':'上锁'}" ${lockingItems.has(item.key)||parentLock?'disabled':''}>${lockingItems.has(item.key)?'保存中':parentLock?'整部功法已锁':fixed?'解除固定锁':'上锁'}</button></div></article>`;
 }).join('');
 $('inventory-grid').querySelectorAll('img').forEach(img=>img.addEventListener('error',()=>{img.replaceWith(Object.assign(document.createElement('span'),{className:'item-placeholder',textContent:'图'}));},{once:true}));
}
initializeProtection();
