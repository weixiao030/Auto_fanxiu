extends RefCounted
const SESSION_UPGRADE = preload("session_upgrade.gd")

static func _static_init() -> void:
	SESSION_UPGRADE.request(SESSION_UPGRADE)
# Recompute from native state at execution time; never accept a planner-supplied reserve.

static func future_context(b) -> Dictionary:
	var entries: Array = b.cfg.get_value("realm", "breakthroughs", [])
	var required: Dictionary = {}
	var upcoming: Dictionary = {}
	for entry in entries:
		if int(entry.get("level", 0)) < int(b.gm.character.level): continue
		for row in entry.get("materials", []):
			var key = "%s:%d" % [row.get("kind", "material"), int(row.id)]
			required[key] = maxi(int(required.get(key, 0)), int(row.count))
		if upcoming.is_empty() or int(entry.level) < int(upcoming.level):
			upcoming = {"level": int(entry.level), "materials": entry.get("materials", []).duplicate(true)}
	return {"known": not entries.is_empty(), "required": required, "upcoming": upcoming}

static func available(b, kind: String, item_id: int) -> int:
	if b._locked(kind, item_id): return 0
	var total = b._owned_count(kind, item_id)
	return clampi(b._bound_count(kind, item_id), 0, total) if b._trade_protected(kind, item_id) else total

static func source_blocked(b, kind: String, item_id: int) -> bool:
	return b._locked(kind, item_id)

static func shortage(b, kind: String, item_id: int, claims: Dictionary) -> int:
	# Only fixed locks prevent replenishing a bound-first stock.
	if b._locked(kind, item_id): return 0
	return maxi(0, int(claims.get("%s:%d" % [kind, item_id], 0)) - available(b, kind, item_id))

static func has_shortage(b, kind: String) -> bool:
	var claims = reserved(b)
	for key in claims:
		var parts = str(key).split(":")
		if parts[0] == kind and shortage(b, kind, int(parts[1]), claims) > 0: return true
	return false

static func _add(target: Dictionary, key: String, amount: int) -> void:
	target[key] = int(target.get(key, 0)) + amount

static func upgrade_claims(b) -> Dictionary:
	var tasks: Dictionary = b.policy.get("tasks", {})
	var upgrade: Dictionary = {}
	if tasks.get("upgrade", true):
		var cap = mini(int(b.gm.character.level) - int(b.policy.get("upgrade_level_gap", 0)), int(b.cfg.get_value("equipment_upgrade", "max_level", 90)))
		var system = load("res://scripts/systems/equipment_upgrade_system.gd")
		for eid in b.gm.character.equip_slots:
			var eq = b.gm.get_equipment(int(eid))
			if eq == null or not b._equipment_allowed(eq) or int(eq.level) >= cap: continue
			for row in system.requirements(eq):
				_add(upgrade, "%s:%d" % [row.get("kind", "material"), int(row.id)], int(row.count))
		for key in upgrade: upgrade[key] += int(b.policy.get("upgrade_reserve", 20))
	return upgrade

static func _conversion_visit(b, mid: int, recipes: Dictionary, visited: Dictionary, order: Array, depth: int = 0) -> bool:
	var status = int(visited.get(mid, 0))
	if status in [1, 3]: return false
	if status == 2 or not recipes.has(mid) or depth >= 8 or source_blocked(b, "material", mid): return true
	visited[mid] = 1
	if not _conversion_visit(b, int(recipes[mid].input_id), recipes, visited, order, depth + 1):
		visited[mid] = 3
		return false
	visited[mid] = 2
	order.append(mid)
	return true

static func conversion_claims(b, upgrade: Dictionary, prior: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	if not b.policy.get("tasks", {}).get("material_synth", true): return result
	var recipes: Dictionary = {}
	for row in b._material_synthesis_snapshot():
		if row.unlocked: recipes[int(row.output_id)] = row
	var visited: Dictionary = {}
	var order: Array = []
	for key in upgrade:
		if str(key).begins_with("material:"):
			_conversion_visit(b, int(str(key).split(":")[1]), recipes, visited, order)
	order.reverse()
	for mid in order:
		var key = "material:%d" % mid
		var deficit = maxi(0, int(prior.get(key, 0)) + int(result.get(key, 0)) - available(b, "material", mid))
		if deficit == 0: continue
		var recipe: Dictionary = recipes[mid]
		var source_key = "material:%d" % int(recipe.input_id)
		if not result.has(source_key): result[source_key] = int(b.policy.get("material_synth_reserve", 20))
		_add(result, source_key, deficit * maxi(1, int(recipe.required_count)))
	return result

static func reserved(b, consumer: String = "background") -> Dictionary:
	var result: Dictionary = b._preparation_reserved()
	if not b.policy.get("growth_linked", false): return result
	var tasks: Dictionary = b.policy.get("tasks", {})
	var future = future_context(b)
	if b._breakthrough_enabled() and b._breakthrough_context().info.is_empty():
		for row in future.upcoming.get("materials", []):
			_add(result, "%s:%d" % [row.get("kind", "material"), int(row.id)], int(row.count))
	if consumer == "breakthrough": return result
	var upgrade = upgrade_claims(b)
	if consumer != "upgrade":
		for key in upgrade: _add(result, key, int(upgrade[key]))
	if consumer in ["upgrade", "alchemy"]: return result
	if tasks.get("alchemy", true):
		var chosen = normal_recipe(b)
		for row in chosen.get("materials", []):
			_add(result, "%s:%d" % [row.kind, int(row.id)], int(row.count) + int(b.policy.get("alchemy_reserve", 5)))
	if consumer == "material_synth": return result
	var conversions = conversion_claims(b, upgrade, result)
	for key in conversions: _add(result, key, int(conversions[key]))
	return result

static func mirror_target(b) -> String:
	# Compare cumulative demand tiers, allocating inventory to higher priorities first.
	var tiers = [reserved(b, "breakthrough"), reserved(b, "alchemy"), reserved(b, "material_synth"), reserved(b)]
	var total: Dictionary = tiers[-1]
	var best: Array = []
	var target = "material"
	for key in total:
		var parts = str(key).split(":")
		if parts[0] not in ["herb", "material"]: continue
		var mid = int(parts[1])
		if b._locked(parts[0], mid): continue
		var have = available(b, parts[0], mid)
		var missing = int(total[key]) - have
		if missing <= 0: continue
		var priority = tiers.size()
		for index in tiers.size():
			if int(tiers[index].get(key, 0)) > have:
				priority = index
				break
		var score = [priority, -missing, str(key)]
		if best.is_empty() or score_before(score, best):
			best = score
			target = parts[0]
	return target

static func retention(b, row: Dictionary, future: Dictionary, held: int = 0) -> int:
	var key = "%s:%d" % [row.get("kind", "material"), int(row.id)]
	var category = str(row.get("category", ""))
	if future.known and category in ["breakthrough_main", "breakthrough_aux", "breakthrough_special"] and not future.required.has(key) and b.policy.get("refine_recycle_obsolete", true):
		return int(b.policy.get("refine_obsolete_reserve", 2))
	# Current claims and the future absolute floor overlap; own extra reserve remains additive.
	return maxi(int(b.policy.get("refine_reserve", 20)), int(future.required.get(key, 0)) - held)

static func normal_recipe(b) -> Dictionary:
	var pd = load("res://scripts/data/pill_data.gd")
	var realm = b.cfg.get_realm_id_by_level(b.gm.character.level)
	var higher = reserved(b, "alchemy")
	var best: Dictionary = {}
	var best_score: Array = []
	for pill in b.cfg.get_pill_list():
		if not b._breakthrough_effect(pill).is_empty() or not b._pill_useful(pill): continue
		if b._owned_count("pill", int(pill.id)) > int(b.policy.get("pill_reserve", 0)): continue
		for index in pill.get("recipes", []).size():
			if int(pill.recipes[index].get("realm", 0)) > realm: continue
			var needs: Array = pd.get_recipe_materials(pill, index)
			if needs.is_empty(): continue
			var blocked = false
			for row in needs:
				if source_blocked(b, str(row.kind), int(row.id)): blocked = true
			if blocked: continue
			var gap = 0
			for row in needs:
				var key = "%s:%d" % [row.kind, int(row.id)]
				gap += maxi(0, int(row.count) + int(b.policy.get("alchemy_reserve", 5)) - maxi(0, available(b, str(row.kind), int(row.id)) - int(higher.get(key, 0))))
			var score = [gap, int(pill.id), index]
			if best.is_empty() or score_before(score, best_score):
				best = {"pill_id": int(pill.id), "recipe_index": index, "materials": needs}
				best_score = score
	return best

static func score_before(left: Array, right: Array) -> bool:
	for i in mini(left.size(), right.size()):
		if left[i] != right[i]: return left[i] < right[i]
	return left.size() < right.size()
