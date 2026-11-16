extends Node
# Read-only Steam Inventory SDK access on the already initialized game session.
# Never request tickets, login, consume, exchange, transfer or generate items.
var sdk
var bridge
var handle = -1
var request_started = 0
var next_refresh = 0
var updated_at = 0.0
var requested_generation = -1
var observed_generation = -1
var complete = false
var message = "等待Steam库存"
var counts: Dictionary = {}
var definitions: Dictionary = {}
var catalogue: Dictionary = {}
var catalogue_ready = false
var catalogue_complete = false
var configured_definitions: Array = []
var page_definitions: Dictionary = {}
var stack_count = 0
var item_count = 0
var catalogue_categories: Dictionary = {}
var next_definition_refresh = 0
const DEFINITION_CACHE = "fanxiu_assistant_definition_ids"

func configure(owner_bridge):
	bridge = owner_bridge
	for info in bridge.cfg.get_all_materials():
		if int(info.get("id",0)) > 0: configured_definitions.append(int(info.id))
		if info.get("category", "") == "gongfa_page":
			page_definitions["%d:%d" % [int(info.get("gongfa_id", -1)), int(info.get("gongfa_layer", -1))]] = int(info.get("id", 0))

func _ready():
	sdk = Engine.get_singleton("Steam") if Engine.has_singleton("Steam") else null
	if sdk == null or not sdk.has_method("getAllItems") or not sdk.has_method("getResultItems") or not sdk.has_method("getItemDefinitionProperty"):
		message = "Steam库存接口不可用，待识别物品保守保留"
		set_process(false)
		return
	_start_catalogue()

func _start_catalogue():
	if sdk.has_signal("inventory_definition_update") and not sdk.inventory_definition_update.is_connected(_definition_updated):
		sdk.inventory_definition_update.connect(_definition_updated)
	# SDK callbacks may have run before this bridge was attached. Keep only the
	# SDK's own current-session IDs, never a disk cache or guessed item range.
	if sdk.has_meta(DEFINITION_CACHE):
		var cached = sdk.get_meta(DEFINITION_CACHE)
		if cached is Array: _definition_updated(cached)
	_refresh_catalogue(Time.get_ticks_msec())

func _refresh_catalogue(now: int):
	if now < next_definition_refresh: return
	next_definition_refresh = now + (300000 if catalogue_ready else 30000)
	if sdk.has_method("loadItemDefinitions"): sdk.loadItemDefinitions()
	_recover_cached_catalogue()

func _definition_updated(ids: Array):
	var next: Dictionary = {}
	var categories: Dictionary = {}
	for definition in ids:
		if not (definition is int or definition is float) or int(definition) <= 0: return
		# Only Steam Community Market listing capability defines this protection.
		# A transferable definition with marketable=false is an ordinary usable item.
		next[int(definition)] = _property(int(definition), "marketable")
		var tags = sdk.getItemDefinitionProperty(int(definition), "tags")
		var category = "unclassified"
		if tags is Dictionary and tags.get("success",false):
			for tag in str(tags.get("property", "")).split(";"):
				if tag.begins_with("category:"): category=tag.trim_prefix("category:")
		categories[category]=int(categories.get(category,0))+1
	if next.is_empty(): return
	catalogue = next
	catalogue_categories = categories
	catalogue_ready = true
	catalogue_complete = true
	sdk.set_meta(DEFINITION_CACHE, ids.duplicate())
	bridge.snapshot_cache.clear()
	bridge.inventory_view.clear()

func _cached_id(definition: int):
	# The short, universal itemdefid property cannot exhaust the SDK buffer.
	# false means absent from the local definitions once that cache is confirmed.
	var result = sdk.getItemDefinitionProperty(definition, "itemdefid")
	if not result is Dictionary or not result.has("success") or not result.success is bool: return null
	if not result.success: return false
	return true if str(result.get("property", "")) == str(definition) else null

func _recover_cached_catalogue():
	if catalogue_ready or not complete: return
	var verified: Dictionary = {}
	# A successful inventory handle alone says nothing about definition readiness.
	# Require every definition in that SDK inventory to resolve to its exact ID.
	for definition in definitions:
		if _cached_id(int(definition)) != true: return
		verified[int(definition)] = _property(int(definition), "marketable")
	# Empty inventories may still have a warm SDK cache; probe actual game config
	# definitions, accepting only a positive exact SDK identity as evidence.
	if verified.is_empty():
		for definition in configured_definitions:
			if _cached_id(int(definition)) == true:
				verified[int(definition)] = _property(int(definition), "marketable")
				break
	if verified.is_empty(): return
	catalogue = verified
	catalogue_ready = true
	catalogue_complete = false
	bridge.snapshot_cache.clear()
	bridge.inventory_view.clear()

func _definition_info(definition: int) -> Dictionary:
	if not catalogue_ready or definition <= 0: return {"known":false,"tradable":true}
	if not catalogue.has(definition):
		if catalogue_complete:
			# A possession absent from a later callback is a metadata conflict.
			if definitions.has(definition): return {"known":false,"tradable":true}
			return {"known":true,"tradable":false}
		var exists = _cached_id(definition)
		if exists == null: return {"known":false,"tradable":true}
		if exists == false and definitions.has(definition): return {"known":false,"tradable":true}
		catalogue[definition] = _property(definition, "marketable") if exists == true else false
	# Missing/malformed flags remain unknown and are retried; they are never
	# silently converted into either a marketable or an ordinary definition.
	if catalogue[definition] == null: catalogue[definition] = _property(definition, "marketable")
	if catalogue[definition] == null: return {"known":false,"tradable":true}
	return {"known":true,"tradable":bool(catalogue[definition])}

func refresh(generation: int):
	requested_generation = generation

func _process(_delta):
	if sdk == null: return
	var now = Time.get_ticks_msec()
	_refresh_catalogue(now)
	if handle >= 0:
		var code = int(sdk.getResultStatus(handle))
		if code == 1:
			_apply_items(sdk.getResultItems(handle))
			sdk.destroyResult(handle)
			handle = -1
			next_refresh = now + maxi(30000, int(bridge.policy.get("inventory_refresh_seconds", 60)) * 1000)
		elif now - request_started > 20000 or code != 22:
			sdk.destroyResult(handle)
			handle = -1
			message = "Steam库存读取未确认，稍后重试；保留上次保护"
			next_refresh = now + 60000
		return
	if now < next_refresh and requested_generation == observed_generation: return
	# A manual refresh never creates concurrent SDK handles.
	observed_generation = requested_generation
	handle = int(sdk.getAllItems())
	request_started = now
	if handle < 0:
		message = "Steam库存请求未接受，稍后重试"
		next_refresh = now + 60000

func _property(definition: int, name: String):
	var result = sdk.getItemDefinitionProperty(definition, name)
	if not result is Dictionary or not result.get("success") is bool or result.success != true: return null
	var value = str(result.get("property", "")).strip_edges().to_lower()
	if value in ["1", "true"]: return true
	if value in ["0", "false"]: return false
	return null

func _apply_items(items: Array):
	var next: Dictionary = {}
	var next_definitions: Dictionary = {}
	var stacks = 0
	var quantity = 0
	for item in items:
		if not item is Dictionary or not item.has("item_definition") or not item.has("quantity") or not item.has("flags"):
			message = "Steam库存结构变化，保留上次保护并等待适配"
			return
		var definition = int(item.item_definition)
		var flags = int(item.flags)
		var amount = maxi(0, int(item.quantity))
		if definition <= 0: return
		# Removed/consumed entries do not represent current possessions.
		if flags & 768 or amount == 0: continue
		var marketable = _property(definition, "marketable")
		next_definitions[definition] = {"marketable":marketable}
		# Temporary instance restrictions do not erase listing capability.
		# Unknown definitions stay protected via describe(), outside confirmed counts.
		if marketable == true:
			next[definition] = int(next.get(definition, 0)) + amount
			stacks += 1
			quantity += amount
	counts = next
	definitions = next_definitions
	complete = true
	if not catalogue_complete:
		catalogue_ready = false
		catalogue.clear()
		_recover_cached_catalogue()
	updated_at = Time.get_unix_time_from_system()
	stack_count = stacks
	item_count = quantity
	message = "已读取当前Steam库存"
	bridge.snapshot_cache.clear()
	bridge.inventory_view.clear()

func describe(kind: String, item_id: int, layer: int = -1) -> Dictionary:
	# Equipment IDs are server-side instances, never Steam item definition IDs.
	if kind == "equipment": return {"steam_trade_known":true, "steam_tradable":false, "steam_tradable_count":0}
	var definition = item_id
	if kind == "gongfa": definition = int(page_definitions.get("%d:%d" % [item_id, layer], 0))
	elif kind == "fashion":
		# Server instance IDs differ from the Steam definition/config ID.
		var fashion = bridge.gm.inventory.get("fashions", {}).get(item_id)
		definition = int(fashion.fashion_id) if fashion != null else 0
	# Catalogue capability also protects newly obtained items before the next SDK snapshot.
	var info = _definition_info(definition)
	return {"steam_trade_known":info.known, "steam_tradable":info.tradable,
		"steam_tradable_count":int(counts.get(definition, 0)), "steam_definition":definition}

func public_status() -> Dictionary:
	var items: Array = []
	for definition in counts:
		items.append({"definition":int(definition),"quantity":int(counts[definition])})
	return {"protection_standard":"steam_marketable","available":sdk!=null,"complete":complete,"catalogue_ready":catalogue_ready,"catalogue_complete":catalogue_complete,"catalogue_source":"sdk_callback" if catalogue_complete else "sdk_cached_properties" if catalogue_ready else "pending","definitions":catalogue.size(),"updated_at":updated_at,"refreshing":handle>=0,
		"categories":catalogue_categories,"items":items,"stacks":stack_count,"quantity":item_count,"message":"已读取库存，等待Steam定义识别（自动重试）" if complete and not catalogue_ready else message}

func _exit_tree():
	if sdk != null and handle >= 0: sdk.destroyResult(handle)
