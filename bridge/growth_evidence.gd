extends RefCounted
# Only numeric gameplay facts cross this boundary; never serialize native replies.

static func _add(target: Dictionary, kind: String, item_id: int, count: int = 0) -> void:
	if kind == "equipment_upgrade": kind = "material"
	if kind not in ["material", "herb", "pill"] or item_id <= 0: return
	var key = "%s:%d" % [kind, item_id]
	target[key] = int(target.get(key, 0)) + count

static func _snapshot(b, keys: Dictionary, equipment_id: int) -> Dictionary:
	var items: Dictionary = {}
	for key in keys:
		var parts = str(key).split(":")
		items[key] = b._owned_count(parts[0], int(parts[1]))
	var equipment = b.gm.get_equipment(equipment_id) if equipment_id > 0 else null
	return {"items":items, "level":int(b.gm.character.level), "equipment_id":equipment_id,
		"equipment_level":int(equipment.level) if equipment != null else 0}

static func begin(b, command: Dictionary) -> Dictionary:
	var kind = str(command.get("kind", ""))
	if kind not in ["refine", "world_forge", "alchemy", "material_synth", "upgrade", "breakthrough"]: return {}
	var p: Dictionary = command.get("params", {})
	var needs: Dictionary = {}
	var keys: Dictionary = {}
	var outputs: Dictionary = {}
	var equipment_id = 0
	match kind:
		"refine", "world_forge":
			var system = load("res://scripts/systems/refine_system.gd")
			for mid in p.get("materials", {}):
				var info = system.get_refine_item_info(int(mid))
				_add(needs, "herb" if info.get("category") == "herb" else "material", int(mid), int(p.materials[mid]))
			for candidate in system.get_preference_candidates(): _add(keys, str(candidate.kind), int(candidate.id))
		"alchemy":
			var pd = load("res://scripts/data/pill_data.gd")
			var pill = pd.get_pill_info(int(p.get("pill_id", 0)))
			var count = 1 if p.get("breakthrough_prepare", false) else clampi(int(p.get("count", 1)), 1, int(b.policy.get("alchemy_batch", 1)))
			for row in pd.get_recipe_materials(pill, int(p.get("recipe_index", -1))):
				_add(needs, str(row.get("kind", "material")), int(row.get("id", 0)), int(row.get("count", 0)) * count)
			_add(outputs, "pill", int(p.get("pill_id", 0)))
		"material_synth":
			for recipe in b._material_synthesis_snapshot():
				if int(recipe.input_id) == int(p.get("material_id", 0)):
					_add(needs, "material", int(recipe.input_id), int(recipe.required_count) * int(p.get("count", 0)))
					_add(outputs, "material", int(recipe.output_id))
					break
		"upgrade":
			equipment_id = int(p.get("item_id", 0))
			var equipment = b.gm.get_equipment(equipment_id)
			if equipment != null:
				for row in load("res://scripts/systems/equipment_upgrade_system.gd").requirements(equipment):
					_add(needs, "material", int(row.get("id", 0)), int(row.get("count", 0)))
		"breakthrough":
			for row in b._breakthrough_context().get("info", {}).get("materials", []):
				_add(needs, str(row.get("kind", "material")), int(row.get("id", 0)), int(row.get("count", 0)))
	for key in needs: keys[key] = 0
	for key in outputs: keys[key] = 0
	return {"kind":kind, "requirements":needs, "output_keys":outputs, "before":_snapshot(b, keys, equipment_id)}

static func finish(b, context: Dictionary, answer: Dictionary) -> Dictionary:
	if context.is_empty(): return {}
	var rewards: Dictionary = {}
	for reward in answer.get("rewards", []) if answer.get("rewards") is Array else []:
		if not reward is Dictionary: continue
		var kind = str(reward.get("type", reward.get("kind", "")))
		if kind in ["item", "prop", "consumable"]: kind = "material"
		var item_id = int(reward.get("herb_id", reward.get("pill_id", reward.get("material_id", reward.get("item_id", reward.get("id", 0))))))
		var count = int(reward.get("count", 1))
		if count > 0: _add(rewards, kind, item_id, count)
	var after = _snapshot(b, context.before.items, int(context.before.equipment_id))
	var outputs: Dictionary = {}
	if context.kind in ["refine", "world_forge"]:
		outputs = rewards.duplicate()
	else:
		for key in context.output_keys:
			var delta = int(after.items.get(key, 0)) - int(context.before.items.get(key, 0))
			if delta > 0: outputs[key] = delta
	return {"schema":1, "kind":context.kind, "native_success":answer.get("success") == true,
		"requirements":context.requirements, "outputs":outputs, "native_rewards":rewards,
		"before":context.before, "after":after}
