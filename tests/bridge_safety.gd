extends Node
# This fixture contains no game resources, credentials, or network calls.
class TestBridge extends "res://assistant.gd":
	var context = {"info":{}, "minimum_rate":1.0, "maximum_rate":1.0}
	func _breakthrough_context(): return context
	func _native_defeat_notice(): return "服务器确认战败"
	func _pill_useful(pill): return true if int(pill.get("id",0)) == 6001 else super._pill_useful(pill)
	var fake_main
	func _main(): return fake_main

class ContextBridge extends "res://assistant.gd":
	var fake_main
	func _main(): return fake_main

class FakeSteam extends RefCounted:
	signal inventory_definition_update(ids: Array)
	var definition_requests = 0
	var emit_definitions = false
	var definitions_available = true
	var mismatched_id = false
	var properties: Dictionary = {}
	func loadItemDefinitions():
		definition_requests += 1
		if emit_definitions: inventory_definition_update.emit([4004,2705,61603])
		return true
	func getItemDefinitionProperty(_definition, name):
		if name == "itemdefid":
			return {"success":definitions_available and int(_definition) in [4004,2705,61603],"property":str(int(_definition)+1 if mismatched_id else int(_definition))}
		if properties.has(int(_definition)) and properties[int(_definition)].has(name): return properties[int(_definition)][name]
		return {"success":true,"property":"category:material;rarity:common" if name=="tags" else "1" if name in ["tradable","marketable"] else "0"}

class KnownCatalogue extends RefCounted:
	var known = true
	var marketable = true
	func describe(_kind, _id, _layer = -1): return {"steam_trade_known":known,"steam_tradable":marketable}

class FakeQueue extends RefCounted:
	var _queue_ahead = 214
	var _queue_next_at = Time.get_ticks_msec() + 23000
	var _queue_claiming = false
	var _queue_token = "fixture-not-a-credential"
	func login_queue_active(): return true
	func login_queue_manual_only(): return false

class FakeCombat extends RefCounted:
	signal battle_ended(result: Dictionary)

class FakeBattle extends RefCounted:
	signal battle_state_changed(active: bool)
	signal dungeon_progress_advanced
	signal toast_requested(message: String)
	signal external_battle_ended(result, context)
	var in_combat = false
	var realtime_combat
	var finished = []
	func finish_external_battle(won, detail, toast): finished.append([won, detail, toast])

class FakeGame extends RefCounted:
	var game_started = true
	var dungeon_status = "available"
	var dungeon_progress = {"cleared_ids":["1_2_7", "2_0_5"]}
	func get_dungeon_status(_key): return dungeon_status
	var inventory = {"bound_items": {"material:1": 10}, "gongfa_pages": {}, "bound_gongfa_pages": {}}
	var character = {"level": 12, "exp_current":0, "equip_slots": [], "wuxing": 25}
	var equipments = {}
	var counts = {1: 10}
	var consumable_counts = {}
	var cave = {"discovered_coords": []}
	var partner = {}
	var captured = false
	var resource_realm = {}
	var dungeon_idle = {"selected":{"difficulty":0,"tier":0,"stage":0}}
	func is_captured_as_slave(): return captured
	func get_cave_furnace_slaves(): return []
	var free_used = 0
	func get_free_explore_used(): return free_used
	var prop_cost = 1
	func get_explore_prop_cost(_mode): return prop_cost
	func tutorial_finished(): return true
	func get_equipment(id): return equipments.get(id)
	func get_material_count(id): return counts.get(id, 0)
	func get_consumable_count(id): return consumable_counts.get(id, 0)
	var storage = {}
	var needs = true
	func get_storage_type_pages(kind): return storage.get(kind, [])
	var guaranteed = false
	var failure_bonus = 0.0
	func first_breakthrough_guaranteed(): return guaranteed
	func get_breakthrough_failure_bonus(): return failure_bonus
	var disabled_features: Array = []
	func is_feature_unlocked(feature): return not feature in disabled_features
	func needs_breakthrough(): return needs

class OrderedApi extends RefCounted:
	var pending_count = 1
	var gameplay_pending = false
	func has_pending_gameplay_request(): return gameplay_pending

class FakeApi extends RefCounted:
	var pending_count = 0
	var dungeon_start_pending = false
	var calls = []
	var applied = 0
	var dungeon_reply = {}
	var dungeon_ok = false
	var dungeon_defer = false
	var dungeon_callback: Callable
	var resume_reply = {}
	var resume_ok = true
	var resume_defer = false
	var resume_callback: Callable
	func dungeon(cb, action, d, t, s, battle_id="", _operation=""):
		calls.append(["dungeon",action,d,t,s,battle_id])
		dungeon_callback=cb
		if not dungeon_defer: cb.call(dungeon_reply,dungeon_ok)
	func combat_resume(cb):
		calls.append(["combat_resume"])
		resume_callback=cb
		if not resume_defer: cb.call(resume_reply,resume_ok)
	var network_blocked=false
	func is_network_blocked(): return network_blocked
	func is_client_update_blocked(): return false
	func equip(_cb, _action, id, _slot): calls.append(["equip", id])
	func equipment_upgrade(_cb, id, _confirm): calls.append(["upgrade", id])
	func synth_upgrade_material(_cb, id, count): calls.append(["material_synth", id, count])
	func synth(_cb, _kind, ids): calls.append(["synth", ids])
	func storage(_cb, action, params): calls.append(["storage", action, params])
	func open_consumable(_cb, id, _overflow, count, binding): calls.append(["open_pack", id, count, binding])
	func alchemy(_cb, action, pid, index, count, request, binding): calls.append(["alchemy", action, pid, index, count, request, binding])
	func breakthrough(_cb): calls.append(["breakthrough"])
	func cave_explore(cb, options):
		calls.append(["explore", options])
		cb.call({"cave_result":{"success":true}}, true)
	func cave_world_delete(_cb, marker): calls.append(["delete", marker])
	func cave_world_harvest(_cb, marker): calls.append(["world_harvest", marker])
	func cave_world_point_action(_cb, marker, choice): calls.append(["point", marker, choice])
	func gacha(_cb, count): calls.append(["gacha", count])
	func gongfa(_cb, action, gid): calls.append(["gongfa", action, gid])
	func apply_deferred_response(_response): applied += 1
	func partner(_cb, action, params): calls.append(["partner", action, params])
	func make_operation_id(_name): return "operation-id"
	func cave_slave_escape(_cb): calls.append(["escape"])
	func cave_slave_escape_talisman(_cb): calls.append(["escape_talisman"])
	func cave_bounty_claim(_cb, event, action="start", battle="", result=""):
		calls.append(["bounty", event, action, battle, result])

	func refine(cb, mats, level, preference):
		calls.append(["refine",mats,level,preference]);cb.call({"refine":{"success":true}},true)
	func cave_world_forge(cb, marker, mats, level, preference):
		calls.append(["world_forge",marker,mats,level,preference]);cb.call({"cave_result":{"success":true}},true)
	func resource_realm(cb, action, params):
		calls.append(["resource_realm",action,params]);cb.call({"resource_realm":{"success":true}},true)

class FakeRealmChecks extends RefCounted:
	var jobs = {}
	func watch(channel, id, enabled):
		if enabled: jobs[channel] = id
class FakeRealmTimer extends RefCounted:
	var seconds = 0.0
	func start(value): seconds = value
class FakeRealmPreparation extends RefCounted:
	var visible = false
	var _pending = false
	var data = {}
	var _result_checks = FakeRealmChecks.new()
	var _state_timer = FakeRealmTimer.new()
	func open_prepare(_resume): visible = true; _pending = true
	func resume_admission(answer): visible = true; data.active = answer
class FakeRealmView extends RefCounted:
	var data = {}
	var entry_id = "entry"
	var _combat_resources = {}
	var _received_tick = 0
	var _stale = false
	var _command_pending = false
	var _command_watch = ""
	var _queued_intent = {}
	var _operation_query = {}
	var _battle_id = "battle"
	var calls = []
	func _now(): return int(data.get("panel", {}).get("server_time", 0)) + maxi(0, Time.get_ticks_msec() - _received_tick)
	func _command(action, params):
		calls.append([action, params]); _operation_query = {"request_id":"native-ticket"}
class FakeRealmMode extends RefCounted:
	var active = true
	var _running_id = "entry"
	var view = FakeRealmView.new()
	var preparation = FakeRealmPreparation.new()
	var resumed = []
	func show_realm(): active = true;view._stale = false;view._received_tick = Time.get_ticks_msec()
	func _resumed(response, _ok): resumed.append(response)
	func enter(answer): resumed.append(answer)
class RealmApi extends RefCounted:
	var calls = []
	var reply = {}
	var ok = true
	func multiplayer_realm(cb, action, params):
		calls.append([action, params]); cb.call(reply, ok)

class FakeConfig extends RefCounted:
	var realm_table = []
	var resource_enabled = false
	var synthesis_table = {}
	var world_max_points = 20
	func get_dungeon_reward_node(d, _t, _s): return {"material_ids":[1], "equipment_upgrade_ids":[1073,1073], "herb_ids":[7001], "challenge":{"next_realm_material_ids":[99]}} if d == 1 else {"material_ids":[2], "equipment_upgrade_ids":[1107]}
	func get_exp_needed(_level): return 100
	func get_material_info(id): return {"use_type":"resource_pack" if id == 1 else "pill"}
	func get_equipment_fixed_stats(_slot, level, _quality): return {"atk":level*2,"hp":level*10}
	func get_partner_config(): return {}
	func get_equipment_slots(): return ["weapon"]
	var multiplayer_enabled = false
	func is_multiplayer_realm_suspended(): return not multiplayer_enabled
	func get_value(table, key, fallback):
		if table == "cave_world" and key == "explore": return {"max_discovered_coords":world_max_points}
		if table == "realm" and key == "breakthroughs": return realm_table
		if table == "resource_realm" and key == "enabled": return resource_enabled
		if table == "multiplayer_realm" and key == "enabled": return multiplayer_enabled
		if table == "global_params" and key == "synth_required_count": return 3
		if table == "equipment_upgrade" and key == "synthesis": return synthesis_table
		if table == "items" and key == "materials": return [{"id": 1, "use_type": "resource_pack"}, {"id": 2, "use_type": "pill"}]
		return fallback
	func get_breakthrough_info(_level): return {"base_rate": 0.4, "materials": [{"id": 1, "count": 2}]}
	func is_world_realm_locked(_level): return false
	func get_realm_id_by_level(_level): return 0
	func is_multiplayer_realm_pill_suspended(_pill): return false
	var pill_list: Array = []
	func get_pill_list(): return pill_list if not pill_list.is_empty() else [load("res://scripts/data/pill_data.gd").get_pill_info(6021)]

var failures = []
var checks = 0
var b

func check(condition, message):
	checks += 1
	if not condition: failures.append(message)

func eq(bound):
	return {"id": 1, "bound": bound, "level": 5, "slot": "weapon", "quality": "common"}

func execute(kind, params = {}):
	b.api.calls.clear()
	b.results.clear()
	b.busy = false
	b._execute({"id": "fixture", "kind": kind, "params": params})

func check_challenge_recovery():
	var saved_bridge=b
	b=TestBridge.new()
	b.gm=FakeGame.new(); b.api=FakeApi.new(); b.cfg=FakeConfig.new(); b.steam={"online":true}
	b.fake_main=load("res://fake_main.gd").new(); b.fake_main.battle_flow=FakeBattle.new()
	b.fake_main.battle_flow.realtime_combat=FakeCombat.new()
	b._watch_battle(b.fake_main)
	b.challenge={"id":"retry","kind":"challenge","key":"0_2_3","battle_id":"same-battle","seen":true,"start":Time.get_ticks_msec(),"ended_at":Time.get_ticks_msec()-6000}
	b._watch_challenge_outcome(b.fake_main)
	b.fake_main.battle_flow.realtime_combat.battle_ended.emit({"win":true})
	check(b.challenge.local_action=="complete" and not b.challenge.has("confirmed"),"local win was treated as server acknowledgement")
	b._check_challenge()
	check(b.api.calls==[["dungeon","complete",0,2,3,"same-battle"]],"429 recovery did not retry the original battle and coordinates")
	check(not b.challenge.has("confirmed"),"failed transport confirmed a dungeon result")
	b._check_challenge()
	check(b.api.calls.size()==1,"dungeon retried before backoff")
	b.challenge.next_retry_at=0
	b.api.dungeon_ok=true; b.api.dungeon_reply={"dungeon":{"success":true,"result":"win","battle_id":"wrong-battle"}}
	b._check_challenge()
	check(not b.challenge.has("confirmed"),"wrong battle ID confirmed settlement")
	b.challenge.next_retry_at=0
	b.api.dungeon_reply={"dungeon":{"success":true,"result":"win","battle_id":"same-battle"}}
	b._check_challenge(); b._check_challenge()
	check(b.challenge.is_empty() and b.results.back().ok,"same-battle server acknowledgement did not finish challenge")
	check(b.api.calls.size()==3 and b.fake_main.restored.is_empty(),"settlement retry started a new fight")
	b.results.clear(); b.api.calls.clear(); b.api.dungeon_defer=true
	b.challenge={"id":"old","kind":"challenge","key":"0_0_1","battle_id":"old-battle","local_action":"fail"}
	b._retry_challenge_settlement()
	var late=b.api.dungeon_callback
	b.challenge={"id":"new","battle_id":"new-battle","kind":"challenge"}
	late.call({"dungeon":{"success":true,"result":"lose","battle_id":"old-battle"}},true)
	check(not b.challenge.has("confirmed"),"late callback confirmed a newer fight")
	b.api.calls.clear(); b.api.dungeon_defer=false; b.api.dungeon_ok=false
	b.challenge={"id":"capped","kind":"challenge","key":"0_0_1","battle_id":"capped-battle","local_action":"fail","seen":true,"start":Time.get_ticks_msec(),"ended_at":Time.get_ticks_msec()-6000}
	for attempt in range(4):
		b.challenge.next_retry_at=0
		b._check_challenge()
	check(b.api.calls.size()==3 and b.challenge.settlement_retries==3,"dungeon settlement exceeded three retries")
	b._retry_challenge_settlement()
	check(b.api.calls.size()==3,"direct retry bypassed settlement cap")
	b.challenge.ended_at=Time.get_ticks_msec()-121000
	b._check_challenge()
	check(b.challenge.is_empty() and b.results.back().data.unconfirmed,"exhausted settlement manufactured a result")
	b.api.calls.clear(); b.api.resume_ok=false
	b.native_recovery={"state":"pending"}
	b._recover_native_challenge()
	check(not b.busy and b.native_recovery.state=="pending","failed resume kept a nonexistent action busy")
	b._recover_native_challenge()
	check(b.api.calls.size()==1,"resume failure ignored backoff")
	b.api.resume_ok=true; b.native_recovery.next_at=0
	b._recover_native_challenge()
	check(not b.busy and b.native_recovery.state=="done","authoritative empty battle did not release recovery")
	for empty_reply in [{},{"battle":null},{"battle":{}}]:
		b.native_recovery={"state":"pending"}; b.api.resume_reply=empty_reply
		b._recover_native_challenge()
		check(b.native_recovery.state=="done" and not b.busy,"native null/empty no-battle response blocked recovery")
	b.native_recovery={"state":"pending"}; b.api.network_blocked=true; b.api.calls.clear()
	b._recover_native_challenge()
	check(not b.busy and b.api.calls.is_empty(),"offline recovery prevented safe idle bridge updates")
	b.api.network_blocked=false
	execute("world_explore")
	check(b.api.calls.is_empty() and b.results.back().detail.contains("核对"),"idle recovery let a queued command reach the native API")
	# A native battle that begins while resume is in flight wins the race.
	b.api.resume_defer=true; b.api.calls.clear(); b.native_recovery={"state":"pending"}
	b._recover_native_challenge()
	b.fake_main.battle_flow.in_combat=true
	b.api.resume_callback.call({},true)
	check(b.native_recovery.state=="pending","concurrent native combat was ignored by resume callback")
	b.fake_main.battle_flow.in_combat=false; b.api.resume_defer=false
	for reply in [{"battle":[]},{"battle":{"battle_id":"b"},"context":[]},{"battle":{"battle_id":"b"},"context":{"kind":"bounty"}},{"battle":{"battle_id":"b"},"context":{"kind":"dungeon","dungeon_node":[0,1.5,2]}},{"battle":{"battle_id":"b"},"context":{"kind":"dungeon","dungeon_node":[0,-1,2]}},{"battle":{"battle_id":"b"},"context":{"kind":"dungeon","dungeon_node":[0,"x",2]}}]:
		b.native_recovery={"state":"pending"}; b.api.resume_reply=reply
		b._recover_native_challenge()
		check(b.native_recovery.state=="blocked" and not b.busy,"invalid/unknown recovery payload released automatic work")
	check(b.fake_main.restored.is_empty(),"invalid recovery payload replayed a fight")
	b.native_recovery={"state":"pending"}; b.api.calls.clear()
	b.api.resume_reply={"battle":{"battle_id":"resume-battle"},"context":{"kind":"dungeon","dungeon_node":[0.0,2.0,3.0]}}
	b._recover_native_challenge()
	check(b.native_recovery.state=="replaying" and b.busy,"valid resumed dungeon released automation before settlement")
	check(b.challenge.battle_id=="resume-battle" and b.challenge.key=="0_2_3","resume changed battle identity or dungeon coordinates")
	check(b.fake_main.dungeon_system.current_battle_id=="resume-battle" and b.fake_main.restored.size()==1,"native resume context was not installed")
	b.fake_main.battle_flow.realtime_combat.battle_ended.emit({"win":false})
	check(b.challenge.local_action=="fail" and not b.challenge.has("confirmed"),"resumed local loss falsely confirmed server settlement")
	b.fake_main.battle_flow.in_combat=false
	b.challenge.ended_at=Time.get_ticks_msec()-6000
	b.api.dungeon_ok=true; b.api.dungeon_reply={"dungeon":{"success":true,"result":"lose","battle_id":"resume-battle"}}
	b._check_challenge(); b._check_challenge()
	check(b.native_recovery.state=="done" and not b.busy and not b.results.back().ok,"confirmed resumed loss did not release recovery")
	check(b.api.calls==[["combat_resume"],["dungeon","fail",0,2,3,"resume-battle"]],"recovery made requests other than resume and same-battle settlement")
	b.fake_main.restore_starts=false; b.native_recovery={"state":"pending"}
	b._recover_native_challenge()
	check(b.native_recovery.state=="blocked" and b.results.back().data.unconfirmed,"failed native replay was marked ready")
	b.fake_main.free(); b.free(); b=saved_bridge

func check_world_cycle():
	var saved_bridge = b
	b = TestBridge.new()
	b.gm = FakeGame.new(); b.api = FakeApi.new(); b.cfg = FakeConfig.new()
	b.steam = {"online":true}; b.fake_main = saved_bridge.fake_main
	b.policy = {"preserve_steam_tradable":false,"preserve_tradable":false,"world_prune":true,"world_point_limit":20,"world_daily_limit":50}
	b.gm.cave = {"discovered_coords":[],"free_explore_limit":1}
	for marker in range(1,20): b.gm.cave.discovered_coords.append({"marker_id":marker,"type":"ordinary"})
	var now_ms = int(Time.get_unix_time_from_system()*1000)
	check(b._world_point_expired({"type":"player","expires_at":now_ms},now_ms),"expiration equality differed from native visibility")
	check(b._world_point_expired({"type":"robot"},now_ms),"missing player expiration differed from native visibility")
	check(not b._world_point_expired({"type":"cultivator","expires_at":now_ms+1000},now_ms),"live player incorrectly expired")
	check(not b._world_point_expired({"type":"ordinary","expires_at":1},now_ms),"ordinary resource treated as expiring player")
	for expired_type in ["player","cultivator","robot"]:
		b.gm.cave.discovered_coords.append({"marker_id":20,"type":expired_type,"expires_at":now_ms-1000})
		var snapshot = b._world_snapshot()
		check(snapshot.point_count==19,"expired "+expired_type+" consumed native map capacity")
		check(snapshot.get("expired_point_count",0)==1,"expired coordinate count missing")
		check(snapshot.points.back().get("expired",false),"expired coordinate not marked for display")
		execute("world_explore")
		check(b.api.calls.size()==1 and b.api.calls[0][0]=="explore","expired coordinate blocked a native free slot")
		execute("world_prune",{"marker_id":20})
		check(b.api.calls.is_empty(),"cleanup ran below the current active capacity")
		b.gm.cave.discovered_coords.pop_back()
	b.gm.cave.discovered_coords[0].type="empty"
	execute("world_prune",{"marker_id":1})
	check(b.api.calls.is_empty(),"stale prune deleted a point after the map had space")
	b.policy.world_point_limit=19
	execute("world_prune",{"marker_id":1})
	check(b.api.calls==[["delete",1]],"latest lower user capacity did not permit cleanup")
	b.policy.world_point_limit=20
	execute("world_prune",{"marker_id":1})
	check(b.api.calls.is_empty(),"raised user capacity did not cancel old cleanup")
	b.cfg.world_max_points=3
	b.gm.cave.discovered_coords=b.gm.cave.discovered_coords.slice(0,3)
	execute("world_prune",{"marker_id":1})
	check(b.api.calls==[["delete",1]],"native capacity was ignored when cleaning a full map")
	execute("world_explore")
	check(b.api.calls.is_empty(),"exploration exceeded native capacity")
	b.policy.world_prune=false
	execute("world_prune",{"marker_id":1})
	check(b.api.calls.is_empty(),"latest cleanup switch did not reject old command")
	b.free(); b=saved_bridge

func check_bound_first_exploration():
	var saved_bridge = b
	b = TestBridge.new()
	b.gm=FakeGame.new(); b.api=FakeApi.new(); b.cfg=FakeConfig.new()
	b.steam={"online":true}; b.steam_inventory=KnownCatalogue.new(); b.fake_main=saved_bridge.fake_main
	b.policy={"preserve_steam_tradable":true,"preserve_tradable":false,"world_use_rumor":true,"world_use_mirror":true,"world_prop_reserve":1}
	b.gm.cave={"discovered_coords":[],"free_explore_limit":0}
	b.gm.prop_cost=3
	b.gm.consumable_counts[4006]=29
	b.gm.inventory.bound_items["consumable:4006"]=28
	var prop=b._world_snapshot().rumor
	check(prop.bound_only_safe and prop.spendable_count==28,"29/28 rumor stock failed bound-first budget")
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.size()==1 and b.api.calls[0][1].get("use_rumor",false),"mixed rumor did not reach native exploration")
	b.gm.consumable_counts[4006]=4; b.gm.inventory.bound_items["consumable:4006"]=3
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.size()==1,"remaining unbound reserve incorrectly required another bound unit")
	b.gm.inventory.bound_items["consumable:4006"]=2
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.is_empty(),"exploration crossed the unbound floor after live stock changed")
	b.gm.inventory.bound_items["consumable:4006"]=3; b.gm.prop_cost=4
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.is_empty(),"increased native exploration cost bypassed bound budget")
	b.gm.prop_cost=3; b.policy.manual_locks=["material:4006"]
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.is_empty(),"fixed lock lost under bound-first deduction")
	b.policy.manual_locks=[]; b.steam_inventory.known=false
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.is_empty(),"unknown Steam definition bypassed exploration waiting")
	b.policy.preserve_steam_tradable=false; b.gm.inventory.bound_items["consumable:4006"]=0
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.size()==1,"disabled protection did not expose ordinary total stock")
	b.policy.preserve_steam_tradable=true; b.steam_inventory.known=true; b.steam_inventory.marketable=false
	execute("world_explore",{"use_rumor":true})
	check(b.api.calls.size()==1,"non-marketable unbound rumor was incorrectly protected")
	b.steam_inventory.marketable=true
	b.gm.consumable_counts[4003]=4; b.gm.inventory.bound_items["consumable:4003"]=3
	execute("world_explore",{"use_mirror":true})
	check(b.api.calls.size()==1 and b.api.calls[0][1].get("use_mirror",false),"mirror failed identical bound-first contract")
	# Binding under the material alias must not authorize consumable deduction.
	b.gm.inventory.bound_items["consumable:4003"]=0; b.gm.inventory.bound_items["material:4003"]=99
	execute("world_explore",{"use_mirror":true})
	check(b.api.calls.is_empty(),"wrong physical pool granted exploration bound stock")
	b.free(); b=saved_bridge

func check_growth_receipts():
	var saved_bridge = b
	b = TestBridge.new()
	b.gm = FakeGame.new(); b.api = FakeApi.new(); b.cfg = FakeConfig.new()
	b.policy = {"alchemy_batch":3}
	var flow = load("res://growth_evidence.gd")
	b.gm.counts = {1001:20, 1008:0, 1:10}
	var begin = flow.begin(b, {"kind":"world_forge", "params":{"materials":{"1001":6}}})
	check(begin.requirements.get("material:1001")==6,"forge receipt multiplied physical inputs")
	b.gm.counts[1001]=14; b.gm.counts[1008]=3
	var receipt = flow.finish(b, begin, {"success":true,"rewards":[{"type":"material","material_id":1008,"count":3,"session_token":"must-not-export"}],"identity":"must-not-export"})
	check(receipt.native_success and receipt.before.items["material:1001"]==20 and receipt.after.items["material:1001"]==14,"receipt lost actual input delta")
	check(receipt.outputs=={"material:1008":3} and receipt.after.items["material:1008"]==3,"native output reward not linked to applied stock")
	check(not JSON.stringify(receipt).contains("must-not-export"),"receipt exported unrelated native data")
	var upgrade_equipment=eq(false); upgrade_equipment.id=17; upgrade_equipment.level=2
	b.gm.equipments[17]=upgrade_equipment
	begin=flow.begin(b,{"kind":"upgrade","params":{"item_id":17}})
	check(begin.requirements=={"material:1":2},"upgrade receipt guessed requirements")
	b.gm.counts[1]=8; b.gm.equipments[17].level=3
	receipt=flow.finish(b,begin,{"success":true})
	check(receipt.before.equipment_level==2 and receipt.after.equipment_level==3,"upgrade receipt lost actual level gain")
	check(receipt.before.equipment_id==17 and receipt.after.equipment_id==17,"upgrade receipt changed equipment identity")
	b.gm.storage={"herb":[{"items":[{"key":"herb:7001","count":100}]}],"pill":[{"items":[{"key":"pill:6001","count":0}]}]}
	begin=flow.begin(b,{"kind":"alchemy","params":{"pill_id":6001,"recipe_index":0,"count":2}})
	check(begin.requirements=={"material:1":6,"herb:7001":20},"alchemy receipt failed to derive batch requirements")
	b.gm.storage.pill[0].items[0].count=2
	receipt=flow.finish(b,begin,{"success":true,"rewards":[]})
	check(receipt.outputs=={"pill:6001":2},"alchemy output not read from confirmed inventory")
	b.context.info={"materials":[{"kind":"material","id":1008,"count":3}]}
	begin=flow.begin(b,{"kind":"breakthrough","params":{}})
	check(begin.requirements=={"material:1008":3},"breakthrough receipt ignored native requirements")
	b.gm.counts[1008]=0; b.gm.character.level+=1
	receipt=flow.finish(b,begin,{"success":true})
	check(receipt.after.level==receipt.before.level+1,"breakthrough receipt lost applied level gain")
	check(flow.begin(b,{"kind":"collect","params":{}}).is_empty(),"unsupported mutation manufactured a receipt")
	b.free(); b=saved_bridge

func check_multiplayer_lifecycle():
	var c = ContextBridge.new()
	c.cfg = FakeConfig.new();c.cfg.multiplayer_enabled = true
	c.fake_main = load("res://fake_main.gd").new()
	var mode = FakeRealmMode.new();c.fake_main._realm_mode = mode
	c.api = RealmApi.new()
	var view = mode.view
	c.gm = FakeGame.new();c.steam = {"online":true};c.api = FakeApi.new()
	c._execute({"id":"old-plan","kind":"collect","params":{}})
	check(c.api.calls.is_empty() and not c.results.back().ok, "old gameplay plan interrupted an active native realm")
	c.api = RealmApi.new()
	view._received_tick = Time.get_ticks_msec() - 10000
	view.data = {"state":"exploring", "panel":{"server_time":2000000,"resources":{"hp":80,"max_hp":100},"can_extract":true}}
	var sample = c._multiplayer_snapshot(c.fake_main)
	check(not sample.stale and sample.hp_known and sample.hp_percent == 80, "10-second native realm snapshot was incorrectly rejected")
	view._received_tick = Time.get_ticks_msec() - 35000
	check(c._multiplayer_snapshot(c.fake_main).stale, "expired native realm snapshot allowed automation")
	view._received_tick = Time.get_ticks_msec()
	view.data.state = "in_combat"
	sample = c._multiplayer_snapshot(c.fake_main)
	check(not sample.hp_known and sample.hp_percent == null, "unknown battle HP was treated as zero")
	c._execute_multiplayer({"id":"hp","params":{"action":"extract","entry_id":"entry"}})
	check(view.calls.is_empty(), "unknown HP triggered low-health extraction")
	c.mp_observed_at = Time.get_ticks_msec() - 901000
	sample = c._multiplayer_snapshot(c.fake_main)
	check(sample.elapsed_seconds >= 900 and sample.elapsed_source == "observed", "missing entry timestamp disabled duration limit")
	c._execute_multiplayer({"id":"time","params":{"action":"extract","entry_id":"entry"}})
	check(view.calls.size() == 1, "duration limit depended on known HP")
	c.realm_command.clear();view.calls.clear()
	view.data.entered_at = 1000000
	sample = c._multiplayer_snapshot(c.fake_main)
	check(sample.elapsed_seconds >= 1000 and sample.elapsed_source == "server", "valid server entry timestamp was ignored")
	mode._running_id = "another";view.entry_id = "another"
	view.data.erase("entered_at")
	sample = c._multiplayer_snapshot(c.fake_main)
	check(sample.elapsed_seconds == 0, "new realm inherited previous duration")
	view.data.state = "choosing"
	view.data.exploration = {"event":{"id":"event","status":"choosing","due_at":view._now()+10000,"options":[{"id":"safe"},{"id":"disabled","disabled":true},{"id":""}]}}
	check(c._multiplayer_snapshot(c.fake_main).event.options == ["safe"], "realm exposed disabled or empty choices")
	view.data.exploration.event.due_at = view._now()-1
	check(c._multiplayer_snapshot(c.fake_main).event.options.is_empty(), "expired realm choice remained actionable")
	mode.active = false;view._stale = true
	c._execute_multiplayer({"id":"resume","params":{"action":"resume","entry_id":"another"}})
	check(mode.active, "hidden realm view was never resumed through native mode")
	mode.active = false;mode._running_id = "";view.entry_id = ""
	mode.preparation.visible = true;mode.preparation.data.active = {"id":"pending","state":"reserving"}
	sample = c._multiplayer_snapshot(c.fake_main)
	check(sample.active and sample.admission_pending and sample.command_pending, "native admission was treated as idle")
	c._execute_multiplayer({"id":"duplicate","params":{"action":"enter"}})
	check(c.api.calls.is_empty(), "admission received duplicate enter")
	mode.preparation.visible = false;mode.preparation.data.clear()
	c.api.reply = {"multiplayer_realm":{"success":true,"active":{"id":"existing","state":"exploring"}}}
	c._execute_multiplayer({"id":"prepare","params":{"action":"prepare"}})
	check(mode.resumed.size() == 1 and c.mp_prepare.is_empty(), "prepare failed to hand existing entry to native resume")
	c.policy = {"mp_auto_enter":true}
	c.mp_prepare = {"available":true,"inventory_ready":true,"realm_key":"realm","free_entry":{"remaining":1}}
	c.mp_prepared_at = Time.get_ticks_msec();c.api.ok = false
	c._execute_multiplayer({"id":"uncertain","params":{"action":"enter","realm_key":"realm"}})
	check(mode.preparation._result_checks.jobs.has("entry") and mode.preparation._state_timer.seconds == 30, "uncertain enter bypassed native confirmation")
	check(c._multiplayer_snapshot(c.fake_main).admission_pending, "uncertain enter allowed another admission before status resolved")
	c.fake_main.free();c.free()

func check_new_native_contracts():
	var server_state = Node.new()
	server_state.name = "ServerState"
	server_state.set_script(load("res://fake_server.gd"))
	get_tree().root.add_child(server_state)
	var c = ContextBridge.new()
	add_child(c)
	c.gm = FakeGame.new()
	c.cfg = FakeConfig.new()
	c.fake_main = b.fake_main
	c.api = OrderedApi.new()
	check(not c._native_gameplay_pending(), "ordered native background read blocked scheduling")
	c.api.gameplay_pending = true
	check(c._native_gameplay_pending(), "native gameplay request did not block scheduling")
	c.api = FakeApi.new()
	c.api.pending_count = 1
	check(c._native_gameplay_pending(), "old native client lost conservative pending fallback")
	c.api.pending_count = 0
	check(not c._native_gameplay_pending(), "old native idle client was blocked")
	c.gm.inventory["fashion_collection"] = {"percent": 12.5, "idle_exp_percent": 5, "limited_count": 1, "private_field": "excluded"}
	c.gm.inventory["activated_fashion_ids"] = [1,2,3]
	var collection = c._fashion_collection_snapshot()
	check(collection.known and collection.activated_count == 3 and collection.percent == 12.5, "native fashion collection summary lost its real bonus")
	check(not collection.has("private_field"), "fashion collection snapshot exposed non-whitelisted state")
	c.gm.inventory.erase("fashion_collection")
	check(not c._fashion_collection_snapshot().known, "unknown collection was presented as a measured zero")
	c.gm.failure_bonus = 0.2
	var context = c._breakthrough_context()
	check(is_equal_approx(context.minimum_rate, 0.6), "native failure bonus was omitted from pill budget")
	check(is_equal_approx(context.failure_bonus, 0.2), "failure bonus was not exposed")
	c.gm.failure_bonus = 0.0
	check(is_equal_approx(c._breakthrough_context().minimum_rate, 0.4), "old failure bonus survived a realm reset")
	c.gm.guaranteed = true
	check(c._breakthrough_context().minimum_rate == 1.0, "first guaranteed breakthrough lost its guarantee")
	c.gm.guaranteed = false
	c.gm.failure_bonus = 1.0
	check(c._breakthrough_context().maximum_rate == 1.0, "probability exceeded 100 percent")
	b.fake_main.auto_pill_ui = {"controller": {"running": true, "in_flight": false, "request_id": "private-id", "pill_id": 6002, "remaining": 3, "status": "WAIT"}}
	var native = c._native_auto_pill_snapshot(b.fake_main)
	check(native.active and not native.has("request_id"), "native pill status leaked receipt or lost active state")
	c.policy = {"pill_timed_buffs": true}
	check(not c._pill_useful({"id": 6002, "effects": [{"type": "timed_buff"}]}), "assistant competed with native automatic pill use")
	b.fake_main.auto_pill_ui = null
	c.gm.character["active_buffs"] = [{"pill_id": 6021, "expires_at": 0}]
	check(not c._pill_useful({"id": 6002, "recipe_group": -1, "effects": [{"type": "timed_buff"}]}), "permanent active buff was treated as expired")
	c.results.clear()
	c.realm_command = {"id": "local", "entry_id": "entry", "action": "choose", "request_id": "ticket", "start": Time.get_ticks_msec()}
	c._observe_realm_command("/api/multiplayer_realm", {"action":"choose", "entry_id":"entry", "request_id":"wrong"}, {"multiplayer_realm":{"success":true}}, true)
	check(c.results.is_empty(), "unrelated realm request confirmed the assistant command")
	c._observe_realm_command("/api/multiplayer_realm", {"action":"choose", "entry_id":"entry", "request_id":"ticket"}, {"multiplayer_realm":{"success":true,"pending":true}}, true)
	check(c.results.is_empty(), "pending realm result counted as success")
	c._observe_realm_command("/api/multiplayer_realm", {"action":"view", "entry_id":"entry", "operation":{"request_id":"ticket"}}, {"multiplayer_realm":{"operation_status":{"status":"confirmed","result":{"accepted":true}}}}, true)
	check(c.results.size()==1 and c.results[0].ok and c.realm_command.is_empty(), "native operation receipt did not finish the original command")
	c.results.clear()
	c.realm_command = {"id": "local", "entry_id": "entry", "action": "choose", "request_id": "ticket", "start": Time.get_ticks_msec()}
	c._observe_realm_command("/api/multiplayer_realm", {"action":"view", "entry_id":"entry", "operation":{"request_id":"ticket"}}, {"multiplayer_realm":{"operation_status":{"status":"superseded"}}}, true)
	check(c.results.size()==1 and not c.results[0].ok, "superseded operation counted as success")
	c.free()
	server_state.free()

func _ready():
	await get_tree().process_frame
	check(load("res://inventory.gd") != null, "inventory reader did not parse")
	b = TestBridge.new()
	add_child(b)
	b.gm = FakeGame.new()
	b.api = FakeApi.new()
	b.cfg = FakeConfig.new()
	b.steam = {"online": true}
	b.policy={"preserve_steam_tradable":false,"preserve_tradable":true}
	b.fake_main = Node.new()
	b.fake_main.set_meta("unused", true)
	# Native Object properties cannot be added; use a script for the battle fixture.
	b.fake_main.set_script(load("res://fake_main.gd"))
	b.gm.consumable_counts[4006] = 4
	b.gm.inventory.bound_items["consumable:4006"] = 4
	check(b._bound_count("material",4006)==4,"bound consumable alias not read")
	check(b._requirements_bound_safe([{"kind":"material","id":4006,"count":1}]),"fully bound exploration prop rejected")
	var binding_view = b._binding_snapshot({"material:4006":4})
	check(binding_view.get("material:4006",0)==4,"planner snapshot lost consumable binding")
	b.gm.consumable_counts[4006] = 5
	check(b._requirements_bound_safe([{"kind":"material","id":4006,"count":1}]),"mixed consumable bound budget rejected")
	check(not b._requirements_bound_safe([{"kind":"material","id":4006,"count":5}]),"mixed consumable crossed unbound floor")
	b.gm.inventory.bound_items["material:4006"] = 999
	check(b._bound_count("material",4006)==4,"stale material binding counted toward consumables")
	b.gm.counts[4006] = 2
	check(b._bound_count("material",4006)==6,"separate material and consumable pools not clamped")
	b.gm.consumable_counts[4006] = 0
	check(b._bound_count("material",4006)==2,"stale consumable binding counted toward materials")
	b.policy={"manual_locks":["material:4006"]}
	check(not b._requirements_bound_safe([{"kind":"material","id":4006,"count":1}]),"fixed lock lost after binding alias")
	b.policy={"preserve_steam_tradable":false,"preserve_tradable":true}
	b.gm.consumable_counts.clear()
	b.gm.counts.erase(4006)
	b.gm.inventory.bound_items.erase("material:4006")
	b.gm.inventory.bound_items.erase("consumable:4006")

	for flag in [false, null]:
		b.gm.equipments = {1: eq(flag)}
		execute("equip", {"item_id": 1, "slot_idx": 0})
		check(b.api.calls.is_empty(), "tradable/unknown equipment reached equip")
		execute("upgrade", {"item_id": 1})
		check(b.api.calls.is_empty(), "tradable/unknown equipment reached upgrade")
	b.gm.equipments = {1: eq(true), 2: eq(true), 3: eq(false)}
	execute("synth", {"item_ids": [1, 2, 3]})
	check(b.api.calls.is_empty(), "mixed equipment reached synth")
	b.gm.equipments[3] = eq(true)
	execute("synth", {"item_ids": [1, 1, 2]})
	check(b.api.calls.is_empty(), "duplicate IDs reached synth")
	execute("synth", {"item_ids": [1, 2, 3]})
	check(b.api.calls.size() == 1, "valid bound synth rejected")
	b.gm.character.equip_slots = [1]
	execute("synth", {"item_ids": [1, 2, 3]})
	check(b.api.calls.is_empty(), "equipped item reached synth")
	b.gm.counts[1] = 11
	execute("breakthrough")
	check(b.api.calls.size()==1, "bound-first mixed material rejected for breakthrough")
	execute("upgrade", {"item_id": 1})
	check(b.api.calls.size()==1, "bound-first mixed material rejected for upgrade")
	b.gm.counts[1] = 10
	check(not b._requirements_bound_safe([{ "id": 1, "count": 6 }, { "id": 1, "count": 6 }]), "duplicate requirements bypassed count")
	check(not b._requirements_bound_safe([{ "id": 0, "count": 1 }]), "unknown requirement accepted")
	check(b._requirements_bound_safe([{ "id": 1, "count": 6 }]), "valid bound material rejected")
	b.gm.inventory.bound_items.clear()
	execute("open_pack", {"material_id": 1})
	check(b.api.calls.is_empty(), "stale box command consumed tradable stock")
	b.gm.inventory.bound_items["material:1"] = 1
	execute("open_pack", {"material_id": 1})
	check(b.api.calls == [["open_pack", 1, 1, 1]], "box operation did not explicitly select bound stock")
	b.gm.inventory.bound_items["material:2"] = 1
	execute("open_pack", {"material_id": 2})
	check(b.api.calls.is_empty(), "arbitrary consumable accepted as a box")
	b.gm.inventory.gongfa_pages = {"6": {"2": 2}}
	b.gm.inventory.bound_gongfa_pages = {"6": {"2": 1}}
	check(b._gongfa_bound_safe(6, 2), "bound-first mixed pages rejected")
	b.gm.inventory.bound_gongfa_pages["6"]["2"]=0
	check(not b._gongfa_bound_safe(6, 2), "unbound protected page consumed")
	check(b._gongfa_bound_safe(6, 2, true), "resume without page consumption rejected")
	execute("gacha", {"count": 10})
	check(b.api.calls == [["gacha", 5]], "stale exploration command exceeded resource reserve")
	b.gm.character.level = 7
	execute("gacha", {"count": 10})
	check(b.api.calls == [["gacha", 1]], "stale batch request ignored native level unlock")
	b.gm.character.level = 12
	b.fake_main.batch_limit = 2
	execute("gacha", {"count": 10})
	check(b.api.calls == [["gacha", 2]], "native batch limit was not rechecked at execution")
	b.fake_main.batch_limit = 15
	for kind in ["equip", "upgrade", "breakthrough", "gacha", "gongfa", "open_pack", "synth", "collect", "levelup", "harvest"]:
		b._callback({}, true, {"id": "callback", "kind": kind})
		check(not b.results.back().ok, "empty result reported success for " + kind)
	b._callback({"equip": {"success": true}}, true, {"id": "ok", "kind": "equip"})
	check(b.results.back().ok, "explicit result rejected")
	b._callback({"character": {"level": 13}, "breakthrough": {"success": true}}, true, {"id": "ok", "kind": "breakthrough"})
	check(b.api.applied == 1, "deferred breakthrough was not applied")
	b.policy = {"preserve_steam_tradable":false,"preserve_tradable": false}
	b.gm.equipments = {1: eq(false), 2: eq(false), 3: eq(false)}
	b.gm.character.equip_slots = [-1]
	execute("equip", {"item_id": 1, "slot_idx": 0})
	check(b.api.calls.size() == 1, "protection off did not allow tradable equipment")
	execute("synth", {"item_ids": [1, 2, 3]})
	check(b.api.calls.size() == 1, "protection off did not allow tradable synth")
	b.gm.equipments[1]["locked"] = true
	execute("synth", {"item_ids": [1, 2, 3]})
	check(b.api.calls.is_empty(), "locked equipment consumed with protection off")
	b.policy.preserve_tradable = true
	execute("equip", {"item_id": 2, "slot_idx": 0})
	check(b.api.calls.is_empty(), "enabling protection failed to block stale command")

	b._callback({"cave_result": {"success": true, "candidates": [{"quality": "common"}, {"quality": "treasure"}]}}, true, {"id": "point", "kind": "world_points", "params": {"marker_id": 9}})
	check(b.stronghold_choices.has("9"), "stronghold choices were not retained")
	b.gm.cave.discovered_coords = [{"marker_id": 9, "type": "stronghold"}]
	execute("world_points", {"marker_id": 9})
	check(b.api.calls == [["point", 9, 1]], "stronghold did not choose higher quality")
	b.gm.cave.discovered_coords = [{"marker_id": 9, "type": "breakthrough_realm"}]
	execute("world_prune", {"marker_id": 9})
	check(b.api.calls.is_empty(), "pruning deleted a breakthrough realm")
	b.gm.cave.discovered_coords = [{"marker_id": 9, "type": "empty", "is_current": true}]
	execute("world_prune", {"marker_id": 9})
	check(b.api.calls.is_empty(), "pruning deleted the current home")
	b.policy.world_prune = true
	b.policy.world_point_limit = 1
	b.gm.cave.discovered_coords = [{"marker_id": 9, "type": "empty"}]
	execute("world_prune", {"marker_id": 9})
	check(b.api.calls == [["delete", 9]], "safe empty marker not pruned")
	b.policy.erase("world_point_limit")
	b.gm.cave.discovered_coords = [{"marker_id": 9, "type": "herb"}]
	execute("world_harvest", {"marker_id": 9})
	check(b.api.calls == [["world_harvest", 9]], "resource harvest rejected")
	b.gm.counts = {1: 10}; b.gm.inventory.bound_items = {"material:1": 10}
	check(not b._requirements_available([{ "kind": "material", "id": 1, "count": 6 }], 1, 5), "crafting spent the reserve")
	check(b._requirements_available([{ "kind": "material", "id": 1, "count": 5 }], 1, 5), "reserve-safe crafting rejected")
	for kind in ["world_sync", "world_explore", "world_harvest", "world_points", "world_prune", "world_events", "alchemy", "pill", "refine", "gongfa_slots", "gongfa_activate", "mail"]:
		b._callback({}, true, {"id": "callback", "kind": kind})
		check(not b.results.back().ok, "empty expansion result reported success for " + kind)
	check(not b._home_safe({"type": "player", "features": []}), "relocation allowed a player target")
	check(not b._home_safe({"type": "ordinary", "features": [{"revealed": false}]}), "relocation accepted unknown features")
	check(not b._home_safe({"type": "ordinary", "features": [{"is_negative": true}]}), "relocation accepted negative features")
	check(b._home_score([{"type": "atk_bonus", "value": 3}]) > b._home_score([{"type": "drawback_atk", "value": 3, "is_negative": true}]), "negative home scores increased utility")
	b.gm.cave = {"world_id": 1, "world_x": 20, "world_y": 30, "discovered_coords": []}
	check(b._point_is_current({"world_id": 1, "coord_x": 20, "coord_y": 30}), "current coordinate was not protected")
	b.challenge = {"id": "timeout", "start": Time.get_ticks_msec() - 300001, "seen": true, "kind": "realm_challenge"}
	b._check_challenge()
	check(b.challenge.is_empty() and not b.results.back().ok and b.results.back().data.unconfirmed, "unconfirmed realm result did not time out")
	for kind in ["material_synth", "furnace_absorb", "home_relocate"]:
		b._callback({}, true, {"id": "callback", "kind": kind})
		check(not b.results.back().ok, "empty progression result reported success for " + kind)
	b._callback({"cave_result": {"success": true, "event": {"event_id": 1, "type": "aura_fluctuation"}}}, true, {"id": "ordinary-event", "kind": "world_explore"})
	check(b.pending_world_event.is_empty(), "already-settled ordinary event blocked exploration")
	b._callback({"cave_result": {"success": false, "pending_event": {"event_id": 12, "type": "cultivator_help"}}}, true, {"id": "interactive-event", "kind": "world_explore"})
	check(b.pending_world_event.get("event_id") == 12, "interactive pending event was lost on blocked exploration")
	b._callback({"cave_result": {"success": true, "pending_event": {}}}, true, {"id": "sync-event", "kind": "world_sync"})
	check(b.pending_world_event.is_empty(), "authoritative empty sync retained stale event")
	b._set_pending_world_event({"event_id": 13, "type": "senior_cultivator"})
	b._callback({"cave_result": {"success": false, "reason": "事件不存在或已处理"}}, true, {"id": "expired-event", "kind": "world_events"})
	check(b.pending_world_event.is_empty() and not b.results.back().ok, "expired event was retained or falsely reported as success")
	b._set_pending_world_event({"event_id": 14, "type": "cultivator_help"})
	b._callback({"cave_result": {"success": false, "reason": "server busy"}}, false, {"id": "busy-event", "kind": "world_events"})
	check(b.pending_world_event.get("event_id") == 14, "transient failure discarded unresolved event")
	b._callback({"code": "", "error_code": "RATE_LIMITED", "http_code": 429, "retry_after_seconds": 75, "body": "private-fixture", "cave_result": {"success": false, "reason": ""}}, false, {"id": "new-error-code", "kind": "world_events"})
	check(b.results.back().detail == "RATE_LIMITED" and b.results.back().data.failure == {"error_code": "RATE_LIMITED", "http_code": 429, "retry_after_seconds": 75.0}, "new native error_code or Retry-After was lost")
	check(not str(b.results.back()).contains("private-fixture"), "raw response body escaped bridge")
	check(b._failure_detail({"server_error": "transport", "code": "BUSY"}, {"reason": "specific"}, "fallback") == "specific", "business rejection lost priority")
	check(b._failure_detail({"server_error": "transport", "code": "BUSY"}, {}, "fallback") == "transport", "transport reason lost priority")
	check(b._failure_detail({"code": "Authorization: private-fixture", "error_code": "VALID_ERROR"}, {}, "fallback") == "VALID_ERROR", "invalid error code escaped validation")
	check(b._failure_metadata({"code": {"body": "private-fixture"}, "http_code": 200, "retry_after_seconds": INF}).is_empty(), "invalid failure scalars accepted")
	b._set_pending_world_event({"event_id": 0, "type": "cultivator_help"})
	check(b.pending_world_event.is_empty(), "zero event ID accepted")
	b.pending_world_event = {"event_id": 9, "type": "aura_fluctuation"}
	execute("world_events", {"event_id": 9, "action": "close"})
	check(b.api.calls.is_empty(), "ordinary event reached event-action API")
	b.challenge = {"id": "short", "seen": false}
	b._on_battle_state_changed(true)
	b._on_battle_state_changed(false)
	check(b.challenge.seen, "short battle start transition was missed")
	b.challenge = {"id": "server-busy", "seen": false}
	b._dungeon_started({"server_error": "server busy"}, false, "server-busy", null, null)
	check(b.challenge.is_empty() and not b.results.back().ok and b.results.back().detail == "server busy", "dungeon transport error lost its real reason")
	b.challenge = {"id": "rejected", "seen": false}
	b._dungeon_started({"dungeon": {"success": false, "reason": "等级不足"}}, true, "rejected", null, null)
	check(b.challenge.is_empty() and b.results.back().detail == "等级不足", "server rejection was treated as a started battle")
	b.challenge = {"id": "current", "seen": false}
	b._dungeon_started({"server_error": "late"}, false, "previous", null, null)
	check(b.challenge.get("id") == "current", "late dungeon callback changed a new command")
	b.challenge.clear()
	b.fake_main.battle_flow = FakeBattle.new()
	b._watch_battle(b.fake_main)
	b.results.clear()
	b.challenge = {"id": "settling", "start": Time.get_ticks_msec(), "key": "0_0_1", "kind": "challenge", "seen": true}
	b._check_challenge()
	check(not b.challenge.is_empty() and b.results.is_empty(), "stale progress was reported as defeat before settlement confirmation")
	b.fake_main.battle_flow.dungeon_progress_advanced.emit()
	b._check_challenge()
	check(b.challenge.is_empty() and b.results.back().ok, "native server win signal was lost while snapshot lagged")
	b.results.clear()
	b.challenge = {"id": "late-snapshot", "start": Time.get_ticks_msec(), "key": "0_0_1", "kind": "challenge", "seen": true}
	b._check_challenge()
	b.gm.dungeon_status = "cleared"
	b._check_challenge()
	check(b.challenge.is_empty() and b.results.back().ok, "delayed authoritative cleared state was lost")
	b.gm.dungeon_status = "available"
	b.challenge = {"id": "loss", "start": Time.get_ticks_msec(), "key": "0_0_1", "kind": "challenge", "seen": true, "battle_id": "current-battle"}
	b._on_game_request("POST", "/api/dungeon", {}, {"dungeon": {"success": true, "result": "win", "battle_id": "old-battle"}}, true)
	check(not b.challenge.has("confirmed"), "unrelated battle settlement changed current challenge")
	b._on_game_request("POST", "/api/dungeon", {}, {"dungeon": {"success": true, "result": "lose", "battle_id": "current-battle"}}, true)
	b._check_challenge()
	check(b.challenge.is_empty() and not b.results.back().ok and b.results.back().detail.contains("未通关"), "confirmed loss was counted as success")
	b.results.clear()
	b.challenge = {"id":"native-loss","start":Time.get_ticks_msec(),"kind":"challenge","seen":true,"battle_id":"own","key":"0_0_1"}
	b.fake_main.battle_flow.toast_requested.emit("结算失败")
	check(not b.challenge.has("confirmed"),"an error toast was treated as confirmed defeat")
	b.fake_main.battle_flow.toast_requested.emit("服务器确认战败\n原生失败原因")
	b._check_challenge()
	check(b.challenge.is_empty() and not b.results.back().ok and b.results.back().detail.contains("未通关"),"normal-mode native defeat notification was lost")
	b._on_native_battle_notice("服务器确认战败")
	check(b.challenge.is_empty(),"late defeat notice created a phantom challenge")
	b.challenge = {"id": "unknown-settlement", "start": Time.get_ticks_msec(), "ended_at": Time.get_ticks_msec() - 31000, "key": "0_0_1", "kind": "challenge", "seen": true}
	b._check_challenge()
	check(b.challenge.is_empty() and not b.results.back().ok and b.results.back().data.unconfirmed and b.results.back().detail.contains("未确认"), "missing settlement was reported as an authoritative loss or success")
	# JSON.parse_string returns floating point numbers, matching the real HTTP wire.
	var decoded = JSON.parse_string('{"id":"wire-choice","kind":"world_points","params":{"marker_id":26}}')
	b._callback({"cave_result": {"success": true, "candidates": [{"quality": "common"}, {"quality": "treasure"}]}}, true, decoded)
	check(b.stronghold_choices.has("26") and not b.stronghold_choices.has("26.0"), "wire marker number did not normalize")
	b.gm.cave.discovered_coords = [{"marker_id": 26.0, "type": "stronghold"}]
	execute("world_points", decoded.params)
	check(b.api.calls == [["point", 26, 1]], "JSON marker candidate lookup repeated discovery instead of choosing reward")
	b._callback({"cave_result": {"success": true, "reward": {"quality": "treasure"}}}, true, decoded)
	check(not b.stronghold_choices.has("26"), "selected stronghold candidates were retained")
	# Queued work must respect configuration and inventory changes immediately.
	b.policy = {"preserve_steam_tradable":false, "preserve_tradable":false, "synth_max_quality":"common"}
	b.gm.equipments = {1:eq(true), 2:eq(true), 3:eq(true)}
	for eid in b.gm.equipments: b.gm.equipments[eid].id = eid
	b.gm.character.equip_slots = [-1]
	for item in b.gm.equipments.values(): item.quality = "rare"
	execute("synth", {"item_ids":[1,2,3]})
	check(b.api.calls.is_empty(), "stale synthesis exceeded latest quality cap")
	for item in b.gm.equipments.values(): item.quality = "common"
	b.gm.inventory["equipments"] = b.gm.equipments
	execute("synth", {"item_ids":[1,2,3]})
	check(b.api.calls.is_empty(), "synthesis consumed fixed-stat best representative")
	b.gm.equipments[4] = eq(true); b.gm.equipments[4].id = 4; b.gm.equipments[4].level = 6
	execute("synth", {"item_ids":[1,2,3]})
	check(b.api.calls.size() == 1, "non-best synthesis was rejected")
	b.policy.merge({"equip_use_weights":true, "weights":{"atk":1}, "equip_min_gain":0.2})
	b.gm.equipments[1]["stats"] = {"atk":100}
	b.gm.equipments[2]["stats"] = {"atk":110}
	b.gm.character.equip_slots = [1]
	execute("equip", {"item_id":2, "slot_idx":0})
	check(b.api.calls.is_empty(), "stale weighted equipment ignored latest minimum gain")
	b.gm.equipments[2].stats.atk = 130
	execute("equip", {"item_id":2, "slot_idx":0})
	check(b.api.calls.size() == 1, "valid weighted equipment was rejected")
	b.gm.inventory.erase("equipments")
	b.policy = {"preserve_steam_tradable":true, "world_use_mirror":true, "world_daily_limit":50}
	b.gm.cave = {"discovered_coords":[], "free_explore_limit":5}
	b.gm.free_used = 0
	b.pending_world_event.clear()
	b.daily_guard = {"day":b._exploration_day(), "world_explore":0}
	execute("world_explore", {"use_mirror":true, "target_type":"material"})
	check(b.api.calls.size() == 1 and not b.api.calls[0][1].has("use_mirror"), "daily reset still consumed a mirror from a stale plan")
	check(b.results.back().data.exploration_mode == "free", "exploration did not report actual execution mode")
	b.policy.world_daily_limit = 0
	execute("world_explore")
	check(b.api.calls.is_empty(), "exploration ignored latest daily limit")
	b.policy.world_daily_limit = 50
	b.gm.free_used = 5
	execute("world_explore", {"use_mirror":true})
	check(b.api.calls.is_empty(), "protected mixed mirror stock was consumed")
	b.gm.free_used = 0
	b.gm.cave = {"discovered_coords":[]}
	b.daily_guard.clear()
	# Stock arriving after planning must prevent needless consuming operations.
	b.policy = {"preserve_steam_tradable":false, "preserve_tradable":false, "material_synth_reserve":0, "upgrade_reserve":0, "material_synth_demand_only":true}
	b.cfg.synthesis_table = {"chains":[[2,1]], "required_count":5}
	b.gm.counts = {1:2, 2:20}
	b.gm.equipments = {1:eq(true)}; b.gm.character.equip_slots = [1]
	execute("material_synth", {"material_id":2, "count":1})
	check(b.api.calls.is_empty(), "stale material synthesis ignored newly filled upgrade demand")
	b.gm.counts[1] = 1
	execute("material_synth", {"material_id":2, "count":1})
	check(b.api.calls == [["material_synth",2,1]], "one-unit current upgrade deficit was rejected")
	execute("material_synth", {"material_id":2, "count":2})
	check(b.api.calls.is_empty(), "material synthesis exceeded the remaining current deficit")
	b.policy.material_synth_demand_only = false
	execute("material_synth", {"material_id":2, "count":2})
	check(b.api.calls == [["material_synth",2,2]], "explicitly disabled demand-only setting still limited synthesis")
	b.cfg.synthesis_table.clear()
	b.gm.counts = {1:30}
	b.gm.storage = {"pill":[{"items":[{"key":"pill:6001", "count":1}]}], "herb":[{"items":[{"key":"herb:7001", "count":100}]}]}
	execute("alchemy", {"pill_id":6001, "recipe_index":0, "count":1})
	check(b.api.calls.is_empty(), "stale alchemy crafted more while a useful pill already existed")
	b.gm.storage.pill[0].items[0].count = 0
	execute("alchemy", {"pill_id":6001, "recipe_index":0, "count":1})
	check(b.api.calls.size() == 1 and b.api.calls[0][0] == "alchemy", "needed normal pill crafting was rejected")
	b.gm.storage.clear()
	# New social actions refuse stale targets and unknown consumable binding.
	b.policy = {"preserve_steam_tradable":false,"preserve_tradable": true, "partner_target": "123", "partner_auto_accept": true, "partner_auto_invite": true}
	b.gm.partner = {"received_invites": [{"id": 7, "player": {"steamid": "456"}, "expires_at": 9999999999999}]}
	execute("partner_social", {"action": "accept_invite", "target": "123", "invite_id": 7})
	check(b.api.calls.is_empty(), "unconfigured invitation was accepted")
	b.gm.partner.received_invites[0].player.steamid = "123"
	execute("partner_social", {"action": "accept_invite", "target": "123", "invite_id": 7})
	check(b.api.calls.size() == 1 and b.api.calls[0][1] == "accept_invite", "configured invitation rejected")
	execute("partner_social", {"action": "accept_invite", "target": "123", "invite_id": 7})
	check(b.api.calls.is_empty(), "invitation was submitted twice")
	# The native client forbids rescuing a partner held by the current character.
	b.steam["steamid"] = "self-fixture"
	b.gm.partner = {"has_partner":true,"partner":{"steamid":"partner-fixture","furnace":{"capture_id":"partner-capture","master_steamid":"self-fixture","expires_at":9999999999999}}}
	check(b._partner_snapshot().self_is_captor, "partner snapshot missed self captivity")
	b.policy.partner_rescue_mode = "talisman_first"
	for action in ["rescue_talisman", "rescue_start"]:
		execute("partner_rescue", {"action":action,"target":"partner-fixture","capture_id":"partner-capture"})
		check(b.api.calls.is_empty() and not b.results.back().ok, "self rescue reached native consumption or combat")
	b.gm.partner.partner.furnace.master_steamid = "other-fixture"
	check(not b._partner_snapshot().self_is_captor, "another captor was treated as the current player")
	b.steam.erase("steamid")
	b.gm.partner.partner.furnace.master_steamid = ""
	check(not b._partner_snapshot().self_is_captor, "missing identities matched each other")
	b.gm.partner = {}
	b.gm.captured = true
	b.gm.cave.captured_as_slave = {"capture_id": "capture", "attempted_escape": false}
	b.gm.counts[4004] = 3
	b.gm.inventory.bound_items["material:4004"] = 2
	execute("slave_escape", {"capture_id": "capture", "action": "escape_talisman"})
	check(b.api.calls==[["escape_talisman"]], "escape rejected sufficient bound talisman budget")
	execute("slave_escape", {"capture_id": "capture", "action": "escape_free"})
	check(b.api.calls == [["escape"]], "free escape rejected")
	execute("slave_escape", {"capture_id": "capture", "action": "escape_free"})
	check(b.api.calls.is_empty(), "free escape repeated in same captivity")
	b._social_response({"cave_result": {"success": true, "escaped": false}}, true, {"id":"failed-escape", "kind":"slave_escape", "params":{"action":"escape_free"}}, "cave_result")
	check(not b.results.back().ok, "failed escape counted as success")
	execute("multiplayer_realm", {"action": "enter"})
	check(b.api.calls.is_empty(), "suspended multiplayer entry sent a request")
	check(b._occupy_home_safe({"type":"player","features":[]}), "occupied home was always excluded from occupation")
	check(not b._occupy_home_safe({"type":"player","features":[{"revealed":false}]}), "unknown occupied-home features accepted")
	# Owned battles are settled once, using the matching server callback.
	b.external = {"id":"owned", "kind":"bounty_claim", "battle_id":"battle", "start":Time.get_ticks_msec(), "settling":false}
	b.api.calls.clear()
	var owned_context = {"assistant_id":"owned","battle_id":"battle","kind":"bounty","event_id":7}
	b._external_ended({"win":true}, owned_context)
	b._external_ended({"win":true}, owned_context)
	check(b.api.calls.size()==1 and b.api.calls[0][2]=="complete", "battle settlement was submitted twice")
	b._external_settled({"cave_result":{"success":true,"result":"win","battle_id":"wrong"}},true,"previous",{},owned_context)
	check(not b.external.is_empty(), "late callback cleared an active battle")
	b._external_settled({"cave_result":{"success":true,"result":"win","battle_id":"wrong"}},true,"owned",{},owned_context)
	check(b.external.is_empty() and not b.results.back().ok and b.results.back().data.unconfirmed, "mismatched battle was reported as a win")
	b.external = {"id":"win", "kind":"bounty_claim", "battle_id":"battle", "start":Time.get_ticks_msec(), "settling":true}
	b._external_settled({"cave_result":{"success":true,"result":"win","battle_id":"battle"}},true,"win",{},owned_context)
	check(b.results.back().ok and b.results.back().data.won, "server-confirmed win was lost")
	# A rejected settlement waits and resubmits the same battle, never a start.
	b.external = {"id":"limited", "kind":"bounty_claim", "battle_id":"same-battle", "start":Time.get_ticks_msec(), "settling":false}
	var limited_context = {"assistant_id":"limited","battle_id":"same-battle","kind":"bounty","event_id":9}
	b.api.calls.clear()
	b._external_ended({"win":true}, limited_context)
	var results_before = b.results.size()
	var presentations_before = b.fake_main.settlements.size()
	var now = Time.get_ticks_msec()
	b._external_settled({"http_code":429,"retry_after_seconds":7},false,"limited",{"win":true},limited_context)
	check(not b.external.is_empty() and b.results.size()==results_before, "429 stopped automation instead of waiting")
	check(int(b.external.retry_at)>=now+7000, "server Retry-After was ignored")
	check(b.fake_main.settlements.size()==presentations_before, "rejected settlement closed native combat")
	b._check_external()
	check(b.api.calls.size()==1, "settlement retried before backoff expired")
	b.external.retry_at = 1
	b._check_external()
	check(b.api.calls.size()==2 and b.api.calls.back()==["bounty",9,"complete","same-battle","win"], "retry started a new battle or changed its result")
	b._external_ended({"win":true},limited_context)
	check(b.api.calls.size()==2, "late combat signal duplicated a retry")
	b._external_settled({"cave_result":{"success":true,"result":"win","battle_id":"same-battle"}},true,"limited",{"win":true},limited_context)
	check(b.external.is_empty() and b.results.size()==results_before+1 and b.results.back().ok, "retry success did not settle exactly once")
	b._external_settled({"cave_result":{"success":true,"result":"win"}},true,"limited",{"win":true},limited_context)
	check(b.results.size()==results_before+1, "late callback duplicated successful reward acknowledgement")
	b.external={"id":"exhausted","battle_id":"same-battle","start":Time.get_ticks_msec(),"settling":true,"settlement_retries":3}
	b._external_settled({"http_code":429,"retry_after_seconds":7},false,"exhausted",{},limited_context)
	check(b.external.is_empty() and b.results.back().data.unconfirmed, "exhausted retries did not stop safely")
	b.external={"id":"network","battle_id":"same-battle","start":Time.get_ticks_msec(),"settling":true}
	b._external_settled({"http_code":0,"error":"timeout"},false,"network",{},limited_context)
	check(b.external.is_empty() and b.results.back().data.unconfirmed, "ambiguous network failure was resubmitted")
	# Packing uses only tradable resources in the original game: never bypass protection.
	b.policy = {"preserve_steam_tradable":false,"preserve_tradable":true,"resource_pack_size":"4","resource_pack_reserve":100,"resource_pack_batch":2}
	var pack_params = {"kind":"herb","material_id":7001,"size":4,"count":2}
	execute("resource_pack", pack_params)
	check(b.api.calls.is_empty(), "protected tradable resources were packed")
	b.policy.preserve_tradable = false
	execute("resource_pack", pack_params)
	check(b.api.calls == [["storage","pack",{"entries":[{"kind":"herb","id":7001,"size":4,"count":2}],"request_id":"fixture"}]], "resource pack payload differs from native API")
	b.policy.resource_pack_reserve = 106
	execute("resource_pack", pack_params)
	check(b.api.calls.is_empty(), "packing spent reserved resources")
	b.policy.resource_pack_reserve = 100
	for patch in [{"size":20},{"size":7},{"material_id":7777},{"kind":"material"},{"count":0},{"count":-1},{"count":3}]:
		var invalid = pack_params.duplicate()
		invalid.merge(patch, true)
		execute("resource_pack", invalid)
		check(b.api.calls.is_empty(), "invalid pack request accepted: "+str(patch))
	b.policy.resource_pack_batch = 1
	execute("resource_pack", pack_params)
	check(b.api.calls.is_empty(), "pack batch limit ignored")
	b.policy.resource_pack_batch = 2
	b.policy.resource_pack_materials = [7002]
	execute("resource_pack", pack_params)
	check(b.api.calls.is_empty(), "pack material allowlist ignored")
	b.policy.tasks = {"resource_pack":true}
	execute("open_pack", {"material_id":1})
	check(b.api.calls.is_empty(), "automatic packing/unpacking loss loop allowed")
	b._callback({}, true, {"id":"pack-empty","kind":"resource_pack"})
	check(not b.results.back().ok, "empty storage response counted as packing success")
	b._callback({"storage":{"success":false}}, true, {"id":"pack-failed","kind":"resource_pack"})
	check(not b.results.back().ok, "rejected pack response counted as success")
	b._callback({"storage":{"success":true}}, true, {"id":"pack-success","kind":"resource_pack"})
	check(b.results.back().ok, "confirmed packing response rejected")
	# Revision 13: category policy and fixed locks are checked in the game too.
	b.policy = {"preserve_steam_tradable":false,"preserve_tradable":true,"trade_rules":{
		"equipment":{"enabled":false,"qualities":["common"]},
		"material":{"enabled":false,"qualities":["common"]},
		"consumable":{"enabled":true,"qualities":["common"]},
		"gongfa":{"enabled":true,"qualities":["common"]},
		"fashion":{"enabled":true,"qualities":["common"]}},"manual_locks":[]}
	b.gm.equipments = {1:eq(false),2:eq(false),3:eq(false)}
	b.gm.character.equip_slots = [-1]
	execute("equip",{"item_id":1,"slot_idx":0})
	check(b.api.calls.size()==1,"default equipment category did not allow tradable equip")
	b.policy.manual_locks=["equipment:1"]
	execute("equip",{"item_id":1,"slot_idx":0})
	check(b.api.calls.is_empty(),"fixed candidate lock failed")
	b.policy.preserve_tradable=false
	execute("synth",{"item_ids":[1,2,3]})
	check(b.api.calls.is_empty(),"fixed synth lock failed with master off")
	b.gm.character.equip_slots=[1]
	execute("equip",{"item_id":2,"slot_idx":0})
	check(b.api.calls.is_empty(),"fixed worn equipment was replaced")
	b.policy.manual_locks=["material:1"]
	execute("open_pack",{"material_id":1})
	check(b.api.calls.is_empty(),"fixed resource pack was opened")
	execute("breakthrough")
	check(b.api.calls.is_empty(),"fixed breakthrough material consumed")
	check(not b._requirements_available([{"kind":"material","id":1,"count":1}],1,0),"fixed requirement allowed with master off")
	b.policy.manual_locks=["herb:7001"]
	execute("resource_pack",pack_params)
	check(b.api.calls.is_empty(),"fixed packing input consumed")
	b.policy.manual_locks=["gongfa:7:2"]
	check(not b._gongfa_bound_safe(7,2,true),"fixed page used for resume")
	b.policy.manual_locks=[]
	b.policy.preserve_tradable=true
	check(b._trade_protected("material",1),"consumable default not protected")
	b.policy.trade_rules.consumable.qualities=["epic"]
	check(b._trade_protected("material",1),"unknown quality must be preserved")
	b.policy.trade_rules.consumable.qualities=[]
	check(not b._trade_protected("material",1),"empty quality selection ignored")
	# Exercise real read-only SDK parser and execution-time protection together.
	var reader = load("res://steam_inventory.gd").new()
	reader.sdk = FakeSteam.new()
	reader.bridge = b
	b.steam_inventory = reader
	reader._start_catalogue()
	check(not reader.catalogue_ready and reader.sdk.definition_requests==1,"missing SDK callback should wait safely")
	reader._refresh_catalogue(reader.next_definition_refresh-1)
	check(reader.sdk.definition_requests==1,"definition retry ignored its backoff")
	reader.sdk.emit_definitions=true
	reader._refresh_catalogue(reader.next_definition_refresh)
	check(reader.sdk.definition_requests==2 and reader.catalogue_ready,"missed definition callback was not retried")
	check(reader.catalogue_ready and reader.catalogue.size()==3,"Steam catalogue not parsed")
	var restored = load("res://steam_inventory.gd").new()
	restored.sdk=reader.sdk; restored.bridge=b
	restored.sdk.emit_definitions=false
	restored._start_catalogue()
	check(restored.catalogue_ready and restored.catalogue==reader.catalogue,"bridge replacement lost current-session SDK definitions")
	check(restored.describe("material",1).steam_trade_known and not restored.describe("material",1).steam_tradable,"cache did not restore ordinary material classification")
	check(restored.describe("material",4004).steam_tradable,"cache restore exposed Steam-tradable material")
	restored._definition_updated([4004,-1])
	check(restored.catalogue.size()==3,"malformed update erased known Steam definitions")
	restored.free()
	var warm = load("res://steam_inventory.gd").new()
	warm.sdk=FakeSteam.new(); warm.bridge=b
	warm._start_catalogue()
	warm.sdk.definitions_available=false
	warm._apply_items([{"item_definition":4004,"quantity":1,"flags":0}])
	check(not warm.catalogue_ready and not warm.describe("material",1).steam_trade_known,"inventory success alone exposed unknown materials")
	warm.sdk.definitions_available=true
	warm.sdk.mismatched_id=true
	warm._recover_cached_catalogue()
	check(not warm.catalogue_ready,"mismatched cached SDK identity marked definitions ready")
	warm.sdk.mismatched_id=false
	warm._recover_cached_catalogue()
	check(warm.catalogue_ready and not warm.catalogue_complete,"warm SDK properties failed to recover without callback")
	check(warm.describe("material",1).steam_trade_known and not warm.describe("material",1).steam_tradable,"SDK-confirmed absent definition overprotected ordinary materials")
	check(warm.describe("material",2705).steam_tradable,"warm cache exposed an unowned Steam definition")
	warm.sdk.definitions_available=false
	warm._apply_items([{"item_definition":4004,"quantity":1,"flags":0}])
	check(not warm.catalogue_ready and not warm.describe("material",1).steam_trade_known,"lost definition readiness kept stale ordinary classification")
	check(warm.describe("material",4004).steam_tradable,"failed cache refresh exposed a known Steam possession")
	warm.free()
	reader.page_definitions={"16:3":61603}
	reader._apply_items([{"item_definition":4004,"quantity":1,"flags":0},{"item_definition":2705,"quantity":2,"flags":0},{"item_definition":61603,"quantity":1,"flags":0},{"item_definition":4004,"quantity":5,"flags":256}])
	check(reader.complete and reader.stack_count==3 and reader.item_count==4,"Steam stacks or removed flags incorrect")
	check(reader.describe("gongfa",16,3).steam_tradable_count==1,"Steam page mapping lost")
	check(reader.describe("equipment",4004).steam_tradable==false,"server equipment confused with Steam definitions")
	check(reader.describe("material",1).steam_trade_known and not reader.describe("material",1).steam_tradable,"internal material not recognized")
	reader.catalogue[6]=true
	reader.counts[6]=1
	b.gm.inventory["fashions"]={2:{"fashion_id":6}}
	check(reader.describe("fashion",2).steam_definition==6,"fashion instance mistaken for Steam definition")
	check(reader.describe("fashion",2).steam_tradable_count==1,"Steam fashion possession not matched")
	check(not reader.describe("fashion",999).steam_trade_known,"missing fashion should remain unknown")
	# Market listing and transfer capability are independent SDK properties.
	var listing_policy = b.policy.duplicate(true)
	b.policy={"preserve_steam_tradable":true,"preserve_tradable":false,"manual_locks":[]}
	for flags in [["1","0"], ["0","1"], ["0","0"], ["1","1"]]:
		reader.sdk.properties[4004]={"tradable":{"success":true,"property":flags[0]},"marketable":{"success":true,"property":flags[1]}}
		reader._definition_updated([4004,2705,61603])
		var listing=reader.describe("material",4004)
		check(listing.steam_trade_known and listing.steam_tradable==(flags[1]=="1"),"transfer flag overrode market listing capability")
		check(b._trade_protected("material",4004)==(flags[1]=="1"),"execution guard retained the obsolete transfer rule")
		var cached_reader=load("res://steam_inventory.gd").new()
		cached_reader.sdk=reader.sdk; cached_reader.bridge=b
		cached_reader._apply_items([{"item_definition":4004,"quantity":2,"flags":0}])
		check(cached_reader.describe("material",4004).steam_tradable==(flags[1]=="1"),"SDK cache fallback retained the obsolete transfer rule")
		cached_reader.free()
		reader._apply_items([{"item_definition":4004,"quantity":2,"flags":0}])
		check(reader.item_count==(2 if flags[1]=="1" else 0),"market inventory counts used transfer capability")
	for malformed in [{"success":false,"property":"1"},{"success":true,"property":""},{"success":"true","property":"1"}]:
		reader.sdk.properties[4004]={"marketable":malformed}
		reader._definition_updated([4004,2705,61603])
		check(not reader.describe("material",4004).steam_trade_known,"unknown listing metadata was marked confirmed")
		reader.sdk.properties[4004].marketable={"success":true,"property":"0"}
		check(reader.describe("material",4004).steam_trade_known and not reader.describe("material",4004).steam_tradable,"recovered listing metadata did not clear unknown protection")
	b.policy=listing_policy
	reader.sdk.properties.clear()
	reader._definition_updated([4004,2705,61603])
	reader._apply_items([{"item_definition":4004,"quantity":1,"flags":0},{"item_definition":2705,"quantity":2,"flags":0},{"item_definition":61603,"quantity":1,"flags":0}])
	var previous_count=reader.item_count
	reader._apply_items([{"definition":4004,"quantity":1}])
	check(reader.item_count==previous_count,"malformed SDK results erased retained stock")
	b.policy={"preserve_steam_tradable":true,"preserve_tradable":false,"manual_locks":[]}
	check(b._trade_protected("material",4004),"Steam talisman not protected")
	check(b._trade_protected("material",2705),"Steam box without config label not protected")
	check(b._trade_protected("gongfa",16,{},3),"Steam page layer not protected")
	check(not b._trade_protected("material",1),"ordinary material overprotected in Steam-only mode")
	check(not b._trade_protected("equipment",4004),"ordinary equipment overprotected")
	reader.catalogue_ready=false
	check(b._trade_protected("material",1),"unknown Steam mapping failed open")
	reader.catalogue_ready=true
	b.policy.preserve_tradable=true
	check(b._trade_protected("material",1),"category and Steam union failed")
	b.policy.preserve_steam_tradable=false
	check(b._trade_protected("material",1),"category independent switch failed")
	b.policy.preserve_tradable=false
	check(not b._trade_protected("material",4004),"both switches off did not work")
	b.policy.manual_locks=["material:4004"]
	check(not b._requirements_bound_safe([{"kind":"material","id":4004,"count":1}]),"fixed lock did not override both switches off")
	reader.free()
	b.steam_inventory=null
	# Execute the new workflow through the real command guards, with no network or game.
	b.policy = {"preserve_steam_tradable":true,"preserve_tradable":false,"manual_locks":[], "tasks":{"breakthrough":true}, "breakthrough_auto_raise":true,"breakthrough_auto_craft":true,"breakthrough_auto_use":true,"breakthrough_auto_find":true,"breakthrough_target_rate":1.0,"min_breakthrough_rate":0.6}
	b.context = {"info":{"materials":[{"kind":"material","id":1,"count":2}]},"minimum_rate":0.6,"maximum_rate":0.6}
	b.gm.character.level=25
	b.gm.counts[1]=10
	b.gm.inventory.bound_items["material:1"]=10
	b.gm.storage={"herb":[{"items":[{"key":"herb:7001","count":10}]}]}
	b.gm.inventory.bound_items["herb:7001"]=10
	var craft={"pill_id":6021,"recipe_index":0,"count":1,"breakthrough_prepare":true}
	execute("alchemy",craft)
	check(b.api.calls.size()==1 and b.api.calls[0][1]=="craft","linked alchemy did not reach native craft")
	b.policy.breakthrough_auto_craft=false
	execute("alchemy",craft)
	check(b.api.calls.is_empty(),"disabled auto-craft spent ingredients")
	b.policy.breakthrough_auto_craft=true
	b.policy.manual_locks=["herb:7001"]
	execute("alchemy",craft)
	check(b.api.calls.is_empty(),"linked craft spent a fixed-locked herb")
	b.policy.manual_locks=[]
	b.gm.inventory.bound_items["herb:7001"]=9
	execute("alchemy",craft)
	check(b.api.calls.is_empty(),"linked craft spent mixed Steam inventory")
	b.gm.inventory.bound_items["herb:7001"]=10
	b.gm.counts[1]=4
	b.gm.inventory.bound_items["material:1"]=4
	execute("alchemy",craft)
	check(b.api.calls.is_empty(),"linked craft consumed the breakthrough's own material reserve")
	b.gm.counts[1]=10
	b.gm.inventory.bound_items["material:1"]=10
	b.gm.storage.pill=[{"items":[{"key":"pill:6021","count":2}]}]
	b.gm.inventory.bound_items["pill:6021"]=1
	execute("pill",{"pill_id":6021,"breakthrough_prepare":true})
	check(b.api.calls.size()==1 and b.api.calls[0][6]==1,"breakthrough pill did not select only bound stock")
	b.policy.breakthrough_auto_use=false
	execute("pill",{"pill_id":6021,"breakthrough_prepare":true})
	check(b.api.calls.is_empty(),"disabled auto-use consumed breakthrough pill")
	b.policy.breakthrough_auto_use=true
	b.gm.needs=false
	execute("pill",{"pill_id":6021,"breakthrough_prepare":true})
	check(b.api.calls.is_empty(),"used breakthrough pill before full experience")
	b.gm.needs=true
	execute("pill",{"pill_id":6021})
	check(b.api.calls.is_empty(),"generic pill command bypassed linked controls")
	execute("breakthrough")
	check(b.api.calls.is_empty(),"low probability reached breakthrough")
	b.context.minimum_rate=0.9
	b.context.maximum_rate=1.0
	execute("breakthrough")
	check(b.api.calls.is_empty(),"random upper bound mistaken for guaranteed success")
	b.context.minimum_rate=1.0
	execute("breakthrough")
	check(b.api.calls.size()==1,"achieved probability did not reach native breakthrough")
	b.policy.breakthrough_auto_raise=false
	b.context.minimum_rate=0.55
	b.context.maximum_rate=0.55
	b.policy.min_breakthrough_rate=0.5
	b.policy.breakthrough_settings_version=2
	check(b._breakthrough_target()==0.5,"legacy target overrode single target")
	check(int(b._preparation_reserved().get("material:1",0))==2,"disabled pills removed base material reserve")
	b.gm.counts[1]=1
	b.gm.inventory.bound_items["material:1"]=1
	check(b._breakthrough_gather_allowed("1_2_7"),"base gathering wrongly required pill automation")
	check(not b._breakthrough_gather_allowed("2_0_5"),"unrelated drop pool accepted for gathering")
	check(not "material:99" in b._idle_reward_stages()[0].items,"challenge-only bonus advertised as idle material")
	check("material:1073" in b._idle_reward_stages()[0].items,"upgrade sand missing from native idle pool")
	check(b._idle_reward_stages()[0].items.count("material:1073") == 1,"duplicate upgrade pool entry inflated gathering coverage")
	check("material:1107" in b._idle_reward_stages()[1].items,"upgrade spirit core missing from native idle pool")
	b.policy.breakthrough_auto_find=false
	check(not b._breakthrough_gather_allowed("1_2_7"),"disabled gathering was bypassed")
	b.policy.breakthrough_auto_find=true
	b.policy.idle_stage="2_0_5"
	check(not b._breakthrough_gather_allowed("1_2_7"),"pinned stage was overwritten")
	# Shared demands are recomputed independently from native state at execution.
	check(load("res://resource_budget.gd") != null,"resource budget helper failed to parse")
	b.policy={"growth_linked":true,"preserve_steam_tradable":false,"preserve_tradable":false,"manual_locks":[],
		"tasks":{"breakthrough":true,"refine":true,"upgrade":false,"alchemy":false,"pill":false,"material_synth":false},
		"refine_reserve":20,"refine_obsolete_reserve":2,"refine_recycle_obsolete":true,"refine_max_items":50,"refine_target_level":1}
	b.gm.character.level=25
	b.gm.character.equip_slots=[]
	b.gm.counts={1001:25,1008:0}
	b.gm.inventory.bound_items={}
	b.cfg.realm_table=[{"level":25,"materials":[{"kind":"material","id":1008,"count":10}]}]
	b.context={"info":{"materials":[{"kind":"material","id":1008,"count":10}]},"minimum_rate":1.0,"maximum_rate":1.0}
	# A stale mirror plan must use the latest demand and latest explicit target.
	b.gm.storage.clear()
	b.policy.world_use_mirror=true
	b.policy.world_mirror_target="auto"
	b.gm.consumable_counts[4003]=3
	b.gm.cave={"discovered_coords":[],"free_explore_limit":5}
	b.gm.free_used=5
	execute("world_explore",{"use_mirror":true,"target_type":"herb"})
	check(b.api.calls.size()==1 and b.api.calls[0][1].get("target_type")=="material","auto mirror lost current material shortage")
	b.context.info.materials=[{"kind":"herb","id":7001,"count":10}]
	execute("world_explore",{"use_mirror":true,"target_type":"material"})
	check(b.api.calls.size()==1 and b.api.calls[0][1].get("target_type")=="herb","auto mirror used stale demand")
	b.policy.world_mirror_target="relic"
	execute("world_explore",{"use_mirror":true,"target_type":"material","breakthrough_prepare":true})
	check(b.api.calls.size()==1 and b.api.calls[0][1].get("target_type")=="relic","old preparation overrode latest manual mirror target")
	b.policy.world_mirror_target="auto"
	b.policy.manual_locks=["herb:7001"]
	check(b._budget().mirror_target(b)=="material","mirror selected fixed-locked demand")
	b.policy.manual_locks=[]
	b.policy.preserve_steam_tradable=true
	b.gm.storage={"herb":[{"items":[{"key":"herb:7001","count":5}]}]}
	b.gm.inventory.bound_items["herb:7001"]=4
	check(b._budget().mirror_target(b)=="herb","mirror failed to replenish mixed bound shortage")
	b.policy.preserve_steam_tradable=false
	# Own reserve adds to, rather than overlaps, the higher-priority claim.
	b.gm.counts[1008]=16
	b.context.info.materials=[{"kind":"material","id":1008,"count":10}]
	check(not b._requirements_available([{"kind":"material","id":1008,"count":2}],1,5),"old craft spent its own reserve overlapping a breakthrough claim")
	b.gm.counts[1008]=17
	check(b._requirements_available([{"kind":"material","id":1008,"count":2}],1,5),"sum-of-reserves boundary rejected valid craft")
	b.context.info.materials=[{"kind":"herb","id":7001,"count":10}]
	b.policy.merge({"resource_pack_size":"4","resource_pack_reserve":100,"resource_pack_batch":2})
	execute("resource_pack",{"kind":"herb","material_id":7001,"size":4,"count":2})
	check(b.api.calls.is_empty(),"old packing plan overlapped its reserve with growth demand")
	b.context.info.materials=[{"kind":"material","id":1008,"count":10}]
	b.gm.counts[1008]=0
	b.gm.storage.clear()
	b.gm.free_used=0
	b.gm.cave={"discovered_coords":[]}
	var refining={"materials":{"1001":17},"preferred_reward":{"kind":"material","id":1008}}
	execute("refine",refining)
	check(b.api.calls.size()==1 and b.api.calls[0][0]=="refine","safe old-material recycling did not reach native refine")
	check(b.api.calls[0][3].get("id")==1008,"native call lost exact demand preference")
	b.policy.tasks.world_forge=true
	b.gm.cave.discovered_coords=[{"marker_id":14,"type":"forge"}]
	var forging={"marker_id":14,"materials":{"1001":6},"preferred_reward":{"kind":"material","id":1008}}
	execute("world_forge",forging)
	check(b.api.calls==[["world_forge",14,{"1001":6},1,{"kind":"material","id":1008}]],"native forge did not triple progress or changed physical input count")
	execute("refine",forging)
	check(b.api.calls.is_empty(),"ordinary refine incorrectly received world forge multiplier")
	forging.materials={"1001":17}
	execute("world_forge",forging)
	check(b.api.calls.size()==1 and b.api.calls[0][3]==3,"forge client_level did not match native effective progress")
	b.gm.counts[1001]=7
	execute("world_forge",forging)
	check(b.api.calls.is_empty(),"forge multiplier bypassed physical inventory and retention")
	b.gm.counts[1001]=25
	forging.materials={"1001":6}
	b.policy.manual_locks=["material:1001"]
	execute("world_forge",forging)
	check(b.api.calls.is_empty(),"forge multiplier bypassed fixed lock")
	b.policy.manual_locks=[]
	b.policy.preserve_steam_tradable=true
	b.gm.inventory.bound_items={"material:1001":24}
	execute("world_forge",forging)
	check(b.api.calls.size()==1,"forge rejected sufficient bound budget")
	b.gm.inventory.bound_items["material:1001"]=5
	execute("world_forge",forging)
	check(b.api.calls.is_empty(),"forge crossed protected unbound floor")
	b.policy.preserve_steam_tradable=false
	b.gm.inventory.bound_items.clear()
	b.gm.dungeon_idle.clear()
	execute("world_forge",forging)
	check(b.api.calls.is_empty(),"forge started without native required idle stage")
	b.gm.dungeon_idle={"selected":{"difficulty":0,"tier":0,"stage":0}}
	b.gm.cave.discovered_coords.clear()
	execute("world_forge",forging)
	check(b.api.calls.is_empty(),"stale forge marker reached native request")
	b.policy.tasks.world_forge=false
	b.gm.counts[1001]=18
	execute("refine",refining)
	check(b.api.calls.is_empty(),"old-material reserve ignored changed inventory")
	b.gm.counts[1001]=25
	b.gm.counts[1008]=10
	execute("refine",refining)
	check(b.api.calls.is_empty(),"satisfied target still consumed refinement inputs")
	b.gm.counts[1008]=0
	b.policy.manual_locks=["material:1001"]
	execute("refine",refining)
	check(b.api.calls.is_empty(),"refine consumed fixed-locked input")
	b.policy.manual_locks=["material:1008"]
	execute("refine",refining)
	check(b.api.calls.is_empty(),"old automatic preference consumed inputs for fixed-locked target")
	b.policy.manual_locks=[]
	b.policy.preserve_steam_tradable=true
	b.gm.counts[1008]=2
	b.gm.inventory.bound_items={"material:1008":1,"material:1001":25}
	execute("refine",refining)
	check(b.api.calls.size()==1,"automatic refinement failed to replenish bound deficit")
	# A queued plan must not count protected unbound stock towards current growth retention.
	b.context.info.materials.append({"kind":"material","id":1001,"count":5})
	b.gm.inventory.bound_items["material:1001"]=23
	execute("refine",refining)
	check(b.api.calls.is_empty(),"refine spent bound stock reserved for current growth")
	b.gm.inventory.bound_items["material:1001"]=24
	execute("refine",refining)
	check(b.api.calls.size()==1,"refine rejected exact bound growth-plus-retention budget")
	b.policy.tasks.world_forge=true
	b.gm.cave.discovered_coords=[{"marker_id":14,"type":"forge"}]
	b.gm.inventory.bound_items["material:1001"]=12
	execute("world_forge",forging)
	check(b.api.calls.is_empty(),"forge spent bound stock reserved for current growth")
	b.gm.inventory.bound_items["material:1001"]=13
	execute("world_forge",forging)
	check(b.api.calls.size()==1,"forge rejected exact bound growth-plus-retention budget")
	b.policy.tasks.world_forge=false
	b.gm.cave.discovered_coords.clear()
	b.policy.preserve_steam_tradable=false
	b.gm.inventory.bound_items["material:1001"]=1
	execute("refine",refining)
	check(b.api.calls.size()==1,"disabled protection still restricted refinement to bound stock")
	b.policy.refine_reserve=2
	b.cfg.realm_table.append({"level":35,"materials":[{"kind":"material","id":1001,"count":8}]})
	b.policy.preserve_steam_tradable=true
	b.gm.inventory.bound_items["material:1001"]=24
	execute("refine",refining)
	check(b.api.calls.is_empty(),"refine crossed future absolute floor")
	b.gm.inventory.bound_items["material:1001"]=25
	execute("refine",refining)
	check(b.api.calls.size()==1,"refine double-counted overlapping current and future requirements")
	b.policy.tasks.world_forge=true
	b.gm.cave.discovered_coords=[{"marker_id":14,"type":"forge"}]
	b.gm.inventory.bound_items["material:1001"]=13
	execute("world_forge",forging)
	check(b.api.calls.is_empty(),"forge crossed future absolute floor")
	b.gm.inventory.bound_items["material:1001"]=14
	execute("world_forge",forging)
	check(b.api.calls.size()==1,"forge double-counted overlapping current and future requirements")
	b.policy.tasks.world_forge=false
	b.gm.cave.discovered_coords.clear()
	b.policy.refine_reserve=20
	b.policy.preserve_steam_tradable=false
	b.cfg.realm_table.resize(1)
	b.context.info.materials.resize(1)
	b.gm.inventory.bound_items["material:1001"]=25
	b.policy.preserve_steam_tradable=false
	execute("refine",refining)
	check(b.api.calls.size()==1,"disabled protection failed to restore automatic refinement")
	b.gm.counts[1008]=0
	b.gm.inventory.bound_items.clear()
	b.cfg.realm_table.append({"level":35,"materials":[{"kind":"material","id":1001,"count":24}]})
	execute("refine",refining)
	check(b.api.calls.is_empty(),"refine consumed future breakthrough requirements")
	b.cfg.realm_table.resize(1)
	b.policy.tasks.refine=false
	execute("refine",refining)
	check(b.api.calls.is_empty(),"disabled task executed stale command")
	b.policy.tasks.refine=true
	b.policy.growth_linked=false
	execute("refine",refining)
	check(b.api.calls.is_empty(),"disabled linkage accepted old automatic preference")
	b.policy.growth_linked=true
	b.gm.resource_realm={"portal":{"id":"portal","type":"material"},"free_remaining":{"shared":1}}
	b.cfg.resource_enabled=true
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.size()==1 and b.api.calls[0][0]=="resource_realm","free resource realm failed to use native operation")
	execute("resource_realm",{"action":"enter","portal_id":"old"})
	check(b.api.calls.is_empty(),"stale resource portal was accepted")
	b.policy.manual_locks=["material:1008"]
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.is_empty(),"old realm plan entered for fixed-locked demand")
	b.context.info.materials.append({"kind":"material","id":1009,"count":1})
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.size()==1,"locked demand hid another usable shortage of same kind")
	b.context.info.materials.resize(1)
	b.policy.manual_locks=[]
	b.policy.preserve_steam_tradable=true
	b.gm.counts[1008]=2
	b.gm.inventory.bound_items["material:1008"]=1
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.size()==1,"realm failed to replenish mixed bound deficit")
	b.gm.inventory.bound_items["material:1008"]=2
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.size()==1,"fully bound realm demand was incorrectly blocked")
	b.gm.inventory.bound_items["material:1008"]=1
	b.policy.preserve_steam_tradable=false
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.size()==1,"disabled protection failed to restore realm demand")
	b.gm.counts[1008]=10
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.is_empty(),"satisfied realm demand still consumed entrance opportunity")
	b.gm.counts[1008]=0
	b.gm.inventory.bound_items.clear()
	b.gm.resource_realm.free_remaining.shared=0
	execute("resource_realm",{"action":"enter","portal_id":"portal"})
	check(b.api.calls.is_empty(),"resource realm spent token while token switch disabled")
	b.gm.disabled_features=["refine"]
	execute("refine",refining)
	check(b.api.calls.is_empty(),"locked native feature accepted stale task")
	b.gm.disabled_features=[]
	b.gm.cave.discovered_coords=[{"marker_id":999,"type":"spring"}]
	b.gm.character.exp_current=100
	execute("world_points",{"marker_id":999})
	check(b.api.calls.is_empty(),"full experience consumed a spring request")
	b.gm.character.exp_current=99
	execute("world_points",{"marker_id":999})
	check(b.api.calls.size()==1,"spring did not resume after experience space became available")
	# Optional recipes must advance past permanently unusable ingredients.
	var budget = load("res://resource_budget.gd")
	b.context = {"info":{}, "minimum_rate":1.0, "maximum_rate":1.0}
	b.gm.needs = false
	b.policy = {"growth_linked":true,"preserve_steam_tradable":false,"preserve_tradable":false,"alchemy_reserve":0,"upgrade_reserve":0,"tasks":{"alchemy":true,"upgrade":false,"breakthrough":false}}
	b.cfg.pill_list = [{"id":6001,"effects":[],"recipes":[{"realm":0,"materials":[{"kind":"material","id":1,"count":1}]},{"realm":0,"materials":[{"kind":"material","id":2,"count":3}]}]}]
	b.gm.counts={1:0,2:0}
	b.gm.inventory.bound_items.clear()
	b.policy.manual_locks=["material:1"]
	check(budget.normal_recipe(b).get("recipe_index")==1,"fixed-locked optional recipe blocked another achievable recipe")
	b.policy.manual_locks=[]
	b.policy.preserve_tradable=true
	b.gm.counts[1]=1
	check(budget.normal_recipe(b).get("recipe_index")==0,"optional recipe ignored replenishable bound deficit")
	b.policy.preserve_tradable=false
	check(budget.normal_recipe(b).get("recipe_index")==0,"disabling protection did not restore optional recipe")
	b.policy.manual_locks=["material:1","material:2"]
	check(budget.normal_recipe(b).is_empty(),"all blocked optional recipes still claimed resources")
	# An unusable high-level/tie representative cannot sacrifice the best usable gear.
	b.policy={"preserve_steam_tradable":false,"preserve_tradable":false,"manual_locks":["equipment:1"]}
	b.gm.equipments={1:eq(true),2:eq(true),3:eq(true),4:eq(true)}
	for eid in b.gm.equipments: b.gm.equipments[eid].id=eid
	b.gm.equipments[1].level=10
	b.gm.inventory.equipments=b.gm.equipments
	check(b._synthesis_preserved().has(2),"fixed locked gear dominated best usable equipment")
	b.policy.manual_locks=[]
	b.gm.equipments[1].locked=true
	check(b._synthesis_preserved().has(2),"game locked gear dominated best usable equipment")
	b.policy.preserve_tradable=true
	b.gm.equipments[1].locked=false
	b.gm.equipments[1].bound=false
	check(b._synthesis_preserved().has(2),"trade protected gear dominated best usable equipment")
	b.policy.preserve_tradable=false
	check(not b._synthesis_preserved().has(2),"disabled protection still excluded usable dominant equipment")
	# Demand-only conversion stops when upgrading is disabled, impossible or capped.
	b.policy={"preserve_steam_tradable":false,"preserve_tradable":false,"upgrade_reserve":0,"upgrade_level_gap":0,"tasks":{"upgrade":true}}
	b.gm.character.equip_slots=[2,3]
	b.gm.counts={1:0}
	check(b._material_upgrade_deficit(1)==4,"upgrade conversion failed to aggregate two valid slots")
	b.gm.equipments[2].locked=true
	check(b._material_upgrade_deficit(1)==2,"locked equipment still requested conversion resources")
	b.gm.equipments[3].level=b.gm.character.level
	check(b._material_upgrade_deficit(1)==0,"capped equipment still requested conversion resources")
	b.gm.equipments[3].level=5
	b.policy.tasks.upgrade=false
	check(b._material_upgrade_deficit(1)==0,"disabled upgrades still requested demand-only conversion")
	b.policy={"growth_linked":true,"preserve_tradable":false,"preserve_steam_tradable":false,"material_synth_reserve":0,"tasks":{"material_synth":true,"upgrade":true,"breakthrough":false,"alchemy":false}}
	b.gm.counts={1:100,2:1,3:0}
	b.cfg.synthesis_table={"chains":[[1,2,3]],"required_count":5}
	var direct={"material:2":2,"material:3":1}
	var conversions=budget.conversion_claims(b,direct,direct)
	check(conversions.get("material:2")==5,"shared intermediate input was not aggregated")
	check(conversions.get("material:1")==30,"shared input stock was allocated twice across conversion tiers")
	b.gm.character.equip_slots=[]
	check(b._material_upgrade_deficit(2)==0,"stale conversion survived removal of every upgrade demand")
	b.policy.manual_locks=["material:2"]
	conversions=budget.conversion_claims(b,{"material:2":2},{"material:2":2})
	check(conversions.is_empty(),"locked output still reserved conversion inputs")
	b.policy.manual_locks=[]
	b.cfg.synthesis_table={"chains":[[1,2,1]],"required_count":5}
	conversions=budget.conversion_claims(b,{"material:2":2},{"material:2":2})
	check(conversions.is_empty(),"cyclic conversion graph generated phantom ingredient demands")
	b.steam=FakeQueue.new()
	var queue=b._login_queue_snapshot()
	check(queue.active and queue.ahead_count==214,"native queue facts were not read")
	check(queue.next_poll_seconds<=23 and queue.next_poll_seconds>=0,"native queue poll seconds were not bounded")
	check(queue.keys().size()==5 and not queue.has("_queue_token"),"queue snapshot exported non-whitelisted fields")
	check_multiplayer_lifecycle()
	check_new_native_contracts()
	check_challenge_recovery()
	check_bound_first_exploration()
	check_world_cycle()
	check_growth_receipts()
	print("BRIDGE_SAFETY_CHECKS=", checks, " FAILURES=", failures.size())
	for failure in failures: push_error(failure)
	b.fake_main.free()
	get_tree().quit(0 if failures.is_empty() else 1)
