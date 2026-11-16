extends Node
# Only invokes existing client operations. Never exports account/session credentials.
var gm
var api
var cfg
var steam
var steam_inventory
var http: HTTPRequest
var timer: Timer
var endpoint = "http://127.0.0.1:17321/bridge"
var token = ""
var busy = false
var manual_breakthrough = false
var last_id = ""
var results: Array = []
var challenge: Dictionary = {}
var native_recovery: Dictionary = {}
var snapshot_cache: Dictionary = {}
var snapshot_at = 0
var policy: Dictionary = {}
var main_cache: WeakRef
var pending_world_event: Dictionary = {}
var stronghold_choices: Dictionary = {}
var mail_cache: Array = []
var partner_synced_at = 0
var bounty_cache: Dictionary = {}
var external: Dictionary = {}
var social_attempts: Dictionary = {}
var capture_attempts: Dictionary = {}
var mp_prepare: Dictionary = {}
var mp_prepared_at = 0
var realm_command: Dictionary = {}
var inventory_options: Dictionary = {}
var inventory_view: Dictionary = {}
var inventory_view_at = 0
var daily_guard: Dictionary = {}
const FORGE_PROGRESS_MULTIPLIER = 3 # Native MainUI._calculate_active_refine_level (0.2.30).
const TASK_FEATURES = {"harvest": "battle_idle", "equip": "equipment", "idle_select": "battle_idle", "gongfa_activate": "gongfa", "gongfa_slots": "gongfa", "gongfa": "gongfa", "gongfa_accelerate": "gongfa", "upgrade": "equipment", "pill": "alchemy", "alchemy": "alchemy", "world_sync": "explore", "world_events": "explore", "world_harvest": "explore", "world_points": "explore", "world_explore": "explore", "world_prune": "explore", "challenge": "dungeon", "synth": "synth", "refine": "refine", "world_forge": "refine", "mail": "mail", "material_synth": "synth", "furnace_absorb": "furnace", "home_relocate": "explore"}
const RESULT_KEYS = {"resource_realm": "resource_realm", "resource_pack": "storage", "material_synth": "synth", "furnace_absorb": "cave_result", "home_relocate": "cave_result","equip": "equip", "upgrade": "equipment_upgrade", "breakthrough": "breakthrough",
	"gacha": "gacha", "gongfa": "gongfa_result", "open_pack": "consumable", "synth": "synth",
	"world_sync": "cave_result", "world_explore": "cave_result", "world_harvest": "cave_result",
	"world_points": "cave_result", "world_events": "cave_result", "world_prune": "cave_result",
	"gongfa_activate": "gongfa_result", "gongfa_slots": "gongfa_result", "gongfa_accelerate": "gongfa_result",
	"pill": "alchemy", "alchemy": "alchemy", "refine": "refine", "world_forge": "cave_result", "mail": "mail"}

func _ready() -> void:
	var upgrader = load(get_script().resource_path.get_base_dir().path_join("session_upgrade.gd"))
	if upgrader != null: upgrader.request(upgrader)
	gm = get_node_or_null("/root/GameManager")
	api = get_node_or_null("/root/ApiClient")
	cfg = get_node_or_null("/root/ConfigManager")
	steam = get_node_or_null("/root/SteamManager")
	if gm == null or api == null:
		print("[FanxiuAssistant] No game singletons; validation only.")
		return
	var key_path = OS.get_executable_path().get_base_dir().path_join("fanxiu-assistant.key")
	if FileAccess.file_exists(key_path):
		token = FileAccess.get_file_as_string(key_path).strip_edges()
	if token.is_empty():
		push_warning("[FanxiuAssistant] Pairing key missing")
		return
	native_recovery = {"state":"pending", "next_at":0}
	steam_inventory = load(get_script().resource_path.get_base_dir().path_join("steam_inventory.gd")).new()
	steam_inventory.configure(self)
	add_child(steam_inventory)
	if api.has_signal("request_logged"): api.request_logged.connect(_on_game_request)
	http = HTTPRequest.new()
	http.timeout = 4.0
	http.request_completed.connect(_on_poll)
	add_child(http)
	timer = Timer.new()
	timer.wait_time = 1.5
	timer.timeout.connect(_poll)
	add_child(timer)
	timer.start()
	print("[FanxiuAssistant] Local bridge ready; PID=", OS.get_process_id())
	_poll()

func _main():
	if main_cache != null and main_cache.get_ref() != null: return main_cache.get_ref()
	var scene = get_tree().current_scene
	if scene != null and scene.has_method("_start_dungeon_challenge"):
		main_cache = weakref(scene)
		return scene
	# The login transition can leave current_scene empty while Main is under root.
	var nodes: Array = [get_tree().root]
	while not nodes.is_empty():
		var node = nodes.pop_front()
		if node.has_method("_start_dungeon_challenge"):
			main_cache = weakref(node)
			return node
		nodes.append_array(node.get_children())
	return null

func _poll() -> void:
	if http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		return
	_recover_native_challenge()
	_check_challenge()
	_check_external()
	_check_realm_command()
	var packet = {"pid": OS.get_process_id(), "state": _snapshot(), "results": results, "busy": busy}
	http.request(endpoint, ["Content-Type: application/json", "X-Bridge-Key: " + token], HTTPClient.METHOD_POST, JSON.stringify(packet))

func _on_poll(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		return
	var message = JSON.parse_string(body.get_string_from_utf8())
	if not message is Dictionary:
		return
	var acks = message.get("acks", [])
	var next_policy: Dictionary = message.get("policy", {})
	if policy != next_policy:
		snapshot_at = 0
		snapshot_cache.clear()
	policy = next_policy
	daily_guard = message.get("daily_guard", {})
	inventory_options = message.get("inventory_request", {})
	if steam_inventory != null: steam_inventory.refresh(int(inventory_options.get("generation", 0)))
	results = results.filter(func(row): return not str(row.get("id", "")) in acks)
	var command = message.get("command", {})
	if command is Dictionary and not command.is_empty() and not busy:
		if str(command.get("id", "")) != last_id:
			last_id = str(command.get("id", ""))
			_execute(command)

func _login_queue_snapshot() -> Dictionary:
	if not steam is Object or not steam.has_method("login_queue_active"): return {}
	# Explicit whitelist: never serialize session/queue tokens or instance IDs.
	var result = {"active": bool(steam.login_queue_active()), "manual_only": bool(steam.login_queue_manual_only()) if steam.has_method("login_queue_manual_only") else false}
	if result.active:
		var ahead = steam.get("_queue_ahead")
		var next_at = steam.get("_queue_next_at")
		if ahead is int: result["ahead_count"] = maxi(0, ahead)
		if next_at is int: result["next_poll_seconds"] = maxi(0, ceili(float(next_at - Time.get_ticks_msec()) / 1000.0))
		result["claiming"] = steam.get("_queue_claiming") == true
	return result

func _native_gameplay_pending() -> bool:
	if api == null: return true
	# The native client excludes only reads it can safely order with inventory state.
	if api.has_method("has_pending_gameplay_request"): return bool(api.has_pending_gameplay_request())
	return int(api.pending_count) > 0

func _snapshot() -> Dictionary:
	var main = _main()
	var state = {"online": bool(steam.online), "ready": bool(gm.game_started) and main != null and native_recovery.get("state", "done") == "done",
		"battle_recovery": {"state":native_recovery.get("state", "done"), "message":native_recovery.get("message", "正在核对服务器战斗结算")},
		"network_blocked": bool(api.is_network_blocked()), "pending": 1 if _native_gameplay_pending() else 0,
		"tutorial_finished": bool(gm.tutorial_finished()), "battle": false, "version": str(load("res://scripts/data/client_version.gd").VERSION), "bridge_revision": 44,
		"protection_policy": _protection_policy(),
		"readiness": {"game_started": gm.game_started, "main_found": main != null,
			"scene": str(get_tree().current_scene.get_path()) if get_tree().current_scene != null else ""}}
	state["login_queue"] = _login_queue_snapshot()
	state["steam_inventory"] = steam_inventory.public_status() if steam_inventory != null else {}
	if not state.ready:
		return state
	state.battle = main.battle_flow != null and bool(main.battle_flow.in_combat)
	state["battle_pending"] = bool(api.dungeon_start_pending)
	state["client_update"] = {"state": api.get_client_update_state(), "latest": str(api.latest_client_version), "minimum": str(api.min_supported_version)}
	state["idle_collecting"] = bool(main.idle_system.get("_collecting")) if main.get("idle_system") != null else false
	var ch = gm.character
	state["character"] = {"name": ch.name, "level": ch.level, "exp": ch.exp_current,
		"exp_needed": cfg.get_exp_needed(ch.level), "wuxing": ch.wuxing, "injury": ch.get_injury_stacks(),
		"hp": ch.get_max_hp(), "atk": ch.get_atk(), "def": ch.get_def(), "element": ch.element,
		"equip_slots": ch.equip_slots, "gongfa": ch.gongfa}
	state["slots"] = cfg.get_equipment_slots()
	state["gacha_batch_limit"] = _gacha_batch_limit(main)
	state["gacha_batch_unlock_level"] = maxi(1, int(cfg.get_value("gacha_weights", "gacha_batch_unlock_level", 10)))
	state["progress"] = gm.dungeon_progress
	state["idle"] = gm.dungeon_idle
	state["idle_reward_stages"] = _idle_reward_stages()
	state["features"] = {}
	for feature in ["explore", "dungeon", "battle_idle", "equipment", "gongfa", "alchemy", "synth", "mail", "refine", "furnace"]:
		state.features[feature] = gm.is_feature_unlocked(feature)
	state["breakthrough"] = gm.get_breakthrough_preview()
	state.breakthrough["bound_only_safe"] = _breakthrough_bound_safe()
	state["breakthrough_preparation"] = _breakthrough_context()
	state["needs_breakthrough"] = gm.needs_breakthrough()
	state["realm_locked"] = cfg.is_world_realm_locked(ch.level)
	state["guaranteed_breakthrough"] = gm.first_breakthrough_guaranteed()
	state["pending_elixirs"] = get_node("/root/ServerState").pending_elixirs
	state["elixir_bonus"] = cfg.calc_pending_elixir_bonus(state.pending_elixirs)
	var next_node = main.dungeon_system.get_next_available()
	if next_node != null:
		state["next_dungeon"] = {"key": next_node.get_key(), "name": next_node.get_display_name(),
			"required_level": next_node.get_required_level()}
	if Time.get_ticks_msec() - snapshot_at > 5000 or snapshot_cache.is_empty():
		snapshot_at = Time.get_ticks_msec()
		snapshot_cache = _inventory_snapshot(main)
	state.merge(snapshot_cache)
	state["world"] = _world_snapshot()
	state["partner"] = _partner_snapshot()
	state["bounty"] = bounty_cache
	state["multiplayer"] = _multiplayer_snapshot(main)
	state["multiplayer_realm"] = {"enabled": state.multiplayer.enabled, "status": "运行中" if state.multiplayer.active else ("已开放，按角色资格和服务器场次入场" if state.multiplayer.enabled else "暂停或未开放")}
	state["native_auto_pill"] = _native_auto_pill_snapshot(main)
	state["fashion_collection"] = _fashion_collection_snapshot()
	state["resource_realm"] = _resource_realm_snapshot(main)
	state.battle = state.battle or state.resource_realm.get("battle_playing", false)
	var generation = int(inventory_options.get("generation", 0))
	var refresh_ms = maxi(5000, int(policy.get("inventory_refresh_seconds",60))*1000)
	if not inventory_options.is_empty() and (inventory_view.is_empty() or int(inventory_view.get("generation",-1)) != generation or (policy.get("inventory_auto_refresh",true) and Time.get_ticks_msec()-inventory_view_at >= refresh_ms)):
		var reader = load(get_script().resource_path.get_base_dir().path_join("inventory.gd"))
		inventory_view = reader.capture(self,str(inventory_options.get("icon_directory","")),generation)
		inventory_view_at = Time.get_ticks_msec()
	state["inventory_view"] = inventory_view
	return state

func _inventory_snapshot(main) -> Dictionary:
	var items: Array = []
	var upgrade_system = load("res://scripts/systems/equipment_upgrade_system.gd")
	for key in gm.inventory.equipments:
		var eq = gm.inventory.equipments[key]
		var item = eq.serialize()
		item.merge(_steam_info("equipment", int(eq.id)))
		item["name"] = eq.get_display_name()
		item["fixed_stats"] = cfg.get_equipment_fixed_stats(eq.slot, eq.level, eq.quality)
		item["stats"] = {}
		for stat in ["atk", "hp", "def", "shield", "mp", "mp_regen_per_sec", "crit_chance", "crit_damage", "attack_speed", "cdr", "lifesteal", "dodge_chance", "combo_chance", "stun_chance", "counter_chance", "resist_stun"]:
			item.stats[stat] = eq.get_stat(stat)
		if int(eq.id) in gm.character.equip_slots and upgrade_system != null:
			item["upgrade_needs"] = upgrade_system.requirements(eq)
			item["upgrade_enough"] = not item.upgrade_needs.is_empty()
			for req in item.upgrade_needs:
				if upgrade_system.count_owned(str(req.kind), int(req.id)) < int(req.count):
					item.upgrade_enough = false
			item["bound_only_safe"] = _requirements_bound_safe(item.upgrade_needs) and _equipment_allowed(eq)
		items.append(item)
	var trains: Array = []
	var gu = main.get("gongfa_ui")
	if gu != null:
		for gid in gu._training_candidates():
			var tr = gu._training_of(gid)
			var layer = gu._cultivated_layer(gid) + 1
			var allowed = gu._can_train_layer(gid, layer, tr.is_empty()).is_empty()
			trains.append({"id": gid, "layer": layer, "state": tr.get("state", ""), "allowed": allowed,
				"bound_only_safe": _gongfa_bound_safe(gid, layer, not tr.is_empty())})
	var materials: Array = []
	var owned: Dictionary = {}
	for kind in ["material", "herb", "pill"]:
		for page in gm.get_storage_type_pages(kind):
			for cell in page.get("items", []):
				var key = str(cell.get("key", ""))
				owned[key] = int(owned.get(key, 0)) + int(cell.get("count", 0))
	for info in cfg.get_value("items", "materials", []):
		var mid = int(info.get("id", 0))
		var count = int(gm.get_material_count(mid)) + int(gm.get_consumable_count(mid))
		owned["material:%d" % mid] = count
		if count > 0:
			materials.append({"id": mid, "count": count, "use_type": info.get("use_type", ""),
				"name": cfg.get_localized_material_name(mid), "category":info.get("category", ""), "quality":info.get("rarity", ""), "bound_count": _bound_count("material", mid)})
	for item in materials: item.merge(_steam_info("material", int(item.id)))
	var extra = _growth_snapshot(main)
	extra.merge({"equipment": items, "training_candidates": trains, "materials": materials,
		"gacha_cost": cfg.get_value("gacha_weights", "gacha_cost_wuxing", 1),
		"synth_count": cfg.get_value("global_params", "synth_required_count", 5),
		"bound_items": _binding_snapshot(owned), "owned_items": owned})
	return extra

func _steam_info(kind: String, item_id: int, layer: int = -1) -> Dictionary:
	return steam_inventory.describe(kind, item_id, layer) if steam_inventory != null else {"steam_trade_known":false,"steam_tradable":false,"steam_tradable_count":0}

func _locked(kind: String, item_id: int, layer: int = -1) -> bool:
	var key = "%s:%d" % [kind, item_id]
	var locks: Array = policy.get("manual_locks", [])
	return key in locks or (layer >= 0 and (key + ":%d" % layer) in locks) or (kind == "equipment" and item_id in policy.get("protected_equipment", []))

func _item_info(kind: String, item_id: int) -> Dictionary:
	if kind == "equipment":
		var eq = gm.get_equipment(item_id)
		return {"quality":eq.quality} if eq != null else {}
	if kind == "pill" and cfg.has_method("get_pill_info"): return cfg.get_pill_info(item_id)
	if kind == "gongfa":
		var path = "res://scripts/data/gongfa_data.gd"
		if ResourceLoader.exists(path): return load(path).get_gongfa_by_id(item_id)
	if kind == "herb":
		var path = "res://scripts/systems/cave_system.gd"
		if ResourceLoader.exists(path): return load(path).get_herb_info(item_id)
	return cfg.get_material_info(item_id) if cfg.has_method("get_material_info") else {}

func _trade_protected(kind: String, item_id: int, known_info: Dictionary = {}, layer: int = -1) -> bool:
	if policy.get("preserve_steam_tradable", true):
		var steam_info = _steam_info(kind, item_id, layer)
		if not steam_info.get("steam_trade_known", false) or steam_info.get("steam_tradable", false): return true
	if not policy.get("preserve_tradable", false): return false
	# Legacy controllers retain their previous strict policy until migrated explicitly.
	if not policy.has("trade_rules"): return true
	var info = _item_info(kind, item_id) if known_info.is_empty() else known_info
	var category = kind if kind in ["equipment","fashion","gongfa"] else "material"
	if kind == "pill": category = "consumable"
	elif kind == "material":
		if info.get("category", "") == "gongfa_page" or info.get("use_type", "") == "gongfa_page": category = "gongfa"
		elif info.get("category", "") in ["consumable","prop"] or info.get("use_type", "") in ["resource_pack","equipment_box","fashion_box","prop","item_bundle","realm_supply"]: category = "consumable"
	var rule: Dictionary = policy.get("trade_rules", {}).get(category, {"enabled":true,"qualities":[]})
	var selected: Array = rule.get("qualities", [])
	var quality = str(info.get("quality", info.get("rarity", "")))
	return rule.get("enabled", true) and not selected.is_empty() and (quality not in ["common","fine","rare","epic","legend","myth","perfect","innate","treasure"] or quality in selected)

func _protection_policy() -> Dictionary:
	return {"preserve_steam_tradable": policy.get("preserve_steam_tradable", true),
		"preserve_tradable": policy.get("preserve_tradable", false),
		"trade_rules": policy.get("trade_rules", {}).duplicate(true),
		"manual_locks": policy.get("manual_locks", []).duplicate(),
		"protected_equipment": policy.get("protected_equipment", []).duplicate()}

func _equipment_score(eq) -> float:
	if eq == null: return 0.0
	var score = 0.0
	for stat in policy.get("weights", {}):
		var value = eq.get("stats", {}).get(stat, 0) if eq is Dictionary else eq.get_stat(stat)
		score += float(value) * float(policy.weights[stat])
	return score

func _synthesis_preserved() -> Array:
	var candidates: Array = []
	for eq in gm.inventory.get("equipments", {}).values():
		if _equipment_allowed(eq) and int(eq.level) <= gm.character.level: candidates.append(eq)
	var keep: Array = []
	if policy.get("equip_use_weights", false):
		var best: Dictionary = {}
		for eq in candidates:
			if not best.has(eq.slot) or _equipment_score(eq) > _equipment_score(best[eq.slot]): best[eq.slot] = eq
		for eq in best.values(): keep.append(int(eq.id))
	else:
		for eq in candidates:
			var dominated = false
			var fixed: Dictionary = cfg.get_equipment_fixed_stats(eq.slot, eq.level, eq.quality)
			for peer in candidates:
				if peer.slot != eq.slot or int(peer.id) == int(eq.id): continue
				if _fixed_upgrade(peer, eq) or (cfg.get_equipment_fixed_stats(peer.slot, peer.level, peer.quality) == fixed and int(peer.id) < int(eq.id)):
					dominated = true
					break
			if not dominated: keep.append(int(eq.id))
	return keep

func _fixed_upgrade(candidate, current) -> bool:
	if current == null: return true
	var next: Dictionary = cfg.get_equipment_fixed_stats(candidate.slot,candidate.level,candidate.quality)
	var old: Dictionary = cfg.get_equipment_fixed_stats(current.slot,current.level,current.quality)
	var improved = false
	for key in next:
		if float(next[key]) < float(old.get(key,0)): return false
		if float(next[key]) > float(old.get(key,0)): improved = true
	for key in old:
		if not next.has(key) and float(old[key]) > 0: return false
	return improved

func _equipment_allowed(eq) -> bool:
	return eq != null and eq.get("locked") != true and not _locked("equipment", int(eq.id)) and (eq.bound == true or not _trade_protected("equipment", int(eq.id), {"quality":eq.quality}))

func _bound_count(kind: String, item_id: int) -> int:
	var bindings: Dictionary = gm.inventory.get("bound_items", {})
	if kind == "material":
		# Material-facing APIs include props; the game stores their binding under consumable.
		# Clamp each physical pool separately so stale entries never grant extra bound stock.
		var materials = clampi(int(bindings.get("material:%d" % item_id, 0)), 0, maxi(0, int(gm.get_material_count(item_id))))
		var consumables = clampi(int(bindings.get("consumable:%d" % item_id, 0)), 0, maxi(0, int(gm.get_consumable_count(item_id))))
		return materials + consumables
	return int(bindings.get("%s:%d" % [kind, item_id], 0))

func _binding_snapshot(owned: Dictionary) -> Dictionary:
	var bindings: Dictionary = gm.inventory.get("bound_items", {}).duplicate(true)
	for key in owned:
		var parts = str(key).split(":")
		if parts.size() == 2 and parts[0] in ["material", "herb", "pill"] and parts[1].is_valid_int():
			bindings[key] = _bound_count(parts[0], int(parts[1]))
	return bindings

func _owned_count(kind: String, item_id: int) -> int:
	if kind == "material":
		return int(gm.get_material_count(item_id)) + int(gm.get_consumable_count(item_id))
	var total = 0
	for page in gm.get_storage_type_pages(kind):
		for cell in page.get("items", []):
			if str(cell.get("key", "")) == "%s:%d" % [kind, item_id]: total += int(cell.get("count", 0))
	return total

func _requirements_bound_safe(requirements: Array) -> bool:
	# Native deduction is bound-first: do not cross the protected unbound floor.
	var merged: Dictionary = {}
	for req in requirements:
		if not req is Dictionary: return false
		var kind = str(req.get("kind", "material"))
		var item_id = int(req.get("id", 0))
		var count = int(req.get("count", 0))
		if kind not in ["material", "herb", "pill"] or item_id <= 0 or count <= 0: return false
		var key = "%s:%d" % [kind, item_id]
		if not merged.has(key): merged[key] = {"kind": kind, "id": item_id, "count": 0}
		merged[key].count += count
	for req in merged.values():
		if _locked(str(req.kind), int(req.id)): return false
		var bound = _bound_count(str(req.kind), int(req.id))
		var total = _owned_count(str(req.kind), int(req.id))
		if total < int(req.count): return false
		if _trade_protected(str(req.kind), int(req.id)) and bound < int(req.count):
			return false
	return true

func _breakthrough_bound_safe() -> bool:
	var info = cfg.get_breakthrough_info(gm.character.level)
	return _requirements_bound_safe(info.get("materials", []))

func _idle_reward_stages() -> Array:
	var stages: Array = []
	if not cfg.has_method("get_dungeon_reward_node"): return stages
	for key in gm.dungeon_progress.get("cleared_ids", []):
		var parts = str(key).split("_")
		if parts.size() != 3: continue
		var reward: Dictionary = cfg.get_dungeon_reward_node(int(parts[0]), int(parts[1]), int(parts[2]))
		var items: Array = []
		# Only the stage's own pools. Challenge-only and next-realm bonuses are not idle guarantees.
		for field in ["material_ids", "pill_material_ids", "equipment_upgrade_ids", "herb_ids"]:
			var kind = "herb" if field == "herb_ids" else "material"
			for item_id in reward.get(field, []):
				var item_key = "%s:%d" % [kind, int(item_id)]
				if not item_key in items: items.append(item_key)
		stages.append({"key": str(key), "name": "关卡 " + str(key), "items": items})
	return stages

func _breakthrough_enabled() -> bool:
	return (policy.get("tasks", {}).get("breakthrough", true) or manual_breakthrough) and not cfg.is_world_realm_locked(gm.character.level)

func _breakthrough_gather_allowed(key: String) -> bool:
	if not _breakthrough_enabled() or not policy.get("breakthrough_auto_find", true): return false
	if policy.get("idle_stage", "auto") != "auto" or not policy.get("tasks", {}).get("idle_select", true) or not policy.get("tasks", {}).get("harvest", true): return false
	var held = _preparation_reserved()
	for row in _idle_reward_stages():
		if row.key != key: continue
		for item_key in row.items:
			var parts = str(item_key).split(":")
			var item_id = int(parts[1])
			if _locked(parts[0], item_id): continue
			var total = _budget().available(self, parts[0], item_id)
			if int(held.get(item_key, 0)) > total: return true
	return false

func _breakthrough_target() -> float:
	var threshold = float(policy.get("min_breakthrough_rate", 0.6))
	return maxf(threshold, float(policy.get("breakthrough_target_rate", threshold))) if int(policy.get("breakthrough_settings_version", 1)) < 2 and policy.get("breakthrough_auto_raise", true) else threshold

func _breakthrough_linked() -> bool:
	return policy.get("breakthrough_auto_raise", true) and _breakthrough_enabled()

func _breakthrough_effect(pill: Dictionary) -> Dictionary:
	for effect in pill.get("effects", []):
		if effect.get("type", "") == "breakthrough_bonus": return effect
	return {}

func _breakthrough_matching(pill: Dictionary) -> bool:
	for recipe in pill.get("recipes", []):
		if int(recipe.get("realm", -1)) == cfg.get_realm_id_by_level(gm.character.level): return true
	return false

func _breakthrough_context() -> Dictionary:
	var info: Dictionary = cfg.get_breakthrough_info(gm.character.level).duplicate(true)
	if info.is_empty(): return {"info": {}, "minimum_rate": 0.0, "maximum_rate": 0.0}
	var requirements: Array = []
	for raw in info.get("materials", []):
		var row: Dictionary = raw.duplicate(true)
		row["kind"] = str(row.get("kind", "material"))
		row["name"] = load("res://scripts/data/pill_data.gd").get_material_name(row.kind, int(row.id))
		requirements.append(row)
	info["materials"] = requirements
	var failure_bonus = float(gm.get_breakthrough_failure_bonus()) if gm.has_method("get_breakthrough_failure_bonus") else 0.0
	var minimum = float(info.get("base_rate", 0)) + failure_bonus
	var maximum = minimum
	for pid in get_node("/root/ServerState").pending_elixirs:
		var pill: Dictionary = cfg.get_pill_info(int(pid))
		if not _breakthrough_matching(pill): continue
		var effect = _breakthrough_effect(pill)
		minimum += float(effect.get("value", effect.get("value_min", 0)))
		maximum += float(effect.get("value", effect.get("value_max", 0)))
	if gm.first_breakthrough_guaranteed():
		minimum = 1.0
		maximum = 1.0
	return {"info": info, "minimum_rate": clampf(minimum, 0, 1), "maximum_rate": clampf(maximum, 0, 1), "failure_bonus": clampf(failure_bonus, 0, 1)}

func _breakthrough_pill_needed(pill: Dictionary) -> bool:
	if not _breakthrough_linked() or not gm.is_feature_unlocked("alchemy") or cfg.is_multiplayer_realm_pill_suspended(pill): return false
	if int(pill.get("min_level", 1)) > gm.character.level or not _breakthrough_matching(pill): return false
	var context = _breakthrough_context()
	return not context.info.is_empty() and float(context.minimum_rate) + 0.000000001 < _breakthrough_target() and float(_breakthrough_effect(pill).get("value", _breakthrough_effect(pill).get("value_min", 0))) > 0

func _preparation_reserved() -> Dictionary:
	var result: Dictionary = {}
	if not _breakthrough_enabled(): return result
	var context = _breakthrough_context()
	if context.info.is_empty(): return result
	for req in context.info.get("materials", []):
		var key = "%s:%d" % [req.get("kind", "material"), int(req.id)]
		result[key] = int(result.get(key, 0)) + int(req.count)
	if not _breakthrough_linked() or not policy.get("breakthrough_auto_craft", true): return result
	var pd = load("res://scripts/data/pill_data.gd")
	var chosen: Dictionary = {}
	var best_score: Array = []
	for pill in cfg.get_pill_list():
		if not _breakthrough_pill_needed(pill): continue
		var pid = int(pill.id)
		var effect = _breakthrough_effect(pill)
		var bonus = float(effect.get("value", effect.get("value_min", 0)))
		var usable = 0 if _locked("pill", pid) else (_bound_count("pill", pid) if _trade_protected("pill", pid) else _owned_count("pill", pid))
		usable = maxi(0, usable - int(policy.get("pill_reserve", 0)))
		var needed = maxi(1, ceili((_breakthrough_target() - float(context.minimum_rate) - 0.000000001) / bonus))
		var best_needs: Array = []
		var best_gap = 2147483647
		for index in pill.get("recipes", []).size():
			var recipe: Dictionary = pill.recipes[index]
			if int(recipe.get("realm", -1)) != cfg.get_realm_id_by_level(gm.character.level): continue
			var needs: Array = pd.get_recipe_materials(pill, index)
			var gap = 0
			for req in needs:
				gap += maxi(0, int(req.count) + int(policy.get("breakthrough_material_reserve", 0)) - _budget().available(self, str(req.get("kind", "material")), int(req.id)))
			if not needs.is_empty() and gap < best_gap:
				best_needs = needs; best_gap = gap
		if usable == 0 and best_needs.is_empty(): continue
		var score = [0 if usable > 0 else 1, needed, pid]
		if chosen.is_empty() or _budget().score_before(score, best_score):
			chosen = {"needs": best_needs, "count": maxi(0, needed - usable)}
			best_score = score
	for req in chosen.get("needs", []):
		if int(chosen.count) <= 0: break
		var key = "%s:%d" % [req.get("kind", "material"), int(req.id)]
		result[key] = int(result.get(key, 0)) + int(req.count) * int(chosen.count) + int(policy.get("breakthrough_material_reserve", 0))

	return result

func _gongfa_bound_safe(gid: int, layer: int, resuming: bool = false) -> bool:
	if _locked("gongfa", gid, layer): return false
	if resuming: return true
	var total = int(gm.inventory.get("gongfa_pages", {}).get(str(gid), {}).get(str(layer), 0))
	var bound = int(gm.inventory.get("bound_gongfa_pages", {}).get(str(gid), {}).get(str(layer), 0))
	return total > 0 and (not _trade_protected("gongfa", gid, {}, layer) or bound > 0)

func _done(id: String, success: bool, detail: String = "", data: Dictionary = {}) -> void:
	if id == str(native_recovery.get("id", "")):
		native_recovery["state"] = "blocked" if data.get("unconfirmed", false) else "done"
		native_recovery["message"] = detail
	busy = false
	manual_breakthrough = false
	snapshot_at = 0
	snapshot_cache.clear()
	results.append({"id": id, "ok": success, "detail": detail.left(600), "data": data})
	while results.size() > 100:
		results.pop_front()

func _failure_metadata(response: Dictionary, answer: Dictionary = {}) -> Dictionary:
	# Only these scalar diagnostics may leave the game; never forward a response body.
	var clean: Dictionary = {}
	for source in [response, answer]:
		for key in ["code", "error_code"]:
			var value = source.get(key)
			if not value is String or value.is_empty() or value.length() > 96 or clean.has(key): continue
			var valid = true
			for character in value:
				if not ((character >= "A" and character <= "Z") or (character >= "a" and character <= "z") or (character >= "0" and character <= "9") or character in ["_", ".", "-"]): valid = false
			if valid: clean[key] = value
		var status = source.get("http_code")
		if status is int and status >= 400 and status <= 599 and not clean.has("http_code"): clean["http_code"] = status
		var delay = source.get("retry_after_seconds")
		if (delay is int or delay is float) and is_finite(float(delay)) and float(delay) > 0 and float(delay) <= 86400:
			clean["retry_after_seconds"] = maxf(float(clean.get("retry_after_seconds", 0)), float(delay))
	return clean

func _failure_detail(response: Dictionary, answer: Dictionary, fallback: String) -> String:
	var metadata = _failure_metadata(response, answer)
	for value in [answer.get("reason"), response.get("server_error"), metadata.get("code"), metadata.get("error_code"), response.get("error")]:
		if value is String and not value.strip_edges().is_empty(): return value.strip_edges().left(600)
	return "游戏请求失败（HTTP %d）" % int(metadata.http_code) if metadata.has("http_code") else fallback

func _callback(response: Dictionary, ok: bool, command: Dictionary, key: String = "") -> void:
	# Result schema is fixed locally; a stale command cannot weaken confirmation.
	var kind = str(command.get("kind", ""))
	key = str(RESULT_KEYS.get(kind, ""))
	var answer = response.get(key, {}) if not key.is_empty() else response
	var success = false
	if ok:
		if not key.is_empty():
			success = answer is Dictionary and answer.get("success") == true
		elif kind in ["collect", "levelup"]:
			success = response.get("character") is Dictionary and not response.character.is_empty()
		elif kind == "harvest":
			success = response.get("dungeon_idle") is Dictionary and not response.dungeon_idle.is_empty()
		elif kind == "mail":
			success = response.has("mail")
	if kind == "breakthrough" and ok and response.get("character") is Dictionary:
		api.apply_deferred_response(response)

	if kind.begins_with("world_") and answer is Dictionary:
		# Only the two interactive event types require a server resolution.
		# Ordinary exploration events have already settled before their popup appears.
		if kind == "world_sync" and success:
			_set_pending_world_event(answer.get("pending_event", {}))
		elif ok and (success or answer.has("pending_event")):
			var event = answer.get("pending_event", answer.get("event", {}))
			if event is Dictionary and not event.is_empty(): _set_pending_world_event(event)
		if kind == "world_events" and (success or (ok and str(answer.get("reason", "")).contains("事件不存在或已处理"))):
			pending_world_event.clear()
		if kind == "world_points" and success:
			var marker = str(int(command.get("params", {}).get("marker_id", 0)))
			if answer.get("candidates") is Array: stronghold_choices[marker] = answer.candidates
			else: stronghold_choices.erase(marker)
	if kind == "mail" and success:
		if answer.get("mails") is Array:
			mail_cache.clear()
			for row in answer.mails:
				mail_cache.append({"id": int(row.get("id", 0)), "claimed": int(row.get("claimed_at", 0)) > 0, "rewards": not row.get("rewards", []).is_empty()})
		elif command.get("params", {}).has("mail_id"):
			for row in mail_cache:
				if int(row.id) == int(command.params.mail_id): row.claimed = true
	var detail = "游戏已确认操作" if success else _failure_detail(response, answer if answer is Dictionary else {}, "操作失败，游戏未返回具体原因")
	if ok and not success and detail == "操作失败，游戏未返回具体原因" and (not answer is Dictionary or answer.is_empty()): detail = "缺少预期结果，未确认成功"
	if success and answer is Dictionary and answer.get("reason") is String and not answer.reason.strip_edges().is_empty():
		detail = answer.reason.strip_edges().left(600)
	var execution: Dictionary = command.get("execution", {}).duplicate(true)
	if not success: execution["failure"] = _failure_metadata(response, answer if answer is Dictionary else {})
	if success and answer is Dictionary and not command.get("_growth_before", {}).is_empty():
		execution["growth_receipt"] = _flow_evidence().finish(self, command._growth_before, answer)
	_done(str(command.id), success, detail, execution)

func _set_pending_world_event(event: Variant) -> void:
	pending_world_event.clear()
	if event is Dictionary and int(event.get("event_id", 0)) > 0 and str(event.get("type", "")) in ["cultivator_help", "senior_cultivator"]:
		pending_world_event = {"event_id": int(event.event_id), "type": str(event.type)}

func _execute(command: Dictionary) -> void:
	command = command.duplicate(true)
	command.erase("_growth_before")
	var id = str(command.get("id", ""))
	var kind = str(command.get("kind", ""))
	var p = command.get("params", {})
	var main = _main()
	if native_recovery.get("state", "done") != "done":
		_done(id, false, "等待服务器战斗核对完成")
		return
	if main == null or not gm.game_started or not steam.online or api.is_network_blocked():
		_done(id, false, "客户端未就绪或连接已暂停")
		return
	if not gm.tutorial_finished():
		_done(id, false, "等待新手引导完成")
		return
	if api.is_client_update_blocked():
		_done(id, false, "原游戏要求更新，已暂停自动操作")
		return
	if (bool(main.battle_flow.in_combat) and kind != "multiplayer_realm") or api.dungeon_start_pending or _native_gameplay_pending() or _resource_realm_snapshot(main).battle_playing:
		_done(id, false, "等待当前战斗结算")
		return
	if not command.get("manual", false) and policy.get("tasks", {}).get(str(command.get("parent_kind", kind)), true) != true:
		_done(id, false, "任务开关已关闭，取消旧计划")
		return
	var feature = str(TASK_FEATURES.get(kind, ""))
	if not feature.is_empty() and not gm.is_feature_unlocked(feature):
		_done(id, false, "功能尚未解锁，取消旧计划")
		return
	manual_breakthrough = command.get("manual", false) and command.get("parent_kind", "") == "breakthrough"
	busy = true
	command["_growth_before"] = _flow_evidence().begin(self, command)
	var cb = func(response: Dictionary, ok: bool): _callback(response, ok, command, str(command.get("result_key", "")))
	match kind:
		"collect": api.collect(cb)
		"levelup": api.check_levelup(cb)
		"gacha":
			var cost = maxf(1.0, float(cfg.get_value("gacha_weights", "gacha_cost_wuxing", 1)))
			var available = int(floor((gm.character.wuxing - float(policy.get("reserve_wuxing", 20))) / cost))
			if available <= 0: _done(id, false, "悟性已到保留值")
			else: api.gacha(cb, clampi(int(p.get("count", 1)), 1, mini(_gacha_batch_limit(main), available)))
		"equip":
			var eid = int(p.get("item_id", -1))
			var eq = gm.get_equipment(eid)
			if not _equipment_allowed(eq) or eq.level > gm.character.level:
				_done(id, false, "装备被锁定、受保护或等级不足，取消换装")
			else:
				var slot = int(p.get("slot_idx", -1))
				var old_id = int(gm.character.equip_slots[slot]) if slot >= 0 and slot < gm.character.equip_slots.size() else -1
				var old = gm.get_equipment(old_id)
				if _locked("equipment", old_id) or (gm.get_equipment(old_id) != null and gm.get_equipment(old_id).get("locked") == true): _done(id, false, "保留手动保护的穿戴装备")
				elif slot < 0 or slot >= gm.character.equip_slots.size(): _done(id,false,"装备位置已变化")
				elif ("weapon" if str(eq.slot).begins_with("weapon_") else str(eq.slot)) != str(cfg.get_equipment_slots()[slot]) or (eid in gm.character.equip_slots and eid != old_id): _done(id,false,"装备部位或穿戴状态已变化")
				elif policy.get("equip_keep_weapon_type",true) and old != null and str(old.slot).begins_with("weapon") and old.slot != eq.slot: _done(id,false,"保留当前武器类型")
				elif not policy.get("equip_use_weights",false) and not _fixed_upgrade(eq,old): _done(id,false,"固定属性有下降或没有提升，保留当前装备")
				elif policy.get("equip_use_weights", false) and _equipment_score(eq) - _equipment_score(old) <= maxf(0.001, absf(_equipment_score(old)) * float(policy.get("equip_min_gain", 0.02))): _done(id,false,"权重评分未达到最新换装门槛")
				else: api.equip(cb, "equip_equipment", eid, slot)
		"upgrade":
			var eq = gm.get_equipment(int(p.get("item_id", -1)))
			var upgrade_system = load("res://scripts/systems/equipment_upgrade_system.gd")
			if not _equipment_allowed(eq) or upgrade_system == null or not _requirements_bound_safe(upgrade_system.requirements(eq)):
				_done(id, false, "装备或强化用料不符合当前保护设置，取消强化")
			elif int(eq.id) not in gm.character.equip_slots or int(eq.id) in policy.get("protected_equipment", []) or eq.level >= gm.character.level - int(policy.get("upgrade_level_gap", 0)) or not _requirements_available(upgrade_system.requirements(eq), 1, int(policy.get("upgrade_reserve", 5)), false, "upgrade"):
				_done(id, false, "强化目标或材料余量已变化")
			else: api.equipment_upgrade(cb, int(p.get("item_id", -1)), false)
		"breakthrough":
			if gm.needs_breakthrough() and not cfg.is_world_realm_locked(gm.character.level) and _breakthrough_bound_safe() and float(_breakthrough_context().get("minimum_rate", 0)) + 0.000000001 >= _breakthrough_target():
				api.breakthrough(cb)
			else:
				_done(id, false, "尚未满足突破条件")
		"harvest":
			var available: Array = []
			for drop in gm.dungeon_idle.get("drops", []):
				if main.dungeon_idle_system.is_drop_available(drop): available.append(int(drop.id))
			if available.is_empty(): _done(id, true, "暂无可领取掉落")
			else: api.dungeon_idle_harvest(cb, available)
		"idle_select":
			var coords = str(p.get("key", "")).split("_")
			if p.get("breakthrough_prepare", false) and not _breakthrough_gather_allowed(str(p.get("key", ""))):
				_done(id, false, "突破补料目标已变化或自动找料已关闭")
			elif not p.get("breakthrough_prepare", false) and str(policy.get("idle_stage", "auto")) != "auto" and str(p.get("key", "")) != str(policy.idle_stage):
				_done(id, false, "挂机目标配置已变化")
			elif coords.size() != 3 or gm.get_dungeon_status(str(p.get("key", ""))) != "cleared":
				_done(id, false, "挂机目标必须已通关")
			else:
				main.dungeon_idle_system.select_stage(int(coords[0]), int(coords[1]), int(coords[2]),
					func(success: bool, reason: String): _done(id, success, reason))
		"challenge":
			var node = main.dungeon_system.get_next_available()
			if node == null or node.get_key() != str(p.get("key", "")) or node.get_required_level() > gm.character.level:
				_done(id, false, "挑战目标已变化或等级不足")
			else:
				challenge = {"id": id, "start": Time.get_ticks_msec(), "key": node.get_key(), "kind": kind, "seen": false}
				_watch_battle(main)
				api.dungeon(func(response: Dictionary, ok: bool): _dungeon_started(response, ok, id, main, node), "start", node.difficulty, node.tier, node.stage)
		"gongfa":
			var action = str(p.get("action", "status"))
			var gid = int(p.get("gongfa_id", -1))
			var gu = main.get("gongfa_ui")
			var safe_page = action == "status" or (gu != null and _gongfa_bound_safe(gid, gu._cultivated_layer(gid) + 1, action == "resume_training"))
			if action in ["status", "start_training", "resume_training"] and safe_page:
				api.gongfa(cb, action, int(p.get("gongfa_id", -1)))
			else: _done(id, false, "不支持的功法动作")
		"mail":
			if p.has("mail_id"): api.mail(cb, "claim_mail", {"mail_id": int(p.mail_id)})
			else: api.mail(cb, "list")
		"open_pack":
			var mid = int(p.get("material_id", 0))
			var allowed = false
			for info in cfg.get_value("items", "materials", []):
				if int(info.get("id", 0)) == mid and info.get("use_type", "") in ["equipment_box", "resource_pack"]: allowed = true
			var pack_info = cfg.get_material_info(mid)
			if policy.get("tasks", {}).get("resource_pack", false) and pack_info.get("use_type", "") == "resource_pack":
				_done(id, false, "资源打包开启时不自动拆资源包，避免反复打包损耗")
			elif not allowed or _locked("material", mid) or (_bound_count("material", mid) <= 0 if _trade_protected("material", mid) else _owned_count("material", mid) <= 0):
				_done(id, false, "箱子库存不足或受当前保护设置限制")
			else: api.open_consumable(cb, mid, false, 1, 1 if _trade_protected("material", mid) else -1)
		"synth":
			var ids: Array = p.get("item_ids", [])
			var valid = ids.size() == int(cfg.get_value("global_params", "synth_required_count", 5))
			var seen: Dictionary = {}
			var group = ""
			var quality_order = ["common", "fine", "rare", "epic", "legend", "myth", "perfect", "innate", "treasure"]
			var cap = quality_order.find(str(policy.get("synth_max_quality", "rare")))
			var preserved = _synthesis_preserved()
			var total_level = 0
			for eid in ids:
				var eq = gm.get_equipment(int(eid))
				if seen.has(int(eid)): valid = false
				seen[int(eid)] = true
				if int(eid) in gm.character.equip_slots or int(eid) in policy.get("protected_equipment", []) or not _equipment_allowed(eq):
					valid = false
					continue
				var eq_group = str(eq.quality)
				if quality_order.find(eq_group) < 0 or quality_order.find(eq_group) > cap or int(eid) in preserved or int(eq.level) >= int(cfg.get_value("global_params", "max_equip_level", 80)): valid = false
				total_level += int(eq.level)
				if not group.is_empty() and eq_group != group: valid = false
				group = eq_group
			if total_level >= int(cfg.get_value("global_params", "max_equip_level", 80)) * ids.size(): valid = false
			if valid: api.synth(cb, "equipment", ids)
			else: _done(id, false, "合成材料已变化或包含穿戴装备")
		_:
			if kind in ["social_sync", "partner_practice", "partner_social", "partner_rescue", "player_capture", "player_occupy", "bounty_sync", "bounty_claim", "bounty_publish", "slave_escape", "multiplayer_realm"]:
				_execute_social(command)
			else: _execute_extended(command, cb)

func _watch_battle(main) -> void:
	if main.battle_flow is Object and main.battle_flow.has_signal("battle_state_changed") and not main.battle_flow.battle_state_changed.is_connected(_on_battle_state_changed):
		main.battle_flow.battle_state_changed.connect(_on_battle_state_changed)


	if main.battle_flow is Object and main.battle_flow.has_signal("dungeon_progress_advanced") and not main.battle_flow.dungeon_progress_advanced.is_connected(_on_dungeon_progress_confirmed):
		main.battle_flow.dungeon_progress_advanced.connect(_on_dungeon_progress_confirmed)
	if main.battle_flow is Object and main.battle_flow.has_signal("toast_requested") and not main.battle_flow.toast_requested.is_connected(_on_native_battle_notice):
		main.battle_flow.toast_requested.connect(_on_native_battle_notice)

func _native_defeat_notice() -> String:
	var locale = get_node_or_null("/root/LocaleManager")
	return str(locale.text("BATTLE_DEFEAT_TOAST")) if locale != null else ""

func _on_native_battle_notice(message: String) -> void:
	# The original battle UI emits this only after an accepted server loss settlement.
	# request_logged is debug-only; enabling debug would expose unrelated requests.
	if challenge.get("kind", "") != "challenge" or not challenge.get("seen", false) or str(challenge.get("battle_id", "")).is_empty(): return
	var expected = _native_defeat_notice()
	if not expected.is_empty() and (message == expected or message.begins_with(expected + "\n")):
		challenge["confirmed"] = true
		challenge["won"] = false

func _on_dungeon_progress_confirmed() -> void:
	# The original UI emits this only after a successful server win settlement.
	# A progression snapshot may arrive later, so do not infer defeat from stale state.
	if challenge.get("kind", "") == "challenge" and challenge.get("seen", false):
		challenge["confirmed"] = true
		challenge["won"] = true

func _on_battle_state_changed(active: bool) -> void:
	if active and not challenge.is_empty(): challenge["seen"] = true

func _dungeon_started(response: Dictionary, ok: bool, id: String, main, node) -> void:
	if challenge.get("id", "") != id: return
	var answer: Dictionary = response.get("dungeon", {})
	if not ok or not answer.get("success", false):
		_done(id, false, _failure_detail(response, answer, "副本启动未确认"), {"failure": _failure_metadata(response, answer)})
		challenge.clear()
		return
	# Follow the original UI start callback after the existing async replay wait.
	var entered: Dictionary = load("res://scripts/ui/ui_dungeon.gd").enter_dungeon(node, main.dungeon_system)
	if not entered.get("success", false):
		var reason = str(entered.get("reason", "客户端不能进入该副本"))
		main._cancel_dungeon_battle_start(node, str(answer.get("battle_id", "")), reason)
		_done(id, false, reason)
		challenge.clear()
		return
	main.dungeon_system.current_battle_id = str(answer.get("battle_id", ""))
	challenge["battle_id"] = main.dungeon_system.current_battle_id
	var allies: Array = []
	if answer.get("partner_ally") is Dictionary:
		allies.append(load("res://scripts/data/combat_unit.gd").from_snapshot(answer.partner_ally, false))
	if not main.battle_flow.start_combat(entered.player, entered.enemies, {"replay": answer.get("battle", {}).get("replay", {})}, allies):
		main._cancel_dungeon_battle_start(node, main.dungeon_system.current_battle_id, "客户端战斗启动失败")
		_done(id, false, "客户端战斗启动失败")
		challenge.clear()
	else:
		_watch_challenge_outcome(main)

func _watch_challenge_outcome(main) -> void:
	if challenge.get("kind", "") != "challenge" or str(challenge.get("battle_id", "")).is_empty(): return
	var combat = main.battle_flow.get("realtime_combat")
	if not combat is Object or not combat.has_signal("battle_ended"): return
	var arguments = [str(challenge.id), str(challenge.battle_id)]
	# Reused native combat objects must not retain an earlier operation's bindings.
	for connection in combat.battle_ended.get_connections():
		var existing: Callable = connection.callable
		if existing.get_object() == self and existing.get_method() == "_on_challenge_outcome" and existing.get_bound_arguments() != arguments:
			combat.battle_ended.disconnect(existing)
	var handler = _on_challenge_outcome.bindv(arguments)
	if not combat.battle_ended.is_connected(handler): combat.battle_ended.connect(handler)

func _on_challenge_outcome(result: Dictionary, id: String, battle_id: String) -> void:
	if challenge.get("id", "") != id or challenge.get("battle_id", "") != battle_id or typeof(result.get("win")) != TYPE_BOOL: return
	# This chooses the original request action only. Server acknowledgement still decides success.
	challenge["local_action"] = "complete" if result.win else "fail"

func _retry_challenge_settlement() -> void:
	if challenge.get("confirmed", false) or challenge.get("settlement_pending", false) or int(challenge.get("settlement_retries", 0)) >= 3: return
	var parts = str(challenge.get("key", "")).split("_")
	var action = str(challenge.get("local_action", ""))
	if parts.size() != 3 or action not in ["complete", "fail"] or str(challenge.get("battle_id", "")).is_empty(): return
	for part in parts:
		if not part.is_valid_int(): return
	var id = str(challenge.id)
	var battle_id = str(challenge.battle_id)
	var attempts = int(challenge.get("settlement_retries", 0)) + 1
	challenge["settlement_retries"] = attempts
	challenge["settlement_pending"] = true
	challenge["next_retry_at"] = Time.get_ticks_msec() + 5000 * (1 << attempts)
	api.dungeon(func(response: Dictionary, ok: bool):
		if challenge.get("id", "") != id or challenge.get("battle_id", "") != battle_id: return
		challenge["settlement_pending"] = false
		var answer: Dictionary = response.get("dungeon", {})
		if ok and answer.get("success", false) and str(answer.get("battle_id", battle_id)) == battle_id and answer.get("result", "") in ["win", "lose"]:
			challenge["confirmed"] = true
			challenge["won"] = answer.result == "win"
	, action, int(parts[0]), int(parts[1]), int(parts[2]), battle_id)

func _recover_native_challenge() -> void:
	if native_recovery.get("state", "done") != "pending": return
	if native_recovery.get("request_pending", false): return
	busy = false
	var main = _main()
	if main == null or not gm.game_started or not gm.tutorial_finished() or not steam.online or api.is_network_blocked() or _native_gameplay_pending() or api.dungeon_start_pending or main.battle_flow.in_combat: return
	if native_recovery.get("request_pending", false) or Time.get_ticks_msec() < int(native_recovery.get("next_at", 0)): return
	busy = true
	native_recovery["request_pending"] = true
	api.combat_resume(func(response: Dictionary, ok: bool):
		native_recovery["request_pending"] = false
		busy = false
		native_recovery["next_at"] = Time.get_ticks_msec() + 10000
		if native_recovery.get("state", "") != "pending": return
		if not ok or response.get("success", true) == false or response.has("error"): return
		var active_main = _main()
		if active_main == null or not gm.game_started or active_main.battle_flow.in_combat: return
		var battle = response.get("battle", {})
		if battle != null and not battle is Dictionary:
			busy = false
			native_recovery["state"] = "blocked"
			native_recovery["message"] = "服务器战斗数据无效，等待原客户端确认结算"
			return
		if battle == null or battle.is_empty():
			native_recovery["state"] = "done"
			busy = false
			return
		var context = response.get("context", {})
		var coords = context.get("dungeon_node", []) if context is Dictionary else []
		var valid_coords = coords is Array and coords.size() == 3
		if valid_coords:
			for coord in coords:
				if not (coord is int or coord is float) or not is_finite(float(coord)) or float(coord) < 0 or float(coord) != floor(float(coord)): valid_coords = false
		if not context is Dictionary or context.get("kind", "") != "dungeon" or not valid_coords or str(battle.get("battle_id", "")).is_empty():
			busy = false
			native_recovery["state"] = "blocked"
			native_recovery["message"] = "服务器仍有其他类型战斗，等待原客户端确认结算"
			return
		var id = "native-recovery-" + str(battle.battle_id).sha256_text().left(20)
		busy = true
		native_recovery["state"] = "replaying"
		native_recovery["id"] = id
		challenge = {"id":id, "start":Time.get_ticks_msec(), "key":"%d_%d_%d" % [int(coords[0]),int(coords[1]),int(coords[2])], "kind":"challenge", "seen":false, "battle_id":str(battle.battle_id)}
		active_main.dungeon_system.current_node = load("res://scripts/data/dungeon_node.gd").new(int(coords[0]),int(coords[1]),int(coords[2]))
		active_main.dungeon_system.current_battle_id = str(battle.battle_id)
		_watch_battle(active_main)
		active_main._on_external_battle_requested(battle, context)
		if active_main.battle_flow.in_combat:
			_watch_challenge_outcome(active_main)
		else:
			_done(id, false, "服务器战斗恢复未能开始", {"unconfirmed":true})
			challenge.clear()
	)

func _check_challenge() -> void:
	if challenge.is_empty(): return
	var main = _main()
	if main == null: return
	if main.battle_flow.in_combat:
		challenge.seen = true
		_watch_challenge_outcome(main)
	var age = Time.get_ticks_msec() - int(challenge.start)
	if bool(challenge.seen) and not main.battle_flow.in_combat and not api.dungeon_start_pending:
		var is_realm = challenge.get("kind", "") == "realm_challenge"
		if not is_realm and gm.get_dungeon_status(str(challenge.get("key", ""))) == "cleared":
			challenge["confirmed"] = true
			challenge["won"] = true
		if not challenge.has("confirmed"):
			if not challenge.has("ended_at"): challenge["ended_at"] = Time.get_ticks_msec()
			var settling_age = Time.get_ticks_msec() - int(challenge.ended_at)
			if not is_realm and settling_age >= 5000 and challenge.has("local_action") and not challenge.get("settlement_pending", false) and int(challenge.get("settlement_retries", 0)) < 3 and Time.get_ticks_msec() >= int(challenge.get("next_retry_at", 0)) and not _native_gameplay_pending():
				_retry_challenge_settlement()
				return
			var wait_limit = 300000 if is_realm else 120000 if challenge.has("local_action") else 30000
			if age > 300000 or Time.get_ticks_msec() - int(challenge.ended_at) > wait_limit:
				_done(str(challenge.id), false, "秘境结算超时，自动任务已暂停" if is_realm else "挑战结算未确认，自动任务已暂停", {"battle": true, "unconfirmed": true})
				challenge.clear()
			return
		var won = bool(challenge.get("won", false))
		_done(str(challenge.id), won, "通关已由服务器确认" if won else "挑战未通关，等待成长后重试", {"battle": true, "won": won})
		challenge.clear()
	elif age > 30000 and not bool(challenge.seen) and not api.dungeon_start_pending:
		_done(str(challenge.id), false, "战斗未能开始", {"unconfirmed": not str(challenge.get("battle_id", "")).is_empty()})
		challenge.clear()
	elif age > 300000:
		_done(str(challenge.id), false, "战斗超时，自动任务已暂停", {"battle": true, "unconfirmed": true})
		challenge.clear()

# Expansion reads only gameplay state; no identity/session fields leave the client.
func _exploration_day() -> String:
	return Time.get_datetime_string_from_unix_time(int(Time.get_unix_time_from_system()) + 8 * 3600).left(10)

func _world_point_expired(point: Dictionary, now_ms: int = -1) -> bool:
	if str(point.get("type", "ordinary")) not in ["player", "cultivator", "robot"]: return false
	if now_ms < 0: now_ms = int(Time.get_unix_time_from_system() * 1000.0)
	return int(point.get("expires_at", 0)) <= now_ms

func _world_map_full(world: Dictionary) -> bool:
	return int(world.get("point_count", 0)) >= mini(int(world.get("max_points", 20)), int(policy.get("world_point_limit", 20)))

func _world_snapshot() -> Dictionary:
	var cave: Dictionary = gm.cave
	var explore: Dictionary = cfg.get_value("cave_world", "explore", {})
	var realm = cfg.get_realm_id_by_level(gm.character.level)
	var limit = int(cave.get("free_explore_limit", int(explore.get("free_explore_base", 5)) + realm * int(explore.get("free_explore_per_realm", 2))))
	var points: Array = []
	var active_count = 0
	var now_ms = int(Time.get_unix_time_from_system() * 1000.0)
	for raw in cave.get("discovered_coords", []):
		if not raw is Dictionary: continue
		var point: Dictionary = {}
		for key in ["marker_id", "type", "quality", "is_current", "expires_at", "world_id", "coord_x", "coord_y", "features", "remaining", "power_assessment", "realm_key", "required_level", "target_level", "harvested_at", "cooldown_until"]:
			if raw.has(key): point[key] = raw[key]
		point["is_current"] = _point_is_current(raw)
		point["expired"] = _world_point_expired(raw, now_ms)
		if not point.expired: active_count += 1
		point["home_score"] = _home_score(raw.get("features", []))
		point["home_safe"] = _occupy_home_safe(raw) if str(raw.get("type", "")) in ["cultivator", "player", "robot"] else _home_safe(raw)
		if str(raw.get("type", "")) in ["cultivator", "player", "robot"]:
			point["target_token"] = _target_token(raw)
			point["furnace_unlocked"] = raw.get("furnace_unlocked", true) == true
			point["furnace_protected_until"] = raw.get("furnace_protected_until", 0)
		if point.get("type") == "breakthrough_realm":
			var view = load("res://scripts/ui/ui_cave_world_view.gd")
			point["difficulty"] = view._realm_difficulty(raw)
		if stronghold_choices.has(str(int(point.get("marker_id", 0)))): point["choices"] = stronghold_choices[str(int(point.marker_id))]
		points.append(point)
	var result = {"points": points, "point_count": active_count, "expired_point_count": points.size() - active_count, "max_points": int(explore.get("max_discovered_coords", 20)),
		"free_remaining": maxi(0, limit - gm.get_free_explore_used()), "pending_event": pending_world_event,
		"free_used": gm.get_free_explore_used(), "daily_count": gm.get_free_explore_used()}
	if str(daily_guard.get("day", "")) == _exploration_day(): result.daily_count = maxi(int(result.daily_count), int(daily_guard.get("world_explore", 0)))
	for mode in ["rumor", "mirror"]:
		result[mode] = _exploration_prop_snapshot(mode)
	result["home"] = {"quality": cave.get("active_coord_quality", "common"), "score": _home_score(cave.get("active_features", []))}
	result["captured"] = gm.is_captured_as_slave()
	var captured: Dictionary = cave.get("captured_as_slave", {}) if cave.get("captured_as_slave") is Dictionary else {}
	result["capture"] = {"capture_id": str(captured.get("capture_id", "")), "expires_at": captured.get("expires_at", 0), "attempted_escape": captured.get("attempted_escape", false), "master_token": str(captured.get("master_steamid", "")).sha256_text()}
	result["furnace_free"] = maxi(0, int(cave.get("furnace_slot_count", 1)) - gm.get_cave_furnace_slaves().size())
	result["escape_prop"] = _prop_snapshot(4004, 1)
	result["bounty_prop"] = _prop_snapshot(4002, 1)
	result["relocate"] = {"id":4001,"count": _owned_count("material", 4001), "bound_only_safe": _requirements_bound_safe([{"kind": "material", "id": 4001, "count": 1}])}
	return result

func _exploration_prop_snapshot(mode: String) -> Dictionary:
	# Native deduction is bound-first; spend only above the protected unbound floor.
	var explore: Dictionary = cfg.get_value("cave_world", "explore", {})
	var mid = int(explore.get(mode + "_material_id", 4006 if mode == "rumor" else 4003))
	var cost = maxi(1, gm.get_explore_prop_cost(mode))
	var total = maxi(0, int(gm.get_consumable_count(mid)))
	# Exploration consumes the consumable pool, never an unrelated material alias.
	var bound = clampi(int(gm.inventory.get("bound_items", {}).get("consumable:%d" % mid, 0)), 0, total)
	var known = not policy.get("preserve_steam_tradable", true) or _steam_info("material", mid).get("steam_trade_known", false)
	var usable = bound if _trade_protected("material", mid) else total
	if _locked("material", mid) or not known: usable = 0
	return {"id":mid, "count":total, "bound_count":bound, "cost":cost,
		"spendable_count":usable, "binding_order":"bound_first", "steam_trade_known":known,
		"bound_only_safe":usable >= cost, "unlocked":mode != "mirror" or gm.is_feature_unlocked("furnace")}

func _find_point(marker_id: int) -> Dictionary:
	for point in gm.cave.get("discovered_coords", []):
		if point is Dictionary and int(point.get("marker_id", 0)) == marker_id:
			var found = point.duplicate(true)
			found["is_current"] = _point_is_current(point)
			return found
	return {}

func _resource_pack_snapshot() -> Dictionary:
	var system = load("res://scripts/systems/resource_pack_system.gd")
	var recipes: Array = []
	for size in [4, 20, 100]:
		for pack in system.recipes(size):
			recipes.append({"input_kind": str(pack.get("pack_kind", "")), "input_id": int(pack.get("pack_resource_id", 0)),
				"size": size, "cost": system.cost(pack), "unbound_count": system.owned(pack), "output_id": int(pack.get("id", 0))})
	return {"recipes": recipes, "remaining": system.remaining()}

func _growth_snapshot(main) -> Dictionary:
	var options: Array = []
	var gd = load("res://scripts/data/gongfa_data.gd")
	var gu = main.get("gongfa_ui")
	if gu != null:
		for gf in gd.get_gongfa_list():
			var gid = int(gf.get("id", 0))
			var layer = gu._cultivated_layer(gid)
			var matched = gd.element_match(gf, gm.character.element)
			var active = gd.is_active(gf)
			var effect = gd.active_effect(gf, maxi(0, layer)) if active else {}
			var tr: Dictionary = gu._training_of(gid)
			var target = int(tr.get("target", layer + 1))
			options.append({"id": gid, "name": cfg.get_localized_gongfa_name(gid), "layer": layer,
				"activated": layer >= 0, "can_activate": layer < 0 and matched and gu._page_count(gid, 0) > 0,
				"activation_bound_safe": _gongfa_bound_safe(gid, 0), "element_match": matched, "active": active,
				"power": float(effect.get("coefficient", 0)) + float(effect.get("heal_ratio", 0)) + float(effect.get("shield_ratio", 0)),
				"training": tr, "spare_pages": gu._page_count(gid, target),
				"acceleration_bound_safe": _gongfa_bound_safe(gid, target)})
	var pills: Array = []
	var recipes: Array = []
	var pd = load("res://scripts/data/pill_data.gd")
	var realm = cfg.get_realm_id_by_level(gm.character.level)
	for pill in pd.get_pill_list():
		var pid = int(pill.get("id", 0))
		var useful = _pill_useful(pill)
		pills.append({"id": pid, "name": cfg.get_localized_pill_name(pid), "count": _owned_count("pill", pid),
			"bound_count": _bound_count("pill", pid), "useful": useful, "quality": pill.get("rarity", "common"),
			"is_breakthrough": not _breakthrough_effect(pill).is_empty(), "breakthrough_matching": _breakthrough_matching(pill) and not cfg.is_multiplayer_realm_pill_suspended(pill) and int(pill.get("min_level", 1)) <= gm.character.level,
			"bonus_min": float(_breakthrough_effect(pill).get("value", _breakthrough_effect(pill).get("value_min", 0))),
			"bonus_max": float(_breakthrough_effect(pill).get("value", _breakthrough_effect(pill).get("value_max", 0)))})
		pills[-1].merge(_steam_info("pill", pid))
		var raw_recipes: Array = pill.get("recipes", [])
		for index in raw_recipes.size():
			var needs = pd.get_recipe_materials(pill, index)
			recipes.append({"pill_id": pid, "recipe_index": index, "materials": needs,
				"is_breakthrough": not _breakthrough_effect(pill).is_empty(),
				"breakthrough_matching": _breakthrough_matching(pill) and int(raw_recipes[index].get("realm", -1)) == realm,
				"unlocked": gm.is_feature_unlocked("alchemy") and not cfg.is_multiplayer_realm_pill_suspended(pill) and int(raw_recipes[index].get("realm", 0)) <= realm,
				"craft_success_rate": float(raw_recipes[index].get("craft_success_rate", 1)),
				"useful": useful and int(raw_recipes[index].get("realm", 0)) <= realm and _owned_count("pill", pid) <= int(policy.get("pill_reserve", 0)),
				"bound_only_safe": _requirements_bound_safe(needs)})
	var refine = load("res://scripts/systems/refine_system.gd")
	var inputs: Array = []
	var future = _budget().future_context(self)
	var excluded: Dictionary = refine.get_auto_fill_exclusions()
	var preferences: Array = []
	for candidate in refine.get_preference_candidates():
		preferences.append({"kind": candidate.kind, "id": int(candidate.id), "name": pd.get_material_name("material" if candidate.kind == "equipment_upgrade" else str(candidate.kind), int(candidate.id))})
	for mat in refine.get_investable_materials():
		var info: Dictionary = mat.info
		var kind = "herb" if info.get("category", "") == "herb" else "material"
		inputs.append({"id": int(mat.id), "kind": kind, "count": int(mat.count),
			"category": info.get("category", ""), "value": refine.get_progress_value(info),
			"name": pd.get_material_name(kind, int(mat.id)), "auto_fill_excluded": excluded.has(str(int(mat.id))),
			"manual_only": info.get("category", "") == "pill_material",
			"future_need": int(future.required.get("%s:%d" % [kind, int(mat.id)], 0)),
			"obsolete": future.known and str(info.get("category", "")) in ["breakthrough_main", "breakthrough_aux", "breakthrough_special"] and not future.required.has("%s:%d" % [kind, int(mat.id)]),
			"bound_only_safe": _requirements_bound_safe([{"kind": kind, "id": int(mat.id), "count": 1}])})
	for item in inputs: item.merge(_steam_info(str(item.kind), int(item.id)))
	var packing = _resource_pack_snapshot()
	return {"resource_pack_recipes": packing.recipes, "resource_pack_remaining": packing.remaining, "material_synthesis": _material_synthesis_snapshot(), "furnace": {"exp_pool": gm.get_cave_furnace_exp_pool()}, "gongfa_options": options, "pills": pills, "alchemy_recipes": recipes,
		"refine_candidates": preferences, "upcoming_breakthrough": future.upcoming, "max_upgrade_level": int(cfg.get_value("equipment_upgrade", "max_level", 90)),
		"refine_inputs": inputs, "refine_progress_per_level": refine.get_progress_per_level(),
		"refine_max_level": refine.get_max_level(), "refine_forge_multiplier": FORGE_PROGRESS_MULTIPLIER, "mails": mail_cache,
		"max_equip_level": cfg.get_value("global_params", "max_equip_level", 80),
		"multiplayer_realm": {"enabled": bool(cfg.get_value("multiplayer_realm", "enabled", false)),
			"status": "当前版本未开放" if not cfg.get_value("multiplayer_realm", "enabled", false) else "需按开放版本验证"}}

func _gacha_batch_limit(main) -> int:
	var unlock = maxi(1, int(cfg.get_value("gacha_weights", "gacha_batch_unlock_level", 10)))
	if int(gm.character.level) < unlock or main == null or not main.has_method("_gacha_batch_count"): return 1
	return maxi(1, int(main.call("_gacha_batch_count")))

func _fashion_collection_snapshot() -> Dictionary:
	var summary = gm.inventory.get("fashion_collection", {})
	if not summary is Dictionary or summary.is_empty(): return {"known": false}
	var activated = gm.inventory.get("activated_fashion_ids", [])
	return {"known": true, "activated_count": activated.size() if activated is Array else 0,
		"percent": maxf(0, float(summary.get("percent", 0))),
		"idle_exp_percent": maxf(0, float(summary.get("idle_exp_percent", 0))),
		"limited_count": maxi(0, int(summary.get("limited_count", 0)))}

func _native_auto_pill_snapshot(main) -> Dictionary:
	var ui = main.get("auto_pill_ui") if main != null else null
	var controller = ui.get("controller") if ui != null else null
	if controller == null: return {"active": false}
	return {"active": bool(controller.running) or bool(controller.in_flight) or not str(controller.request_id).is_empty(),
		"running": bool(controller.running), "in_flight": bool(controller.in_flight),
		"pill_id": int(controller.pill_id), "remaining": int(controller.remaining), "status": str(controller.status)}

func _pill_useful(pill: Dictionary) -> bool:
	if pill.is_empty() or cfg.is_multiplayer_realm_pill_suspended(pill): return false
	if int(pill.get("min_level", 1)) > gm.character.level: return false
	var pd = load("res://scripts/data/pill_data.gd")
	var now = int(Time.get_unix_time_from_system() * 1000)
	for effect in pill.get("effects", []):
		match str(effect.get("type", "")):
			"change_element", "realm_restore", "realm_revive": return false
			"heal_injury": return gm.character.get_injury_stacks() > 0
			"breakthrough_bonus":
				return policy.get("breakthrough_auto_use", true) and gm.needs_breakthrough() and _breakthrough_pill_needed(pill)
			"timed_buff":
				if not policy.get("pill_timed_buffs", true) or _native_auto_pill_snapshot(_main()).active: return false
				for buff in gm.character.active_buffs:
					if not buff is Dictionary or (int(buff.get("expires_at", 0)) != 0 and int(buff.get("expires_at", 0)) <= now): continue
					var active = pd.get_pill_info(int(buff.get("pill_id", 0)))
					if active.get("recipe_group", -1) == pill.get("recipe_group", -2): return false
				return not pd.is_effect_covered(pill, gm.character.active_buffs)
	return false

func _requirements_available(requirements: Array, count: int, reserve: int, preparation: bool = false, consumer: String = "background") -> bool:
	var totals: Dictionary = {}
	for req in requirements:
		var key = "%s:%d" % [req.get("kind", "material"), int(req.get("id", 0))]
		if not totals.has(key): totals[key] = {"kind": req.get("kind", "material"), "id": int(req.get("id", 0)), "count": 0}
		totals[key].count += int(req.get("count", 0)) * count
	if totals.is_empty(): return false
	var held: Dictionary = {} if preparation else _budget().reserved(self, consumer)
	for req in totals.values():
		var retained = int(held.get("%s:%d" % [req.kind, int(req.id)], 0)) + reserve
		if int(req.id) <= 0 or int(req.count) <= 0 or _budget().available(self, str(req.kind), int(req.id)) - int(req.count) < retained: return false
	return _requirements_bound_safe(totals.values())

func _execute_extended(command: Dictionary, cb: Callable) -> void:
	var kind = str(command.kind)
	var id = str(command.id)
	var p: Dictionary = command.get("params", {})
	var main = _main()
	if p.get("breakthrough_prepare", false) and (not _breakthrough_enabled() or (kind in ["world_explore", "world_harvest"] and not policy.get("breakthrough_auto_find", true))):
		_done(id, false, "突破准备子开关已关闭")
		return
	var marker = int(p.get("marker_id", 0))
	match kind:
		"resource_pack":
			var chosen: Dictionary = {}
			var packing = _resource_pack_snapshot()
			for recipe in packing.recipes:
				if recipe.input_kind == p.get("kind") and recipe.input_id == p.get("material_id") and recipe.size == p.get("size"):
					chosen = recipe
			var count = int(p.get("count", 0))
			if _locked(str(p.get("kind", "")), int(p.get("material_id", 0))) or _trade_protected(str(p.get("kind", "")), int(p.get("material_id", 0))) or chosen.is_empty() or count < 1 or count > mini(int(packing.remaining), int(policy.get("resource_pack_batch", 1))):
				_done(id, false, "交易保护开启、打包原料无效或每日额度不足")
			elif int(chosen.size) != int(policy.get("resource_pack_size", "4")) or (not policy.get("resource_pack_materials", []).is_empty() and not int(chosen.input_id) in policy.resource_pack_materials) or int(chosen.unbound_count)-count*int(chosen.cost) < (int(policy.get("resource_pack_reserve", 100)) + int(_budget().reserved(self).get("%s:%d" % [chosen.input_kind, int(chosen.input_id)], 0))):
				_done(id, false, "打包参数或原料保留量已变化")
			else:
				api.storage(cb, "pack", {"entries": [{"kind":chosen.input_kind, "id":chosen.input_id, "size":chosen.size, "count":count}], "request_id":id})
		"world_sync": api.cave_world_status(cb)
		"world_explore":
			var w = _world_snapshot()
			if not pending_world_event.is_empty() or _world_map_full(w):
				_done(id, false, "等待处理奇遇或腾出地图位置")
				return
			if int(w.daily_count) >= int(policy.get("world_daily_limit", 50)):
				_done(id, false, "已达到最新设置的今日探索上限")
				return
			var options = {"request_id": id}
			var mode = "" if int(w.free_remaining) > 0 else ("mirror" if p.get("use_mirror", false) else "rumor")
			if not mode.is_empty():
				var prop: Dictionary = w[mode]
				if not policy.get("world_use_" + mode, false) or not prop.unlocked or int(prop.count) - int(prop.cost) < int(policy.get("world_prop_reserve", 1)) or not prop.bound_only_safe:
					_done(id, false, "探索道具已到保留值或来源不符合保护设置")
					return
				options["use_" + mode] = true
				if mode == "mirror":
					var target = str(policy.get("world_mirror_target", "auto"))
					if target == "auto": target = _budget().mirror_target(self)
					options["target_type"] = target if target in ["herb", "material", "relic", "stronghold", "spring", "forge"] else "material"
			var execution = {"exploration_mode": "free" if mode.is_empty() else mode, "exploration_day": _exploration_day()}
			var exploration_command = command.duplicate(true)
			exploration_command["execution"] = execution
			api.cave_explore(func(response: Dictionary, ok: bool): _callback(response, ok, exploration_command), options)
		"world_harvest", "world_points", "world_prune":
			var point = _find_point(marker)
			var type = str(point.get("type", ""))
			if point.is_empty() or point.get("is_current", false):
				_done(id, false, "地图目标已变化")
				return
			if kind == "world_harvest" and type in ["ordinary", "herb", "material"]:
				api.cave_world_harvest(cb, marker)
			elif kind == "world_points" and (type in ["spring", "stronghold"] or (type == "relic" and policy.get("world_relics", true))):
				if type == "spring" and gm.character.exp_current >= cfg.get_exp_needed(gm.character.level):
					_done(id, false, "修为已满，等待升级或突破后再吸取灵泉")
					return
				var choice = -1
				var candidates: Array = stronghold_choices.get(str(marker), [])
				if not candidates.is_empty():
					choice = 0
					for index in candidates.size():
						if _reward_score(candidates[index]) > _reward_score(candidates[choice]): choice = index
				api.cave_world_point_action(cb, marker, choice)
			elif kind == "world_prune" and policy.get("world_prune", true) and (type == "empty" or _world_point_expired(point)):
				if not _world_map_full(_world_snapshot()):
					_done(id, false, "地图仍有探索空位，已取消旧清理计划")
					return
				api.cave_world_delete(cb, marker)
			else: _done(id, false, "目标类型不适合此操作")
		"world_events":
			if int(p.get("event_id", 0)) <= 0 or str(pending_world_event.get("type", "")) not in ["cultivator_help", "senior_cultivator"] or int(pending_world_event.get("event_id", 0)) != int(p.get("event_id", 0)) or p.get("action", "") != "close": _done(id, false, "奇遇目标已变化")
			else: api.cave_world_event_action(cb, int(p.event_id), "close")
		"gongfa_activate":
			var gid = int(p.get("gongfa_id", 0))
			var gu = main.get("gongfa_ui")
			var gd = load("res://scripts/data/gongfa_data.gd")
			if gu == null or gu._is_activated(gid) or gu._page_count(gid, 0) <= 0 or not gd.element_match(gd.get_gongfa_by_id(gid), gm.character.element) or not _gongfa_bound_safe(gid, 0):
				_done(id, false, "功法未满足激活条件、绑定预算不足或页受保护")
			else: api.gongfa_activate(cb, gid)
		"gongfa_slots":
			var slots: Array = p.get("slots", [])
			var valid = slots.size() == 3
			var seen: Dictionary = {}
			var gd = load("res://scripts/data/gongfa_data.gd")
			for gid_value in slots:
				var gid = int(gid_value)
				if gid == 0: continue
				var gf = gd.get_gongfa_by_id(gid)
				if seen.has(gid) or not gd.is_active(gf) or not gd.element_match(gf, gm.character.element) or not gm.character.gongfa.get("cultivated", {}).has(str(gid)): valid = false
				seen[gid] = true
			if valid: api.gongfa_set_active_slots(cb, slots)
			else: _done(id, false, "主动功法组合无效")
		"gongfa_accelerate":
			var gid = int(p.get("gongfa_id", 0))
			var gu = main.get("gongfa_ui")
			var tr = gu._training_of(gid) if gu != null else {}
			var target = int(tr.get("target", 0))
			if tr.get("state", "") != "running" or gu._page_count(gid, target) <= int(policy.get("gongfa_accelerate_reserve", 2)) or not _gongfa_bound_safe(gid, target):
				_done(id, false, "没有可用于加速的多余功法页")
			else: api.gongfa_accelerate_training(cb, gid, target)
		"pill", "alchemy":
			var pid = int(p.get("pill_id", 0))
			var pd = load("res://scripts/data/pill_data.gd")
			var pill = pd.get_pill_info(pid)
			var preparing = p.get("breakthrough_prepare", false) == true and not _breakthrough_effect(pill).is_empty()
			if preparing and (not _breakthrough_pill_needed(pill) or not policy.get("breakthrough_auto_use" if kind == "pill" else "breakthrough_auto_craft", true) or (kind == "pill" and not gm.needs_breakthrough())):
				_done(id, false, "突破丹准备条件已变化或子开关已关闭")
				return
			if (not preparing and not _breakthrough_effect(pill).is_empty()) or (not preparing and not _pill_useful(pill)):
				_done(id, false, "丹药效果已生效或当前不需要")
				return
			if kind == "pill":
				var have = 0 if _locked("pill", pid) else (_bound_count("pill", pid) if _trade_protected("pill", pid) else _owned_count("pill", pid))
				if have <= int(policy.get("pill_reserve", 0)): _done(id, false, "丹药已到保留值")
				else: api.alchemy(cb, "use", pid, 0, 1, id, 1 if _trade_protected("pill", pid) else -1)
			else:
				var index = int(p.get("recipe_index", -1))
				var recipes: Array = pill.get("recipes", [])
				var count = 1 if preparing else clampi(int(p.get("count", 1)), 1, int(policy.get("alchemy_batch", 1)))
				var requirements: Array = pd.get_recipe_materials(pill, index).duplicate(true)
				var reserve = int(policy.get("breakthrough_material_reserve", 0)) if preparing else int(policy.get("alchemy_reserve", 5))
				if not preparing and _owned_count("pill", pid) > int(policy.get("pill_reserve", 0)):
					_done(id, false, "已有丹药库存，等待使用后再炼制")
					return
				if preparing:
					var recipe_keys: Array = requirements.map(func(row): return "%s:%d" % [row.get("kind", "material"), int(row.id)])
					for req in _breakthrough_context().info.get("materials", []):
						if "%s:%d" % [req.get("kind", "material"), int(req.id)] in recipe_keys: requirements.append(req)
					var have = 0 if _locked("pill", pid) else (_bound_count("pill", pid) if _trade_protected("pill", pid) else _owned_count("pill", pid))
					if have > int(policy.get("pill_reserve", 0)):
						_done(id, false, "已有可用突破丹，等待服用后再炼制")
						return
				if index < 0 or index >= recipes.size() or (preparing and int(recipes[index].get("realm", -1)) != cfg.get_realm_id_by_level(gm.character.level)) or int(recipes[index].get("realm", 0)) > cfg.get_realm_id_by_level(gm.character.level) or not _requirements_available(requirements, count, reserve, preparing, "alchemy"):
					_done(id, false, "炼丹配方未解锁或材料已到保留值")
				else: api.alchemy(cb, "craft", pid, index, count, id, -1)
		"material_synth":
			var mid = int(p.get("material_id", 0))
			var count = int(p.get("count", 0))
			var valid = false
			for recipe in _material_synthesis_snapshot():
				if recipe.input_id == mid and recipe.unlocked and count >= 1 and count <= int(policy.get("material_synth_batch", 5)) and int(recipe.count) - int(recipe.required_count) * count >= int(policy.get("material_synth_reserve", 20)) and recipe.bound_only_safe and _requirements_available([{"kind":"material", "id":mid, "count":int(recipe.required_count)}], count, int(policy.get("material_synth_reserve",20)), false, "material_synth"): valid = true
			if valid and policy.get("material_synth_demand_only", true):
				for recipe in _material_synthesis_snapshot():
					if int(recipe.input_id) == mid and count > _material_upgrade_deficit(int(recipe.output_id)): valid = false
			if valid: api.synth_upgrade_material(cb, mid, count)
			else: _done(id, false, "材料合成条件已变化或触及保留数量")
		"furnace_absorb":
			if gm.get_cave_furnace_exp_pool() >= int(policy.get("furnace_min_exp", 1)) and gm.character.exp_current < cfg.get_exp_needed(gm.character.level): api.cave_furnace_absorb(cb)
			else: _done(id, false, "暂无可领取的炉鼎经验或当前修为已满")
		"home_relocate":
			var point = _find_point(marker)
			var score = _home_score(point.get("features", []))
			var current = _home_score(gm.cave.get("active_features", []))
			if gm.is_captured_as_slave() or not _home_safe(point) or score <= current + maxf(0.01, absf(current) * float(policy.get("home_min_gain", 5)) / 100.0) or not _requirements_available([{"kind": "material", "id": 4001, "count": 1}], 1, int(policy.get("home_reserve", 1))):
				_done(id, false, "迁居增益不足、洞府有不明特性或迁居令已到保留值")
			else: api.cave_world_relocate(cb, marker)
		"refine", "world_forge": _execute_refine(command, cb)
		"resource_realm": _execute_resource_realm(command)
		"realm_challenge":
			var point = _find_point(marker)
			if point.get("type", "") != "breakthrough_realm" or main.get("cave_world_ui") == null:
				_done(id, false, "突破秘境目标已变化")
			elif int(point.get("required_level", 0)) > gm.character.level or (not policy.get("realm_allow_danger", false) and load("res://scripts/ui/ui_cave_world_view.gd")._realm_difficulty(point) == "DANGER"):
				_done(id, false, "突破秘境难度或等级不符合当前设置")
			else:
				_start_world_external(command, "breakthrough_realm")
		_: _done(id, false, "未知操作")

func _reward_score(reward: Dictionary) -> float:
	var quality_order = ["common", "fine", "rare", "epic", "legend", "myth", "perfect", "innate", "treasure"]
	return quality_order.find(str(reward.get("quality", reward.get("rarity", "common")))) * 100.0 + float(reward.get("count", 1))

func _prop_snapshot(mid: int, cost: int) -> Dictionary:
	return {"id": mid, "count": _owned_count("material", mid), "cost": cost,
		"bound_only_safe": _requirements_bound_safe([{"kind": "material", "id": mid, "count": cost}])}

func _target_token(point: Dictionary) -> String:
	var identity: Array = []
	for key in ["marker_id", "id", "type", "steamid", "target_steamid", "target_name", "target_level", "world_id", "coord_x", "coord_y"]:
		identity.append(str(point.get(key, "")))
	return JSON.stringify(identity).sha256_text()

func _partner_snapshot() -> Dictionary:
	var raw: Dictionary = gm.partner
	var other: Dictionary = raw.get("partner", {}) if raw.get("partner") is Dictionary else {}
	var rescue_cfg: Dictionary = cfg.get_partner_config()
	var info = {"synced_at": partner_synced_at, "has_partner": raw.get("has_partner", false),
		"target": str(other.get("steamid", "")), "name": str(other.get("name", "")), "daily": raw.get("daily", {}),
		"cooldown_until": raw.get("cooldown_until", 0), "capture": other.get("furnace", {}) if other.get("furnace") is Dictionary else {},
		"rescue": _prop_snapshot(int(rescue_cfg.get("rescue_talisman_id", 4004)), int(rescue_cfg.get("rescue_talisman_count", 2)))}
	# Do not export private chat or unrelated profile data.
	for key in ["received_invites", "sent_invites"]:
		info[key] = []
		for invite in raw.get(key, []):
			if invite is Dictionary:
				info[key].append({"id": int(invite.get("id", 0)), "target": str(invite.get("player", {}).get("steamid", "")), "expires_at": int(invite.get("expires_at", 0))})
	return info

func _assessment_ok(value: String, threshold: String) -> bool:
	return value == "碾压" or (threshold in ["advantage", "close"] and value == "优势") or (threshold == "close" and value == "相近")

func _social_response(response: Dictionary, ok: bool, command: Dictionary, key: String) -> void:
	var answer: Dictionary = response.get(key, {}) if response.get(key) is Dictionary else {}
	var success = ok and answer.get("success") == true
	if command.kind == "social_sync" and success: partner_synced_at = int(Time.get_unix_time_from_system() * 1000)
	if command.kind == "bounty_sync" and success:
		bounty_cache = {"synced_at": int(Time.get_unix_time_from_system() * 1000), "daily_claims_used": answer.get("daily_claims_used", 0), "daily_claim_limit": answer.get("daily_claim_limit", 0), "events": []}
		for event in answer.get("events", []):
			if not event is Dictionary: continue
			var clean: Dictionary = {}
			for field in ["id", "event_type", "power_assessment", "target_level", "is_owner", "busy", "remaining_uses", "expires_at"]:
				if event.has(field): clean[field] = event[field]
			clean["target_token"] = _target_token(event)
			bounty_cache.events.append(clean)
	if command.kind == "slave_escape" and command.params.action == "escape_free":
		success = success and answer.get("escaped") == true
	if command.kind in ["partner_practice", "partner_social", "partner_rescue"] and success:
		partner_synced_at = int(Time.get_unix_time_from_system() * 1000)
	var detail = "游戏已确认操作" if success else _failure_detail(response, answer, "未确认成功")
	if command.kind == "slave_escape" and ok and answer.get("success") == true and answer.get("escaped") == false:
		detail = "普通逃脱失败，本次囚禁不再重复尝试"
	_done(str(command.id), success, detail, {} if success else {"failure": _failure_metadata(response, answer)})

func _execute_social(command: Dictionary) -> void:
	var kind = str(command.kind)
	var p: Dictionary = command.get("params", {})
	var id = str(command.id)
	var now = int(Time.get_unix_time_from_system() * 1000)
	var cb = func(response: Dictionary, ok: bool): _social_response(response, ok, command, "partner_result" if kind.begins_with("partner_") or kind == "social_sync" else "cave_result")
	match kind:
		"social_sync": api.partner(cb, "status", {})
		"partner_practice":
			var partner = _partner_snapshot()
			var daily: Dictionary = partner.daily
			if not partner.has_partner or gm.is_captured_as_slave() or int(daily.get("practice_used", 0)) >= mini(int(daily.get("practice_limit", 0)), int(policy.get("partner_practice_limit", 10))):
				_done(id, false, "双修次数已满、无道侣或当前被捕")
			else: api.partner(cb, "practice", {"operation_id": api.make_operation_id("practice")})
		"partner_social":
			var target = str(policy.get("partner_target", ""))
			var action = str(p.get("action", ""))
			var raw: Dictionary = gm.partner
			if target.is_empty() or str(p.get("target", "")) != target or raw.get("has_partner", false) or int(raw.get("cooldown_until", 0)) > now or social_attempts.has(target):
				_done(id, false, "结缘目标已变化、冷却中或本次已提交")
			elif action == "invite" and policy.get("partner_auto_invite", false):
				for row in raw.get("sent_invites", []):
					if str(row.get("player", {}).get("steamid", "")) == target and int(row.get("expires_at", 0)) > now:
						_done(id, false, "指定目标已有待处理邀请")
						return
				social_attempts[target] = true
				api.partner(cb, "invite", {"target_steamid": target})
			elif action == "accept_invite" and policy.get("partner_auto_accept", false):
				for row in raw.get("received_invites", []):
					if int(row.get("id", 0)) == int(p.get("invite_id", 0)) and str(row.get("player", {}).get("steamid", "")) == target and int(row.get("expires_at", 0)) > now:
						social_attempts[target] = true
						api.partner(cb, action, {"invite_id": int(row.id)})
						return
				_done(id, false, "指定邀请已失效")
			else: _done(id, false, "定向邀请或接受开关未开启")
		"partner_rescue":
			var partner = _partner_snapshot()
			var captured: Dictionary = partner.capture
			if not partner.has_partner or gm.is_captured_as_slave() or captured.is_empty() or int(captured.get("expires_at", 0)) <= now or str(partner.target) != str(p.get("target", "")) or str(captured.get("capture_id", "")) != str(p.get("capture_id", "")):
				_done(id, false, "道侣或被捕状态已变化")
				return
			var mode = str(policy.get("partner_rescue_mode", "talisman"))
			if p.get("action") == "rescue_talisman" and mode != "battle":
				var prop: Dictionary = partner.rescue
				if _requirements_available([{"kind": "material", "id": int(prop.id), "count": int(prop.cost)}], 1, int(policy.get("rescue_prop_reserve", 1))):
					api.partner(cb, "rescue_talisman", {"operation_id": api.make_operation_id("rescue_talisman")})
				else: _done(id, false, "脱身符不足、可交易或已到保留量")
			elif p.get("action") == "rescue_start" and mode != "talisman" and gm.character.get_injury_stacks() <= int(policy.get("pvp_max_injury", 0)):
				_start_external(command, "partner_rescue", {})
			else: _done(id, false, "解救方式或伤势不符合设置")
		"player_capture", "player_occupy":
			var point = _find_point(int(p.get("marker_id", 0)))
			if not str(point.get("type", "")) in ["cultivator", "player", "robot"] or _target_token(point) != str(p.get("target_token", "")) or gm.is_captured_as_slave() or int(point.get("expires_at", 0)) <= now or gm.character.get_injury_stacks() > int(policy.get("pvp_max_injury", 0)) or not _assessment_ok(str(point.get("power_assessment", "")), str(policy.get("pvp_assessment", "advantage"))):
				_done(id, false, "目标、保护期、战力或伤势已变化")
				return
			if kind == "player_capture":
				if not gm.is_feature_unlocked("furnace") or point.get("furnace_unlocked", true) != true or int(point.get("furnace_protected_until", 0)) > now or gm.get_cave_furnace_slaves().size() >= int(gm.cave.get("furnace_slot_count", 1)):
					_done(id, false, "目标受保护、未解锁或炉鼎已满")
					return
			else:
				var current = _home_score(gm.cave.get("active_features", []))
				if not _occupy_home_safe(point) or _home_score(point.get("features", [])) <= current + maxf(0.01, absf(current) * float(policy.get("occupy_min_gain", 5)) / 100.0):
					_done(id, false, "占领洞府增益不足或有不明特性")
					return
			_start_world_external(command, "capture" if kind == "player_capture" else "occupy")
		"bounty_sync": api.cave_bounty_list(cb)
		"bounty_claim":
			for event in bounty_cache.get("events", []):
				if int(event.get("id", 0)) != int(p.get("event_id", 0)): continue
				if event.get("target_token", "") != p.get("target_token", "") or gm.is_captured_as_slave() or event.get("is_owner", false) or event.get("busy", false) or int(event.get("remaining_uses", 0)) <= 0 or int(event.get("expires_at", 0)) <= now or (event.get("event_type") != "monster_clear" and not policy.get("bounty_allow_players", false)) or not _assessment_ok(str(event.get("power_assessment", "")), str(policy.get("bounty_assessment", "advantage"))) or gm.character.get_injury_stacks() > int(policy.get("pvp_max_injury", 0)) or int(bounty_cache.get("daily_claims_used", 0)) >= int(bounty_cache.get("daily_claim_limit", 0)):
					_done(id, false, "悬赏目标、剩余次数或战力已变化")
				else: _start_external(command, "bounty", {"event_id": int(event.id)})
				return
			_done(id, false, "悬赏已失效，等待列表同步")
		"slave_escape", "bounty_publish":
			var captured: Dictionary = gm.cave.get("captured_as_slave", {}) if gm.cave.get("captured_as_slave") is Dictionary else {}
			var cid = str(captured.get("capture_id", ""))
			var action = str(p.get("action", "bounty_publish"))
			var attempt_key = cid + ":" + action
			if not gm.is_captured_as_slave() or cid.is_empty() or cid != str(p.get("capture_id", "")) or capture_attempts.has(attempt_key):
				_done(id, false, "被捕状态已变化或本次已提交")
				return
			if action == "bounty_publish":
				var master = str(captured.get("master_steamid", ""))
				if not policy.get("bounty_publish_captured", false) or master.is_empty() or master.sha256_text() != str(p.get("master_token", "")) or not _requirements_available([{"kind": "material", "id": 4002, "count": 1}], 1, int(policy.get("bounty_prop_reserve", 1))):
					_done(id, false, "悬赏开关、主人或悬赏令保护条件不符")
				else:
					capture_attempts[attempt_key] = true
					api.cave_bounty_publish(cb, master)
			elif action == "escape_talisman" and policy.get("escape_mode", "talisman_first") != "free_only":
				if _requirements_available([{"kind": "material", "id": 4004, "count": 1}], 1, int(policy.get("escape_prop_reserve", 0))):
					capture_attempts[attempt_key] = true
					api.cave_slave_escape_talisman(cb)
				else: _done(id, false, "脱身符不足、可交易或到保留量")
			elif action == "escape_free" and policy.get("escape_mode", "talisman_first") != "talisman_only" and not captured.get("attempted_escape", false):
				capture_attempts[attempt_key] = true
				api.cave_slave_escape(cb)
			else: _done(id, false, "本次囚禁已尝试普通逃脱或方式未开启")
		"multiplayer_realm": _execute_multiplayer(command)

func _start_world_external(command: Dictionary, action: String) -> void:
	_start_external(command, "world_action", {"marker_id": int(command.params.get("marker_id", 0)), "action": action})

func _start_external(command: Dictionary, context_kind: String, context: Dictionary) -> void:
	var main = _main()
	if not external.is_empty() or main == null or main.battle_flow.in_combat:
		_done(str(command.id), false, "另一场战斗尚未结算")
		return
	var original = Callable(main, "_on_external_battle_ended")
	if main.battle_flow.external_battle_ended.is_connected(original):
		main.battle_flow.external_battle_ended.disconnect(original)
	if not main.battle_flow.external_battle_ended.is_connected(_external_ended):
		main.battle_flow.external_battle_ended.connect(_external_ended)
	context["kind"] = context_kind
	context["assistant_id"] = str(command.id)
	external = {"id": str(command.id), "kind": str(command.kind), "start": Time.get_ticks_msec(), "context": context, "settling": false}
	var cb = func(response: Dictionary, ok: bool): _external_started(response, ok, str(command.id))
	if context_kind == "partner_rescue": api.partner(cb, "rescue_start", {"operation_id": api.make_operation_id("rescue_start")})
	elif context_kind == "bounty": api.cave_bounty_claim(cb, int(context.event_id))
	else: api.cave_world_player_action(cb, int(context.marker_id), str(context.action))

func _external_started(response: Dictionary, ok: bool, id: String) -> void:
	if str(external.get("id", "")) != id: return
	var key = "partner_result" if external.context.kind == "partner_rescue" else "cave_result"
	var answer: Dictionary = response.get(key, {})
	var battle: Dictionary = answer.get("battle", {})
	if not ok or answer.get("success") != true or (external.context.kind != "partner_rescue" and answer.get("battle_pending") != true) or str(battle.get("battle_id", "")).is_empty():
		_done(id, false, _failure_detail(response, answer, "战斗启动未确认"), {"failure": _failure_metadata(response, answer)})
		external.clear()
		return
	external["battle_id"] = str(battle.battle_id)
	_main()._on_external_battle_requested(battle, external.context)

func _external_ended(local_result: Dictionary, context: Dictionary) -> void:
	var main = _main()
	if main == null: return
	if str(context.get("assistant_id", "")).is_empty():
		# Manual battles keep the original settlement handler.
		main._on_external_battle_ended(local_result, context)
		return
	if external.is_empty() or str(context.get("assistant_id", "")) != str(external.get("id", "")): return
	if external.get("settling", false) or str(context.get("battle_id", "")) != str(external.get("battle_id", "")): return
	external["settling"] = true
	var id = str(external.id)
	_submit_external_settlement(id, local_result, context)

func _submit_external_settlement(id: String, local_result: Dictionary, context: Dictionary) -> void:
	if str(external.get("id", "")) != id or external.get("submission_pending", false): return
	external["submission_pending"] = true
	external["local_result"] = local_result.duplicate(true)
	external["settlement_context"] = context.duplicate(true)
	var battle_id = str(external.battle_id)
	var outcome = "win" if local_result.get("win", false) else "lose"
	var cb = func(response: Dictionary, ok: bool): _external_settled(response, ok, id, local_result, context)
	if context.kind == "partner_rescue": api.partner(cb, "rescue_complete", {"battle_id": battle_id, "result": outcome})
	elif context.kind == "bounty": api.cave_bounty_claim(cb, int(context.event_id), "complete", battle_id, outcome)
	else: api.cave_world_player_action(cb, int(context.marker_id), str(context.action), "complete", battle_id, outcome)

func _external_settled(response: Dictionary, ok: bool, id: String, local_result: Dictionary, context: Dictionary) -> void:
	if str(external.get("id", "")) != id: return
	external["submission_pending"] = false
	# HTTP 429 explicitly rejects this submission. Honor its backoff before
	# retrying the same battle; ambiguous transport failures still stop safely.
	if not ok and int(response.get("http_code", 0)) == 429 and int(external.get("settlement_retries", 0)) < 3:
		var attempt = int(external.get("settlement_retries", 0)) + 1
		var delay = maxf(float(response.get("retry_after_seconds", 0)), minf(30.0, pow(2.0, attempt)))
		external["settlement_retries"] = attempt
		external["retry_at"] = Time.get_ticks_msec() + int(maxf(2.0, delay) * 1000.0)
		return
	var key = "partner_result" if context.kind == "partner_rescue" else "cave_result"
	var answer: Dictionary = response.get(key, {})
	var confirmed = ok and answer.get("success") == true and str(answer.get("result", "")) in ["win", "lose"] and str(answer.get("battle_id", external.get("battle_id", ""))) == str(external.get("battle_id", ""))
	var won = confirmed and answer.result == "win"
	var main = _main()
	if main != null:
		if context.kind == "partner_rescue": main.battle_flow.finish_external_battle(won, str(answer.get("reason", "道侣解救结算")), "")
		else: main._finish_external_battle_settlement(answer if confirmed else {"success": false, "reason": "服务器结算未确认"}, local_result, context)
	if context.kind == "bounty": bounty_cache.clear()
	_done(id, won, "战斗胜利已由服务器确认" if won else "战斗失败，等待成长后重试" if confirmed else "战斗结果未确认，自动任务已暂停", {"battle": true, "won": won, "unconfirmed": not confirmed, "failure": {} if confirmed else _failure_metadata(response, answer)})
	external.clear()

func _check_external() -> void:
	if external.is_empty(): return
	if int(external.get("retry_at", 0)) > 0 and Time.get_ticks_msec() >= int(external.retry_at):
		external["retry_at"] = 0
		_submit_external_settlement(str(external.id), external.local_result, external.settlement_context)
	if external.is_empty(): return
	if Time.get_ticks_msec() - int(external.start) > 300000:
		_done(str(external.id), false, "外部战斗超时未确认，自动任务已暂停", {"unconfirmed": true})
		external.clear()

func _multiplayer_snapshot(main) -> Dictionary:
	var suspended = cfg.is_multiplayer_realm_suspended()
	var result = {"suspended": suspended, "enabled": not suspended and cfg.get_value("multiplayer_realm", "enabled", false) == true, "active": false, "escape_supported": false}
	if not result.enabled: return result
	var mode = main.get("_realm_mode")
	if mode != null and mode.view != null: result.escape_supported = mode.view.has_method("_can_escape")
	if mode != null and mode.view != null and (mode.active or not str(mode.get("_running_id") if mode.get("_running_id") != null else "").is_empty()):
		var view = mode.view
		var data: Dictionary = view.data
		var resources: Dictionary = view._combat_resources if data.get("state") == "in_combat" else data.get("panel", {}).get("resources", {})
		var event: Dictionary = data.get("exploration", {}).get("event", {})
		var options: Array = []
		for row in event.get("options", []):
			if row is Dictionary and not row.get("disabled", false) and int(event.get("due_at", 0)) > view._now(): options.append(str(row.get("id", "")))
		result.merge({"active": true, "entry_id": view.entry_id, "state": data.get("state", ""),
			"stale": view._stale or Time.get_ticks_msec() - int(view._received_tick) >= 5000, "command_pending": view._command_pending or not realm_command.is_empty() or (view.get("_command_watch") != null and not str(view.get("_command_watch")).is_empty()) or (view.get("_queued_intent") is Dictionary and not view.get("_queued_intent").is_empty()),
			"can_extract": data.get("panel", {}).get("can_extract", false), "can_escape": view._can_escape() if view.has_method("_can_escape") else false, "battle_id": view._battle_id,
			"hp_percent": 100.0 * float(resources.get("hp", 0)) / maxf(1.0, float(resources.get("max_hp", 1))),
			"elapsed_seconds": maxi(0, int((view._now() - int(data.get("entered_at", view._now()))) / 1000)),
			"event": {"id": str(event.get("id", "")), "options": options}})
	else:
		result["prepared"] = not mp_prepare.is_empty() and Time.get_ticks_msec() - mp_prepared_at < int(policy.get("mp_interval", 60)) * 1000
		result["available"] = mp_prepare.get("available", false) and mp_prepare.get("inventory_ready", false) and str(mp_prepare.get("blocked_reason", "")).is_empty()
		result["free_entries"] = maxi(0, int(mp_prepare.get("free_entry", {}).get("remaining", 0)))
		result["blocked_reason"] = str(mp_prepare.get("blocked_reason", ""))
		result["realm_key"] = str(mp_prepare.get("realm_key", ""))
		result["key_item"] = str(mp_prepare.get("key_item", ""))
		result["key_count"] = 0
		for item in mp_prepare.get("items", []):
			if item is Dictionary and item.get("role") == "key" and item.get("item_key") == mp_prepare.get("key_item"):
				result.key_count += int(item.get("quantity", 0))
	return result

func _execute_multiplayer(command: Dictionary) -> void:
	var id = str(command.id)
	var p: Dictionary = command.params
	var main = _main()
	var current = _multiplayer_snapshot(main)
	if not current.get("enabled", false):
		_done(id, false, "原游戏多人秘境暂停或未开放，未提交请求")
		return
	var action = str(p.get("action", ""))
	if action == "prepare":
		api.multiplayer_realm(func(response: Dictionary, ok: bool):
			mp_prepare = response.get("multiplayer_realm", {}) if ok else {}
			mp_prepared_at = Time.get_ticks_msec()
			_done(id, ok and not mp_prepare.is_empty(), "秘境准备状态已同步" if ok else "秘境准备未确认")
		, "prepare", {})
	elif action == "enter":
		var parts = str(current.get("key_item", "")).split(":")
		var key_allowed = parts.size() == 2 and parts[0] in ["material","herb","pill"] and parts[1].is_valid_int()
		if key_allowed: key_allowed = _requirements_bound_safe([{ "kind": parts[0], "id": int(parts[1]), "count": 1 }]) and _budget().available(self, parts[0], int(parts[1])) >= 1
		if not policy.get("mp_auto_enter", false) or (not key_allowed and int(current.get("free_entries", 0)) <= 0) or not current.get("prepared", false) or not current.get("available", false) or (int(current.get("key_count", 0)) <= 0 and int(current.get("free_entries", 0)) <= 0) or current.get("realm_key") != p.get("realm_key"):
			_done(id, false, "秘境未开放、钥匙不足或当前保护设置禁止使用钥匙")
			return
		api.multiplayer_realm(func(response: Dictionary, ok: bool):
			var answer: Dictionary = response.get("multiplayer_realm", {})
			var accepted = ok and answer.get("success") == true and not str(answer.get("id", "")).is_empty()
			if accepted:
				if str(answer.get("state", "")) in ["reserving", "cancelling"]: main._realm_mode.preparation.resume_admission(answer)
				else: main._realm_mode.enter(answer)
			mp_prepare.clear()
			_done(id, accepted, "入场已确认" if accepted else "入场未确认")
		, "enter", {"realm_key": p.realm_key, "request_id": id, "carry": [], "strategy": mp_prepare.get("strategy_defaults", {})})
	elif current.get("active", false) and str(p.get("entry_id", "")) == str(current.get("entry_id", "")):
		var view = main._realm_mode.view
		var valid = not current.stale and not current.command_pending
		if action == "extract": valid = valid and current.can_extract and (current.hp_percent <= float(policy.get("mp_extract_hp", 40)) or current.elapsed_seconds >= int(policy.get("mp_max_seconds", 900)))
		elif action == "battle_escape": valid = valid and current.can_escape and current.battle_id == p.get("battle_id") and current.hp_percent <= float(policy.get("mp_escape_hp", 25))
		elif action == "choose": valid = valid and current.state == "choosing" and current.event.id == p.get("event_id") and current.event.options.has(str(p.get("option_id", ""))) and str(p.get("option_id", "")) == str(policy.get("mp_event_option", ""))
		else: valid = false
		if not valid:
			_done(id, false, "秘境状态已变化或动作条件不符")
			return
		# Native command owns tickets, idempotency IDs and unresolved result checks.
		var payload = p.duplicate(true)
		payload.erase("action")
		payload.erase("entry_id")
		realm_command = {"id": id, "action": action, "entry_id": str(current.entry_id), "request_id": "", "start": Time.get_ticks_msec()}
		view._command(action, payload)
		var operation = view.get("_operation_query")
		if operation is Dictionary: realm_command["request_id"] = str(operation.get("request_id", ""))
		if str(realm_command.get("request_id", "")).is_empty() and (not view.get("_queued_intent") is Dictionary or view.get("_queued_intent").is_empty()):
			realm_command.clear()
			_done(id, false, "原生秘境未接受该动作，等待刷新")
	else: _done(id, false, "秘境场次已变化")

func _check_realm_command() -> void:
	if realm_command.is_empty(): return
	if Time.get_ticks_msec() - int(realm_command.start) > 300000:
		var id = str(realm_command.id)
		realm_command.clear()
		_done(id, false, "秘境操作五分钟未确认，等待原生核对，未重复提交", {"unconfirmed": true})

func _observe_realm_command(url: String, body: Dictionary, response: Dictionary, ok: bool) -> void:
	if realm_command.is_empty() or url != "/api/multiplayer_realm" or not ok: return
	var operation = body.get("operation", {})
	var direct = str(body.get("action", "")) == str(realm_command.action) and str(body.get("entry_id", "")) == str(realm_command.entry_id)
	if direct and str(realm_command.request_id).is_empty(): realm_command.request_id = str(body.get("request_id", ""))
	var matches = direct and not str(realm_command.request_id).is_empty() and str(body.get("request_id", "")) == str(realm_command.request_id)
	var queried = operation is Dictionary and not str(realm_command.request_id).is_empty() and str(operation.get("request_id", "")) == str(realm_command.request_id) and str(body.get("entry_id", "")) == str(realm_command.entry_id)
	if not matches and not queried: return
	var answer = response.get("multiplayer_realm", {})
	if not answer is Dictionary: return
	var receipt = answer.get("operation_status", {}) if queried else {}
	var confirmed = receipt is Dictionary and receipt.get("status") in ["confirmed", "superseded"]
	var final = matches and answer.has("success") and not bool(answer.get("pending", false))
	if not confirmed and not final: return
	var accepted = bool(answer.get("success", false)) if final else receipt.get("status") == "confirmed" and (not receipt.get("result") is Dictionary or receipt.result.get("accepted", true) != false)
	var id = str(realm_command.id)
	realm_command.clear()
	_done(id, accepted, "秘境动作已由服务器确认" if accepted else "秘境动作未执行或已失效")

func _flow_evidence():
	return load(get_script().resource_path.get_base_dir().path_join("growth_evidence.gd"))

func _budget():
	return load(get_script().resource_path.get_base_dir().path_join("resource_budget.gd"))

func _resource_realm_snapshot(main) -> Dictionary:
	var data: Dictionary = gm.get("resource_realm") if gm.get("resource_realm") is Dictionary else {}
	var portal: Dictionary = data.get("portal", {}) if data.get("portal") is Dictionary else {}
	var run: Dictionary = data.get("run", {}) if data.get("run") is Dictionary else {}
	var mode = main.get("_resource_realm_mode") if main != null else null
	var token_id = int(cfg.get_value("resource_realm", "token_id", 4204))
	var cost = int(cfg.get_value("resource_realm", "token_cost", 1))
	var remaining: Dictionary = data.get("free_remaining", {})
	var token_info = _prop_snapshot(token_id, cost)
	var result = {"enabled": cfg.get_value("resource_realm", "enabled", false) == true and int(gm.character.level) >= int(cfg.get_value("resource_realm", "min_level", 15)),
		"portal": {"id": str(portal.get("id", "")), "type": str(portal.get("type", ""))},
		"active": not run.is_empty() and str(run.get("state", "")) != "finished",
		"run": {"id": str(run.get("id", "")), "state": str(run.get("state", "")), "ends_at": run.get("ends_at", 0), "type": run.get("type", "")},
		"free_remaining": int(remaining.get("shared", remaining.get(str(portal.get("type", "")), 0))),
		"token": token_info, "stale": false, "command_pending": false, "battle_playing": false}
	if mode != null:
		result.stale = Time.get_ticks_msec() - int(mode._received) >= 35000
		result.command_pending = mode._pending or mode._polling
		result.battle_playing = mode.view != null and (mode.view.battle_flow.in_combat or mode.view.has_pending_battle())
	return result

func _execute_resource_realm(command: Dictionary) -> void:
	var id = str(command.id)
	var p: Dictionary = command.params
	var current = _resource_realm_snapshot(_main())
	var action = str(p.get("action", ""))
	if not current.enabled or current.command_pending or current.battle_playing:
		_done(id, false, "资源秘境未解锁或当前操作尚未完成")
		return
	var params: Dictionary = {}
	if action == "enter":
		if current.active or str(current.portal.id).is_empty() or str(current.portal.id) != str(p.get("portal_id", "")):
			_done(id, false, "资源秘境入口或运行状态已变化")
			return
		if policy.get("growth_linked", true):
			if not _budget().has_shortage(self, str(current.portal.type)):
				_done(id, false, "对应资源无可补给缺口，无需消耗入场机会")
				return
		if int(current.free_remaining) <= 0:
			var token_info: Dictionary = current.token
			if not policy.get("resource_realm_use_token", false) or not _requirements_available([{"kind": "material", "id": int(token_info.id), "count": int(token_info.cost)}], 1, int(policy.get("resource_realm_token_reserve", 1))):
				_done(id, false, "免费次数已用完，秘境令开关、来源保护或保留量不满足")
				return
		params = {"portal_id": current.portal.id, "request_id": id}
	elif action != "status":
		_done(id, false, "未知资源秘境操作")
		return
	api.resource_realm(func(response: Dictionary, ok: bool):
		var answer: Dictionary = response.get("resource_realm", {})
		var confirmed = ok and not answer.is_empty() and (answer.get("success") == true if action == "enter" else answer.get("success", true) == true)
		if confirmed and action == "enter":
			var mode = _main().get("_resource_realm_mode")
			if mode != null: mode._entered()
		_done(id, confirmed, "资源秘境入场已确认，原客户端继续探索与战斗" if confirmed and action == "enter" else "资源秘境进度已同步" if confirmed else str(answer.get("reason", "资源秘境操作未确认")))
	, action, params)

func _execute_refine(command: Dictionary, cb: Callable) -> void:
	var p: Dictionary = command.get("params", {})
	var mats: Dictionary = p.get("materials", {})
	var is_forge = str(command.kind) == "world_forge"
	if not gm.dungeon_idle.get("selected") is Dictionary:
		_done(str(command.id), false, "先选择已通关的挂机地点")
		return
	if is_forge:
		var point = _find_point(int(p.get("marker_id", 0)))
		if point.get("type") != "forge" or _point_is_current(point):
			_done(str(command.id), false, "世界熔炉已失效")
			return
	var refine = load("res://scripts/systems/refine_system.gd")
	var needs: Array = []
	var units = 0
	var future = _budget().future_context(self)
	var held = _budget().reserved(self)
	var excluded: Dictionary = refine.get_auto_fill_exclusions()
	var preferred = int(policy.get("refine_preferred_id", 0))
	var preference: Dictionary = p.get("preferred_reward", {}).duplicate(true)
	if preferred > 0:
		preference.clear()
		for candidate in refine.get_preference_candidates():
			if int(candidate.id) == preferred: preference = {"kind": candidate.kind, "id": preferred}
		if preference.is_empty():
			_done(str(command.id), false, "指定炼化偏好已失效")
			return
	elif not preference.is_empty():
		if not policy.get("growth_linked", true) or refine.get_valid_preference(preference).is_empty():
			_done(str(command.id), false, "自动炼化目标已变化")
			return
		var kind = "material" if preference.get("kind") == "equipment_upgrade" else str(preference.get("kind", ""))
		if _budget().shortage(self, kind, int(preference.get("id", 0)), held) <= 0:
			_done(str(command.id), false, "定向炼化目标已受保护或缺口已补齐")
			return
	elif not policy.get("refine_surplus_without_demand", false):
		_done(str(command.id), false, "没有有效缺料偏好，保留材料")
		return
	for mid in mats:
		var info = refine.get_refine_item_info(int(mid))
		var category = str(info.get("category", ""))
		var count = int(mats[mid])
		var kind = "herb" if category == "herb" else "material"
		var key = "%s:%d" % [kind, int(mid)]
		var keep = _budget().retention(self, {"kind": kind, "id": int(mid), "category": category}, future, int(held.get(key, 0)))
		if category in ["breakthrough_rare", "pill_material"] or excluded.has(str(int(mid))) or int(mid) == int(preference.get("id", 0)) or count < 1 or refine.get_progress_value(info) <= 0:
			_done(str(command.id), false, "炼化投入包含保留材料、排除项或目标本身")
			return
		if _budget().available(self, kind, int(mid)) - count < int(held.get(key, 0)) + keep:
			_done(str(command.id), false, "炼化会侵占最新成长需求或保留数量")
			return
		needs.append({"kind": kind, "id": int(mid), "count": count})
		units += count
	var display_mats = mats.duplicate()
	if is_forge:
		for mid in display_mats: display_mats[mid] = int(display_mats[mid]) * FORGE_PROGRESS_MULTIPLIER
	var calc = refine.calculate_level(display_mats)
	if mats.is_empty() or units > int(policy.get("refine_max_items", 50)) or int(calc.level) < int(policy.get("refine_target_level", 1)) or not _requirements_bound_safe(needs):
		_done(str(command.id), false, "炼化投入不足、超过预算或保护不允许消耗")
		return
	if is_forge:
		api.cave_world_forge(cb, int(p.marker_id), mats, int(calc.level), preference)
	else:
		api.refine(cb, mats, int(calc.level), preference)

func _on_game_request(_method: String, url: String, _body: Dictionary, response: Dictionary, ok: bool) -> void:
	# Read only our matching operation receipt; never retain request bodies or credentials.
	_observe_realm_command(url, _body, response, ok)
	if not ok or not challenge.get("seen", false): return
	if challenge.get("kind", "") == "challenge" and url == "/api/dungeon":
		var answer: Dictionary = response.get("dungeon", {})
		var expected_id = str(challenge.get("battle_id", ""))
		if not expected_id.is_empty() and str(answer.get("battle_id", expected_id)) != expected_id: return
		if answer.get("success", false) and answer.get("result", "") in ["win", "lose"]:
			challenge["confirmed"] = true
			challenge["won"] = answer.result == "win"
	elif challenge.get("kind", "") == "realm_challenge":
		var answer: Dictionary = response.get("cave_result", {})
		if answer.get("result", "") in ["win", "lose"]:
			challenge["confirmed"] = true
			challenge["won"] = answer.get("success", false) and answer.result == "win"


func _material_upgrade_deficit(mid: int) -> int:
	if not policy.get("tasks", {}).get("upgrade", true): return 0
	if _budget().source_blocked(self, "material", mid): return 0
	if policy.get("growth_linked", false):
		var key = "material:%d" % mid
		var upgrade = _budget().upgrade_claims(self)
		var prior = _budget().reserved(self, "material_synth")
		var conversions = _budget().conversion_claims(self, upgrade, prior)
		if not upgrade.has(key) and not conversions.has(key): return 0
		return maxi(0, int(_budget().reserved(self).get(key, 0)) - _budget().available(self, "material", mid))
	var required = 0
	var cap = mini(int(gm.character.level) - int(policy.get("upgrade_level_gap", 0)), int(cfg.get_value("equipment_upgrade", "max_level", 90)))
	var upgrade = load("res://scripts/systems/equipment_upgrade_system.gd")
	for eid in gm.character.equip_slots:
		var eq = gm.get_equipment(int(eid))
		if not _equipment_allowed(eq) or int(eq.level) >= cap: continue
		for req in upgrade.requirements(eq):
			if req.get("kind", "material") == "material" and int(req.get("id", 0)) == mid: required += int(req.count)
	if required > 0: required += int(policy.get("upgrade_reserve", 20))
	var have = _owned_count("material", mid) if _requirements_bound_safe([{"kind":"material", "id":mid, "count":1}]) else 0
	return maxi(0, required - have)

func _material_synthesis_snapshot() -> Array:
	var table: Dictionary = cfg.get_value("equipment_upgrade", "synthesis", {})
	var required = maxi(1, int(table.get("required_count", 5)))
	var recipes: Array = []
	for chain in table.get("chains", []):
		for index in range(chain.size() - 1):
			var mid = int(chain[index])
			var output = int(chain[index + 1])
			var info = cfg.get_material_info(output)
			recipes.append({"input_id": mid, "output_id": output, "required_count": required,
				"count": _owned_count("material", mid), "unlocked": gm.character.level >= int(info.get("min_level", 0)),
				"bound_only_safe": _requirements_bound_safe([{"kind": "material", "id": mid, "count": required}])})
	return recipes

func _point_is_current(point: Dictionary) -> bool:
	if point.get("is_current", false): return true
	return point.has("coord_x") and point.has("coord_y") and int(point.get("world_id", -1)) == int(gm.cave.get("world_id", 1)) and int(point.coord_x) == int(gm.cave.get("world_x", 0)) and int(point.coord_y) == int(gm.cave.get("world_y", 0))

func _home_safe(point: Dictionary) -> bool:
	if point.is_empty() or _point_is_current(point) or point.get("type", "") not in ["ordinary", "herb", "material", "spring", "relic", "stronghold", "forge", "empty"]: return false
	for feature in point.get("features", []):
		if not feature.get("revealed", true) or feature.get("is_negative", false): return false
	return true

func _occupy_home_safe(point: Dictionary) -> bool:
	# Occupation allows occupied homes, but keeps the same feature checks as relocation.
	if point.get("type", "") not in ["cultivator", "player", "robot"]: return false
	var home = point.duplicate(true)
	home["type"] = "ordinary"
	return _home_safe(home)

func _home_score(features: Array) -> float:
	var mode = str(policy.get("home_priority", "balanced"))
	var score = 0.0
	for feature in features:
		if not feature.get("revealed", true): continue
		var kind = str(feature.get("type", ""))
		var raw = feature.get("value", 0)
		var value = float(raw) if raw is float or raw is int else float(raw.get("chance", 0)) * float(raw.get("recovery_percent", 0)) / 100.0 if raw is Dictionary else 0.0
		var weight = 1.0
		if kind in ["idle_exp_bonus", "spring_exp_bonus"]: weight = 4.0 if mode == "growth" else 2.0
		elif kind in ["harvest_herb_bonus", "harvest_material_bonus", "extra_card"]: weight = 4.0 if mode == "loot" else 1.0
		elif kind in ["atk_bonus", "def_bonus", "hp_bonus", "crit_chance", "attack_speed", "crit_damage", "dodge_chance", "shield_break_bonus", "last_stand_hp", "last_stand_shield"]: weight = 3.0 if mode == "combat" else 1.0
		if feature.get("is_negative", false): value = -absf(value) * 2.0
		score += value * weight
	return score
