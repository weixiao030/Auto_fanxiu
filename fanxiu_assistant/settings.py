from __future__ import annotations
from copy import deepcopy
import math
from .protection import DEFAULT_RULES, validate_rules, valid_lock

QUALITIES = dict(zip(('common','fine','rare','epic','legend','myth','perfect','innate','treasure'),
                     ('凡品','下品','中品','上品','极品','仙品','完美','先天','至宝')))

# Packaged defaults captured from the current user-selected strategy on 2026-11-10.
DEFAULTS = {'preserve_steam_tradable': True,
 'preserve_tradable': False,
 'trade_rules': {'equipment': {'enabled': False,
                               'qualities': ['common',
                                             'fine',
                                             'rare',
                                             'epic',
                                             'legend',
                                             'myth',
                                             'perfect',
                                             'innate',
                                             'treasure']},
                 'material': {'enabled': False,
                              'qualities': ['common',
                                            'fine',
                                            'rare',
                                            'epic',
                                            'legend',
                                            'myth',
                                            'perfect',
                                            'innate',
                                            'treasure']},
                 'consumable': {'enabled': True,
                                'qualities': ['common',
                                              'fine',
                                              'rare',
                                              'epic',
                                              'legend',
                                              'myth',
                                              'perfect',
                                              'innate',
                                              'treasure']},
                 'gongfa': {'enabled': True,
                            'qualities': ['common',
                                          'fine',
                                          'rare',
                                          'epic',
                                          'legend',
                                          'myth',
                                          'perfect',
                                          'innate',
                                          'treasure']},
                 'fashion': {'enabled': True,
                             'qualities': ['common',
                                           'fine',
                                           'rare',
                                           'epic',
                                           'legend',
                                           'myth',
                                           'perfect',
                                           'innate',
                                           'treasure']}},
 'manual_locks': [],
 'equip_use_weights': False,
 'equip_keep_weapon_type': True,
 'inventory_auto_refresh': True,
 'inventory_refresh_seconds': 60,
 'allow_game_restart': False,
 'auto_reconnect': True,
 'reconnect_delay_seconds': 60,
 'reconnect_max_attempts': 0,
 'auto_steam_update': False,
 'steam_update_interval': 1800,
 'interval': 3,
 'reserve_wuxing': 0,
 'min_breakthrough_rate': 0.545,
 'challenge_retry_seconds': 180,
 'upgrade_level_gap': 0,
 'upgrade_reserve': 0,
 'equip_min_gain': 0.02,
 'idle_stage': 'auto',
 'stop_at_level': 0,
 'protected_equipment': [],
 'synth_max_quality': 'treasure',
 'resource_pack_size': '4',
 'resource_pack_reserve': 100,
 'resource_pack_batch': 1,
 'resource_pack_materials': [],
 'world_interval': 15,
 'world_daily_limit': 50,
 'world_point_limit': 20,
 'world_use_rumor': True,
 'world_use_mirror': True,
 'world_prop_reserve': 1,
 'world_mirror_target': 'auto',
 'world_relics': True,
 'world_prune': True,
 'breakthrough_auto_raise': True,
 'breakthrough_auto_find': True,
 'breakthrough_auto_craft': True,
 'breakthrough_auto_use': True,
 'breakthrough_target_rate': 0.545,
 'breakthrough_material_reserve': 0,
 'breakthrough_settings_version': 2,
 'alchemy_reserve': 5,
 'alchemy_batch': 1,
 'pill_reserve': 0,
 'gongfa_preferred': [],
 'gongfa_accelerate_reserve': 2,
 'pill_timed_buffs': True,
 'growth_linked': True,
 'refine_recycle_obsolete': True,
 'refine_obsolete_reserve': 0,
 'refine_surplus_without_demand': False,
 'resource_realm_use_token': True,
 'resource_realm_token_reserve': 1,
 'refine_reserve': 0,
 'refine_max_items': 50,
 'refine_target_level': 1,
 'refine_preferred_id': 0,
 'realm_allow_danger': True,
 'realm_retry_seconds': 600,
 'material_synth_reserve': 2,
 'material_synth_batch': 5,
 'material_synth_demand_only': True,
 'furnace_min_exp': 1,
 'home_reserve': 1,
 'home_min_gain': 5,
 'home_priority': 'growth',
 'social_interval': 120,
 'partner_target': '',
 'partner_auto_invite': False,
 'partner_auto_accept': False,
 'partner_practice_limit': 10,
 'partner_rescue_mode': 'talisman_first',
 'rescue_prop_reserve': 1,
 'pvp_assessment': 'advantage',
 'capture_daily_limit': 3,
 'occupy_daily_limit': 3,
 'pvp_max_injury': 0,
 'pvp_retry_seconds': 900,
 'occupy_min_gain': 5,
 'bounty_interval': 180,
 'bounty_daily_limit': 5,
 'bounty_allow_players': True,
 'bounty_assessment': 'advantage',
 'bounty_publish_captured': False,
 'bounty_prop_reserve': 1,
 'escape_mode': 'talisman_first',
 'escape_prop_reserve': 0,
 'mp_auto_enter': False,
 'mp_interval': 60,
 'mp_extract_hp': 40,
 'mp_escape_hp': 25,
 'mp_event_option': '',
 'mp_max_seconds': 900,
 'weights': {'atk': 1,
             'hp': 0.1,
             'def': 0.6,
             'shield': 0.12,
             'mp': 0.05,
             'mp_regen_per_sec': 2,
             'crit_chance': 1.5,
             'crit_damage': 0.3,
             'attack_speed': 2,
             'cdr': 1.5,
             'lifesteal': 2,
             'dodge_chance': 1,
             'combo_chance': 1,
             'stun_chance': 0.7,
             'counter_chance': 0.5,
             'resist_stun': 0.3},
 'tasks': {'collect': True,
           'levelup': True,
           'equip': True,
           'harvest': True,
           'breakthrough': True,
           'gacha': True,
           'challenge': True,
           'idle_select': True,
           'upgrade': True,
           'gongfa': True,
           'open_pack': True,
           'synth': True,
           'mail': True,
           'world_sync': True,
           'world_explore': True,
           'world_harvest': True,
           'world_points': True,
           'world_events': True,
           'world_prune': True,
           'gongfa_activate': True,
           'gongfa_slots': True,
           'alchemy': True,
           'pill': True,
           'gongfa_accelerate': True,
           'refine': True,
           'world_forge': True,
           'realm_challenge': True,
           'material_synth': True,
           'furnace_absorb': True,
           'home_relocate': True,
           'social_sync': True,
           'partner_practice': True,
           'partner_social': True,
           'partner_rescue': True,
           'player_capture': True,
           'player_occupy': True,
           'bounty_sync': True,
           'bounty_claim': True,
           'bounty_publish': True,
           'slave_escape': True,
           'multiplayer_realm': True,
           'resource_pack': False,
           'resource_realm': True}}

LABELS = {"collect": "领取修炼收益", "levelup": "检查升级", "equip": "择优换装",
          "harvest": "领取挂机掉落", "breakthrough": "境界突破", "gacha": "悟性探索",
          "challenge": "挑战下一关", "idle_select": "选择刷图关卡", "upgrade": "强化装备",
          "gongfa": "功法修炼", "open_pack": "开启资源箱", "synth": "闲置装备合成", "mail": "领取邮件",
          "world_sync": "世界状态同步", "world_explore": "世界地图探索", "world_harvest": "世界资源采集",
          "world_points": "探索据点与灵泉", "world_events": "处理探索奇遇", "world_prune": "清理失效坐标",
          "gongfa_activate": "激活功法", "gongfa_slots": "配置主动功法", "alchemy": "自动炼丹", "pill": "使用成长丹药"}
LABELS.update(material_synth='强化材料合成', furnace_absorb='领取炉鼎经验', home_relocate='择优迁居', gacha='悟性化物', gongfa_accelerate='功法修炼加速', refine='盈余材料炼化', world_forge='世界锻炉炼化', realm_challenge='突破秘境挑战')
LABELS.update(social_sync='道侣状态同步', partner_practice='道侣双修', partner_social='道侣定向结缘',
              partner_rescue='道侣解救', player_capture='主动抓捕', player_occupy='玩家占领',
              bounty_sync='悬赏列表同步', bounty_claim='悬赏挑战', bounty_publish='被捕悬赏求援',
              slave_escape='被捕自动逃脱', multiplayer_realm='多人秘境托管')
LABELS.update(refine='盈余材料炼化', world_forge='世界熔炉炼化', resource_pack='资源打包')

LABELS.update(resource_realm='资源秘境补给')

CONFIG_FIELDS = {
    'growth_linked': ('自动联动成长与补料',),
    'refine_recycle_obsolete': ('回收不再用于后续突破的旧材料',),
    'refine_obsolete_reserve': ('每种旧突破材料保留数量', 0, 100000),
    'refine_surplus_without_demand': ('无缺料目标时仍允许盈余炼化',),
    'resource_realm_use_token': ('免费次数后允许使用资源秘境令',),
    'resource_realm_token_reserve': ('资源秘境令保留数量', 0, 10000),
    'breakthrough_auto_raise': ('自动用丹药提高成功率',),
    'breakthrough_auto_find': ('自动寻找缺少的材料',),
    'breakthrough_auto_craft': ('自动炼制突破丹',),
    'breakthrough_auto_use': ('满修为后自动服用突破丹',),
    'breakthrough_target_rate': ('联动目标成功率（%）', 0, 1),
    'breakthrough_material_reserve': ('突破炼丹每种原料额外保留', 0, 100000),
    'equip_use_weights': ('使用自定义属性权重（默认关闭）',),
    'equip_keep_weapon_type': ('保持当前武器类型',),
    'inventory_auto_refresh': ('自动刷新背包',),
    'inventory_refresh_seconds': ('背包刷新间隔（秒）', 5, 3600),
    'resource_pack_size': ('每包产出数量', {'4':'4份（原料成本5）','20':'20份（原料成本25）','100':'100份（原料成本120）'}),
    'resource_pack_reserve': ('每种可交易原料保留数量', 0, 10000000),
    'resource_pack_batch': ('每次最多打包数量', 1, 30),
    'resource_pack_materials': ('仅打包这些原料编号（空为全部）', 'ids'),
    'social_interval': ('道侣同步间隔（秒）', 30, 3600),
    'partner_target': ('指定道侣好友编号（留空不结缘）', 'steamid'),
    'partner_auto_invite': ('自动向指定编号发邀请',),
    'partner_auto_accept': ('自动接受指定编号的邀请',),
    'partner_practice_limit': ('每日最多双修次数', 0, 100),
    'partner_rescue_mode': ('解救方式', {'talisman':'仅脱身符','battle':'战斗解救','talisman_first':'先符后战斗'}),
    'rescue_prop_reserve': ('解救后脱身符保留数量', 0, 10000),
    'pvp_assessment': ('抓捕与占领战力门槛', {'crush':'仅碾压','advantage':'碾压或优势','close':'允许相近'}),
    'capture_daily_limit': ('每日最多抓捕尝试', 0, 100),
    'occupy_daily_limit': ('每日最多占领尝试', 0, 100),
    'pvp_max_injury': ('允许参战的最大伤势层数', 0, 100),
    'pvp_retry_seconds': ('同一目标失败等待（秒）', 60, 86400),
    'occupy_min_gain': ('占领洞府最少提升（%）', 0, 1000),
    'bounty_interval': ('悬赏同步间隔（秒）', 30, 3600),
    'bounty_daily_limit': ('每日最多悬赏挑战尝试', 0, 100),
    'bounty_allow_players': ('允许挑战玩家悬赏',),
    'bounty_assessment': ('悬赏战力门槛', {'crush':'仅碾压','advantage':'碾压或优势','close':'允许相近'}),
    'bounty_publish_captured': ('被捕时自动对当前主人发布悬赏',),
    'bounty_prop_reserve': ('发布后悬赏令保留数量', 0, 10000),
    'escape_mode': ('逃脱方式（普通失败可能延长囚禁）', {'talisman_only':'仅脱身符','talisman_first':'先符后普通尝试','free_only':'仅普通尝试'}),
    'escape_prop_reserve': ('逃脱后脱身符保留数量', 0, 10000),
    'mp_auto_enter': ('自动空载入场（免费优先，钥匙遵守保护）',),
    'mp_interval': ('秘境状态同步间隔（秒）', 15, 600),
    'mp_extract_hp': ('生命低于此比例尝试撤离（%）', 1, 100),
    'mp_escape_hp': ('战斗生命低于此比例尝试逃脱（%）', 1, 100),
    'mp_event_option': ('事件选项编号（留空交原游戏策略）', 'text'),
    'mp_max_seconds': ('入场后最多探索时长（秒）', 60, 7200),
    'allow_game_restart': ('允许重开游戏（排队期间保持关闭）',),
    'auto_reconnect': ('连接恢复后自动继续任务',),
    'reconnect_delay_seconds': ('断线等待后重试（秒）', 15, 600),
    'reconnect_max_attempts': ('最多恢复次数（0持续重试）', 0, 100),
    'auto_steam_update': ('通过Steam自动更新游戏',),
    'steam_update_interval': ('Steam更新检查间隔（秒）', 300, 86400),
    'material_synth_reserve': ('每种合成原料保留数量', 0, 100000),
    'material_synth_batch': ('每次最多合成份数', 1, 100),
    'material_synth_demand_only': ('仅补齐穿戴装备强化缺口',),
    'furnace_min_exp': ('经验池达到多少再领取', 1, 100000000),
    'home_reserve': ('迁居令保留数量', 0, 10000),
    'home_min_gain': ('洞府评分最少提升（%）', 0, 1000),
    'home_priority': ('洞府增益偏好', {'balanced':'综合收益','growth':'修为成长','combat':'战斗属性','loot':'探索收获'}),
    'refine_reserve': ('炼化每种材料保留数量', 0, 100000),
    'refine_max_items': ('每次炼化最多投入件数', 1, 10000),
    'refine_target_level': ('炼化目标等级', 1, 15),
    'refine_preferred_id': ('炼化偏好奖励编号（0不指定）', 0, 999999),
    'realm_allow_danger': ('允许挑战危险评级的突破秘境',),
    'realm_retry_seconds': ('突破秘境失败等待（秒）', 60, 86400),
    'pill_timed_buffs': ('允许使用限时增益丹药',),
    'world_interval': ('世界探索间隔（秒）', 5, 3600),
    'world_daily_limit': ('世界每日探索上限', 0, 1000),
    'world_point_limit': ('保留地图坐标上限', 1, 20),
    'world_use_rumor': ('免费次数后使用传闻',),
    'world_use_mirror': ('允许使用窥真镜嗅探',),
    'world_prop_reserve': ('探索道具保留数量', 0, 10000),
    'world_mirror_target': ('嗅探目标', {'auto':'自动按成长缺口','herb':'灵草','material':'材料','relic':'遗迹','stronghold':'据点','spring':'灵泉','forge':'锻炉'}),
    'world_relics': ('允许探索带陷阱风险的遗迹',),
    'world_prune': ('地图满时清理失效坐标',),
    'alchemy_reserve': ('炼丹每种材料保留数量', 0, 100000),
    'alchemy_batch': ('每次炼丹数量', 1, 100),
    'pill_reserve': ('每种丹药保留数量', 0, 10000),
    'gongfa_preferred': ('优先主动功法编号（逗号分隔）', 'ids'),
    'gongfa_accelerate_reserve': ('功法加速页保留数量', 0, 10000),
}


def validate_config(raw):
    if not isinstance(raw, dict):
        raise ValueError("配置必须为对象")
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ValueError("未知配置项：" + ",".join(unknown))
    result = deepcopy(DEFAULTS)
    for key, value in raw.items():
        if key in ("tasks", "weights"):
            if not isinstance(value, dict) or set(value) - set(DEFAULTS[key]):
                raise ValueError(f"{key} 包含未知项目")
            result[key].update(value)
        else:
            result[key] = value
    result['trade_rules'] = validate_rules(result['trade_rules'])
    if not isinstance(result['manual_locks'],list) or len(result['manual_locks'])>10000 or any(not valid_lock(key) for key in result['manual_locks']):
        raise ValueError('固定锁条目无效')
    result['manual_locks']=list(dict.fromkeys(result['manual_locks']))
    ranges = {"interval": (2, 60), "reserve_wuxing": (0, 10000000),
              "min_breakthrough_rate": (0, 1), "challenge_retry_seconds": (30, 86400),
              "upgrade_level_gap": (0, 90), "upgrade_reserve": (0, 10000000),
              "equip_min_gain": (0, 1), "stop_at_level": (0, 1000)}
    for key, spec in CONFIG_FIELDS.items():
        if len(spec) == 3: ranges[key] = spec[1:]
        elif len(spec) == 1 and type(result[key]) is not bool: raise ValueError(f'{key} 必须为布尔值')
        elif len(spec) == 2 and isinstance(spec[1], dict) and result[key] not in spec[1]: raise ValueError(f'{key} 选项无效')
    for key, (lo, hi) in ranges.items():
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} 必须在 {lo}–{hi} 之间")
    if any(type(v) is not bool for v in result["tasks"].values()):
        raise ValueError("任务开关必须为布尔值")
    if any(type(result[k]) is not bool for k in ("preserve_tradable", "preserve_steam_tradable")):
        raise ValueError("物品保护总开关必须为布尔值")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1000 for v in result["weights"].values()):
        raise ValueError("装备权重必须在 0–1000 之间")
    if not isinstance(result["protected_equipment"], list) or any(type(v) is not int or v < 0 for v in result["protected_equipment"]):
        raise ValueError("保护装备必须为物品编号列表")
    if result["synth_max_quality"] not in QUALITIES:
        raise ValueError("无效的合成品质上限")
    if not isinstance(result['gongfa_preferred'], list) or any(type(v) is not int or v <= 0 for v in result['gongfa_preferred']):
        raise ValueError('优先功法必须为正整数编号列表')
    if not isinstance(result['resource_pack_materials'], list) or any(type(v) is not int or v <= 0 for v in result['resource_pack_materials']):
        raise ValueError('打包原料必须为正整数编号列表')
    if not isinstance(result['partner_target'], str) or (result['partner_target'] and (not result['partner_target'].isascii() or not result['partner_target'].isdigit() or len(result['partner_target']) > 20)):
        raise ValueError('道侣编号须为最多20位数字字符串')
    if not isinstance(result['mp_event_option'], str) or len(result['mp_event_option']) > 64:
        raise ValueError('秘境选项编号须为不超过64字的字符串')
    stage = result["idle_stage"]
    if not isinstance(stage, str) or (stage != "auto" and (len(stage.split("_")) != 3 or not all(x.isdigit() for x in stage.split("_")))):
        raise ValueError("挂机关卡格式为 auto 或 难度_层级_关卡")
    # Migrate the old two-threshold settings without lowering the user's effective goal.
    version = raw.get('breakthrough_settings_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError('突破设置版本无效')
    if version < 2 and result['breakthrough_auto_raise']:
        result['min_breakthrough_rate'] = max(result['min_breakthrough_rate'], raw.get('breakthrough_target_rate', 0))
    result['breakthrough_target_rate'] = result['min_breakthrough_rate']  # legacy alias
    result['breakthrough_settings_version'] = 2
    return result


