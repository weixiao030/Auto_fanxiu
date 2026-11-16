"""Item protection shared by planning, configuration and the local lock API."""
from copy import deepcopy
import re

QUALITY_IDS = ('common','fine','rare','epic','legend','myth','perfect','innate','treasure')
CATEGORIES = {'equipment':'装备','material':'材料','consumable':'消耗品','gongfa':'功法','fashion':'时装'}
DEFAULT_RULES = {key:{'enabled':key in ('consumable','gongfa','fashion'),'qualities':list(QUALITY_IDS)} for key in CATEGORIES}
LOCK_PATTERN = re.compile(r'^(equipment|material|herb|pill|fashion|gongfa):[0-9]+(?::[0-9]+)?$')

def validate_rules(raw):
    if not isinstance(raw,dict) or set(raw)-set(CATEGORIES):raise ValueError('交易保留分类无效')
    result=deepcopy(DEFAULT_RULES)
    for key,rule in raw.items():
        if not isinstance(rule,dict) or set(rule)!={'enabled','qualities'} or type(rule['enabled']) is not bool:
            raise ValueError('交易保留分类格式无效')
        values=rule['qualities']
        if not isinstance(values,list) or any(q not in QUALITY_IDS for q in values) or len(set(values))!=len(values):
            raise ValueError('交易保留品质无效')
        result[key]=deepcopy(rule)
    return result

def valid_lock(key):
    if not isinstance(key,str) or len(key)>80 or not LOCK_PATTERN.fullmatch(key):return False
    return key.count(':')==1 or key.startswith('gongfa:')

def locked(config,kind,item_id,layer=None):
    key=f'{kind}:{int(item_id)}'
    keys=config.get('manual_locks',[])
    return key in keys or (layer is not None and f'{key}:{int(layer)}' in keys) or (kind=='equipment' and int(item_id) in config.get('protected_equipment',[]))

def category(kind,info=None):
    info=info or {}
    if kind in ('equipment','fashion','gongfa'):return kind
    if kind=='pill':return 'consumable'
    if kind=='herb':return 'material'
    if info.get('trade_category') in CATEGORIES:return info['trade_category']
    if info.get('category')=='gongfa_page' or info.get('use_type')=='gongfa_page':return 'gongfa'
    if info.get('category') in ('consumable','prop') or info.get('use_type') in ('resource_pack','equipment_box','fashion_box','prop','item_bundle','realm_supply'):return 'consumable'
    return 'material'

def trade_preserved(config,kind,info=None):
    info=info or {}
    # Server equipment instances are not Steam item definitions.
    if kind=='equipment':info={**info,'steam_trade_known':True,'steam_tradable':False}
    # Unknown SDK metadata is protected until the running bridge identifies its definition.
    steam=config.get('preserve_steam_tradable',False) and (info.get('steam_trade_known') is not True or info.get('steam_tradable') is True)
    if not config.get('preserve_tradable',False):return bool(steam)
    rule=config.get('trade_rules',DEFAULT_RULES).get(category(kind,info),{'enabled':True,'qualities':list(QUALITY_IDS)})
    quality=info.get('quality',info.get('rarity',''))
    return bool(steam) or rule['enabled'] and bool(rule['qualities']) and (quality not in QUALITY_IDS or quality in rule['qualities'])

def equipment_allowed(config,item):
    return not item.get('locked') and not locked(config,'equipment',item['id']) and (item.get('bound') is True or not trade_preserved(config,'equipment',item))

def metadata(state,kind,item_id,layer=None):
    key=f'{kind}:{int(item_id)}'+(f':{int(layer)}' if layer is not None else '')
    for item in state.get('inventory_view',{}).get('items',[]):
        if item.get('key')==key:return item
    rows=state.get('materials',[]) if kind=='material' else state.get('pills',[]) if kind=='pill' else state.get('gongfa_options',[]) if kind=='gongfa' else []
    return next((row for row in rows if row.get('id')==item_id),{})

def available(config,state,kind,item_id,*,layer=None,selector=False,info=None,total=None,bound=None):
    if locked(config,kind,item_id,layer):return 0
    info=metadata(state,kind,item_id,layer) if info is None else info
    key=f'{kind}:{int(item_id)}'
    if total is None:total=state.get('owned_items',{}).get(key,info.get('count',0))
    if bound is None:bound=state.get('bound_items',{}).get(key,info.get('bound_count',0))
    total = max(0, int(total))
    bound = min(total, max(0, int(bound)))
    # Native stack consumption is bound-first. Keep every protected unbound unit.
    if trade_preserved(config,kind,info):
        return bound
    return total

def source_blocked(config, state, kind, item_id):
    # A mixed stack can be replenished and spent within its bound budget.
    return locked(config, kind, item_id)


def requirements_allowed(config,state,requirements,reserve=0,count=1):
    merged={}
    for req in requirements:
        key=(req.get('kind','material'),int(req.get('id',0)))
        merged[key]=merged.get(key,0)+int(req.get('count',0))*count
    return bool(merged) and all(amount>0 and available(config,state,kind,mid)-amount>=reserve for (kind,mid),amount in merged.items())

def command_keys(kind,params,state):
    keys=set()
    def add(resource,mid):
        if mid is not None and int(mid)>=0:keys.add(f'{resource}:{int(mid)}')
    def needs(rows):
        for row in rows:add(row.get('kind','material'),row.get('id'))
    if kind in ('equip','upgrade'):
        add('equipment',params.get('item_id'))
        if kind=='equip':
            slots=state.get('character',{}).get('equip_slots',[]);index=params.get('slot_idx',-1)
            if 0<=index<len(slots):add('equipment',slots[index])
        else:
            item=next((e for e in state.get('equipment',[]) if e['id']==params.get('item_id')),{});needs(item.get('upgrade_needs',[]))
    elif kind=='synth':
        for eid in params.get('item_ids',[]):add('equipment',eid)
    elif kind in ('open_pack','material_synth'):add('material',params.get('material_id'))
    elif kind=='resource_pack':add(params.get('kind','material'),params.get('material_id'))
    elif kind=='pill':add('pill',params.get('pill_id'))
    elif kind=='alchemy':
        recipe=next((r for r in state.get('alchemy_recipes',[]) if r['pill_id']==params.get('pill_id') and r['recipe_index']==params.get('recipe_index')),{});needs(recipe.get('materials',[]))
    elif kind in ('refine','world_forge'):
        for mid in params.get('materials',{}):
            row=next((r for r in state.get('refine_inputs',[]) if r['id']==int(mid)),{})
            add(row.get('kind','material'),int(mid))
    elif kind in ('gongfa','gongfa_activate','gongfa_accelerate'):
        gid = params.get('gongfa_id')
        layer = None
        if kind == 'gongfa_activate' and any(g.get('id') == gid for g in state.get('gongfa_options', [])):
            layer = 0
        elif kind == 'gongfa':
            entry = next((g for g in state.get('training_candidates', []) if g.get('id') == gid), {})
            layer = entry.get('layer')
        elif kind == 'gongfa_accelerate':
            entry = next((g for g in state.get('gongfa_options', []) if g.get('id') == gid), {})
            layer = entry.get('training', {}).get('target')
        # Missing target information must still overlap every page of this gongfa.
        if layer is None:
            add('gongfa', gid)
        elif gid is not None:
            keys.add(f'gongfa:{int(gid)}:{int(layer)}')
    elif kind=='breakthrough':
        b=state.get('breakthrough',{});needs(b.get('requirements',b.get('materials',b.get('info',{}).get('materials',[]))))
    elif kind=='home_relocate':add('material',4001)
    elif kind=='world_explore':
        world=state.get('world',{});prop=world.get('mirror' if params.get('use_mirror') else 'rumor',{})
        if params.get('use_mirror') or params.get('use_rumor'):add('material',prop.get('id',prop.get('material_id')))
    elif kind in ('partner_rescue','bounty_publish','slave_escape'):
        owner=state.get('partner',{}) if kind=='partner_rescue' else state.get('world',{})
        prop=owner.get('rescue' if kind=='partner_rescue' else 'bounty_prop' if kind=='bounty_publish' else 'escape_prop',{})
        if 'talisman' in params.get('action','') or kind=='bounty_publish':add('material',prop.get('id'))
    elif kind=='resource_realm' and params.get('action')=='enter':
        if state.get('resource_realm', {}).get('free_remaining', 0) <= 0:
            add('material', state.get('resource_realm', {}).get('token', {}).get('id', 4204))
    elif kind=='multiplayer_realm' and params.get('action')=='enter' and state.get('multiplayer',{}).get('free_entries',0)<=0:
        key=state.get('multiplayer',{}).get('key_item','')
        if valid_lock(key):keys.add(key)
    return keys

def keys_overlap(left,right):
    return left==right or left.startswith(right+':') or right.startswith(left+':')
