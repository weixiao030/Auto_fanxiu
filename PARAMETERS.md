# 配置参数（0.46）

下表来自发布源码默认值，不包含开发者的实际配置。升级保留已有设置；在网页修改单字段会与服务端最新策略合并。任务开关不绕过解锁、资源、固定锁和保护条件。

`breakthrough_target_rate` 与兼容键 `min_breakthrough_rate` 表示同一目标，网页以百分数显示、内部使用 0–1。`mp_escape_hp` 只在原生仍支持战斗逃脱时显示。

| 配置键 | 含义 | 首次默认值 | 可选范围 |
| --- | --- | --- | --- |
| `preserve_steam_tradable` | 只保护 Steam 可上架物品 | 开启 |  |
| `preserve_tradable` | 按分类品质保留 | 关闭 |  |
| `manual_locks` | 固定锁 | `[]` |  |
| `equip_use_weights` | 使用自定义属性权重（默认关闭） | 关闭 |  |
| `equip_keep_weapon_type` | 保持当前武器类型 | 开启 |  |
| `inventory_auto_refresh` | 自动刷新背包 | 开启 |  |
| `inventory_refresh_seconds` | 背包刷新间隔（秒） | `60` | 5–3600 |
| `allow_game_restart` | 允许重开游戏（排队期间保持关闭） | 关闭 |  |
| `auto_reconnect` | 连接恢复后自动继续任务 | 开启 |  |
| `reconnect_delay_seconds` | 断线等待后重试（秒） | `60` | 15–600 |
| `reconnect_max_attempts` | 最多恢复次数（0持续重试） | `0` | 0–100 |
| `auto_steam_update` | 通过Steam自动更新游戏 | 关闭 |  |
| `steam_update_interval` | Steam更新检查间隔（秒） | `1800` | 300–86400 |
| `interval` | 全局操作间隔（秒） | `3` |  |
| `reserve_wuxing` | 悟性保留 | `0` |  |
| `min_breakthrough_rate` | 突破目标成功率（兼容旧键） | `0.545` |  |
| `challenge_retry_seconds` | 挑战失败等待（秒） | `180` |  |
| `upgrade_level_gap` | 装备强化等级差 | `0` |  |
| `upgrade_reserve` | 强化额外材料保留 | `0` |  |
| `equip_min_gain` | 权重换装最低提升比例 | `0.02` |  |
| `idle_stage` | 挂机关卡 | `"auto"` |  |
| `stop_at_level` | 停止等级，0不限 | `0` |  |
| `protected_equipment` | 兼容旧版的保护装备编号 | `[]` |  |
| `synth_max_quality` | 装备合成品质上限 | `"treasure"` |  |
| `resource_pack_size` | 每包产出数量 | `"4"` | 4：4份（原料成本5）；20：20份（原料成本25）；100：100份（原料成本120） |
| `resource_pack_reserve` | 每种可交易原料保留数量 | `100` | 0–10000000 |
| `resource_pack_batch` | 每次最多打包数量 | `1` | 1–30 |
| `resource_pack_materials` | 仅打包这些原料编号（空为全部） | `[]` | ids |
| `world_interval` | 世界探索间隔（秒） | `15` | 5–3600 |
| `world_daily_limit` | 世界每日探索上限 | `50` | 0–1000 |
| `world_point_limit` | 保留地图坐标上限 | `20` | 1–20 |
| `world_use_rumor` | 免费次数后使用传闻 | 开启 |  |
| `world_use_mirror` | 允许使用窥真镜嗅探 | 开启 |  |
| `world_prop_reserve` | 探索道具保留数量 | `1` | 0–10000 |
| `world_mirror_target` | 嗅探目标 | `"auto"` | auto：自动按成长缺口；herb：灵草；material：材料；relic：遗迹；stronghold：据点；spring：灵泉；forge：锻炉 |
| `world_relics` | 允许探索带陷阱风险的遗迹 | 开启 |  |
| `world_prune` | 地图满时清理失效坐标 | 开启 |  |
| `breakthrough_auto_raise` | 自动用丹药提高成功率 | 开启 |  |
| `breakthrough_auto_find` | 自动寻找缺少的材料 | 开启 |  |
| `breakthrough_auto_craft` | 自动炼制突破丹 | 开启 |  |
| `breakthrough_auto_use` | 满修为后自动服用突破丹 | 开启 |  |
| `breakthrough_target_rate` | 联动目标成功率（%） | `0.545` | 0–1 |
| `breakthrough_material_reserve` | 突破炼丹每种原料额外保留 | `0` | 0–100000 |
| `breakthrough_settings_version` | breakthrough_settings_version | `2` |  |
| `alchemy_reserve` | 炼丹每种材料保留数量 | `5` | 0–100000 |
| `alchemy_batch` | 每次炼丹数量 | `1` | 1–100 |
| `pill_reserve` | 每种丹药保留数量 | `0` | 0–10000 |
| `gongfa_preferred` | 优先主动功法编号（逗号分隔） | `[]` | ids |
| `gongfa_accelerate_reserve` | 功法加速页保留数量 | `2` | 0–10000 |
| `pill_timed_buffs` | 允许使用限时增益丹药 | 开启 |  |
| `growth_linked` | 自动联动成长与补料 | 开启 |  |
| `refine_recycle_obsolete` | 回收不再用于后续突破的旧材料 | 开启 |  |
| `refine_obsolete_reserve` | 每种旧突破材料保留数量 | `0` | 0–100000 |
| `refine_surplus_without_demand` | 无缺料目标时仍允许盈余炼化 | 关闭 |  |
| `resource_realm_use_token` | 免费次数后允许使用资源秘境令 | 开启 |  |
| `resource_realm_token_reserve` | 资源秘境令保留数量 | `1` | 0–10000 |
| `refine_reserve` | 炼化每种材料保留数量 | `0` | 0–100000 |
| `refine_max_items` | 每次炼化最多投入件数 | `50` | 1–10000 |
| `refine_target_level` | 炼化目标等级 | `1` | 1–15 |
| `refine_preferred_id` | 炼化偏好奖励编号（0不指定） | `0` | 0–999999 |
| `realm_allow_danger` | 允许挑战危险评级的突破秘境 | 开启 |  |
| `realm_retry_seconds` | 突破秘境失败等待（秒） | `600` | 60–86400 |
| `material_synth_reserve` | 每种合成原料保留数量 | `2` | 0–100000 |
| `material_synth_batch` | 每次最多合成份数 | `5` | 1–100 |
| `material_synth_demand_only` | 仅补齐穿戴装备强化缺口 | 开启 |  |
| `furnace_min_exp` | 经验池达到多少再领取 | `1` | 1–100000000 |
| `home_reserve` | 迁居令保留数量 | `1` | 0–10000 |
| `home_min_gain` | 洞府评分最少提升（%） | `5` | 0–1000 |
| `home_priority` | 洞府增益偏好 | `"growth"` | balanced：综合收益；growth：修为成长；combat：战斗属性；loot：探索收获 |
| `social_interval` | 道侣同步间隔（秒） | `120` | 30–3600 |
| `partner_target` | 指定道侣好友编号（留空不结缘） | `""` | steamid |
| `partner_auto_invite` | 自动向指定编号发邀请 | 关闭 |  |
| `partner_auto_accept` | 自动接受指定编号的邀请 | 关闭 |  |
| `partner_practice_limit` | 每日最多双修次数 | `10` | 0–100 |
| `partner_rescue_mode` | 解救方式 | `"talisman_first"` | talisman：仅脱身符；battle：战斗解救；talisman_first：先符后战斗 |
| `rescue_prop_reserve` | 解救后脱身符保留数量 | `1` | 0–10000 |
| `pvp_assessment` | 抓捕与占领战力门槛 | `"advantage"` | crush：仅碾压；advantage：碾压或优势；close：允许相近 |
| `capture_daily_limit` | 每日最多抓捕尝试 | `3` | 0–100 |
| `occupy_daily_limit` | 每日最多占领尝试 | `3` | 0–100 |
| `pvp_max_injury` | 允许参战的最大伤势层数 | `0` | 0–100 |
| `pvp_retry_seconds` | 同一目标失败等待（秒） | `900` | 60–86400 |
| `occupy_min_gain` | 占领洞府最少提升（%） | `5` | 0–1000 |
| `bounty_interval` | 悬赏同步间隔（秒） | `180` | 30–3600 |
| `bounty_daily_limit` | 每日最多悬赏挑战尝试 | `5` | 0–100 |
| `bounty_allow_players` | 允许挑战玩家悬赏 | 开启 |  |
| `bounty_assessment` | 悬赏战力门槛 | `"advantage"` | crush：仅碾压；advantage：碾压或优势；close：允许相近 |
| `bounty_publish_captured` | 被捕时自动对当前主人发布悬赏 | 关闭 |  |
| `bounty_prop_reserve` | 发布后悬赏令保留数量 | `1` | 0–10000 |
| `escape_mode` | 逃脱方式（普通失败可能延长囚禁） | `"talisman_first"` | talisman_only：仅脱身符；talisman_first：先符后普通尝试；free_only：仅普通尝试 |
| `escape_prop_reserve` | 逃脱后脱身符保留数量 | `0` | 0–10000 |
| `mp_auto_enter` | 自动空载入场（免费优先，钥匙遵守保护） | 关闭 |  |
| `mp_interval` | 秘境状态同步间隔（秒） | `60` | 15–600 |
| `mp_extract_hp` | 生命低于此比例尝试撤离（%） | `40` | 1–100 |
| `mp_escape_hp` | 战斗生命低于此比例尝试逃脱（%） | `25` | 1–100 |
| `mp_event_option` | 事件选项编号（留空交原游戏策略） | `""` | text |
| `mp_max_seconds` | 入场后最多探索时长（秒） | `900` | 60–7200 |

## 任务开关

| 键（tasks 下） | 任务 | 首次默认 |
| --- | --- | --- |
| `harvest` | 领取挂机掉落 | 开启 |
| `equip` | 择优换装 | 开启 |
| `breakthrough` | 境界突破 | 开启 |
| `idle_select` | 选择刷图关卡 | 开启 |
| `levelup` | 检查升级 | 开启 |
| `collect` | 领取修炼收益 | 开启 |
| `open_pack` | 开启资源箱 | 开启 |
| `gongfa_activate` | 激活功法 | 开启 |
| `gongfa_slots` | 配置主动功法 | 开启 |
| `gongfa` | 功法修炼 | 开启 |
| `gongfa_accelerate` | 功法修炼加速 | 开启 |
| `upgrade` | 强化装备 | 开启 |
| `pill` | 使用成长丹药 | 开启 |
| `alchemy` | 自动炼丹 | 开启 |
| `world_sync` | 世界状态同步 | 开启 |
| `world_events` | 处理探索奇遇 | 开启 |
| `world_harvest` | 世界资源采集 | 开启 |
| `world_points` | 探索据点与灵泉 | 开启 |
| `world_explore` | 世界地图探索 | 开启 |
| `world_prune` | 清理失效坐标 | 开启 |
| `gacha` | 悟性化物 | 开启 |
| `challenge` | 挑战下一关 | 开启 |
| `realm_challenge` | 突破秘境挑战 | 开启 |
| `synth` | 闲置装备合成 | 开启 |
| `refine` | 盈余材料炼化 | 开启 |
| `world_forge` | 世界熔炉炼化 | 开启 |
| `mail` | 领取邮件 | 开启 |
| `material_synth` | 强化材料合成 | 开启 |
| `furnace_absorb` | 领取炉鼎经验 | 开启 |
| `home_relocate` | 择优迁居 | 开启 |
| `social_sync` | 道侣状态同步 | 开启 |
| `slave_escape` | 被捕自动逃脱 | 开启 |
| `partner_practice` | 道侣双修 | 开启 |
| `partner_social` | 道侣定向结缘 | 开启 |
| `partner_rescue` | 道侣解救 | 开启 |
| `player_capture` | 主动抓捕 | 开启 |
| `player_occupy` | 玩家占领 | 开启 |
| `bounty_sync` | 悬赏列表同步 | 开启 |
| `bounty_claim` | 悬赏挑战 | 开启 |
| `bounty_publish` | 被捕悬赏求援 | 开启 |
| `multiplayer_realm` | 多人秘境托管 | 开启 |
| `resource_realm` | 资源秘境补给 | 开启 |
| `resource_pack` | 资源打包 | 关闭 |

## 分类保护与属性权重

两项保护独立、取并集。固定锁永远优先。默认仅开启 Steam 上架保护；分类保护关闭，预选消耗品、功法、时装全部品质，装备与材料不预选。SDK 元数据未知时等待识别。

固定锁键由背包页生成，功法同时包含层数；无需手工拼接。只保护 `marketable=true`，仅 `tradable=true` 可转移不触发 Steam 保护。受保护混合堆叠按原生绑定优先预算使用，不得扣到受保护未绑定份。

自定义权重方案默认关闭。开启后的首次权重：

| 属性键 | 权重 |
| --- | --- |
| `atk` | 1 |
| `hp` | 0.1 |
| `def` | 0.6 |
| `shield` | 0.12 |
| `mp` | 0.05 |
| `mp_regen_per_sec` | 2 |
| `crit_chance` | 1.5 |
| `crit_damage` | 0.3 |
| `attack_speed` | 2 |
| `cdr` | 1.5 |
| `lifesteal` | 2 |
| `dodge_chance` | 1 |
| `combo_chance` | 1 |
| `stun_chance` | 0.7 |
| `counter_chance` | 0.5 |
| `resist_stun` | 0.3 |
