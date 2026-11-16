extends Node
# Updates only our bridge at a settled boundary. Never touches native sessions.
var base_dir = ""
var next_check = 0
var verified_target = ""

static func request(script) -> void:
	var tree = Engine.get_main_loop()
	if not tree is SceneTree or tree.root.has_meta("fanxiu_session_upgrader"): return
	tree.root.set_meta("fanxiu_session_upgrader", true)
	var watcher = script.new()
	watcher.name = "FanxiuSessionUpgrade"
	watcher.base_dir = script.resource_path.get_base_dir()
	tree.root.add_child.call_deferred(watcher)

func _process(_delta) -> void:
	if Time.get_ticks_msec() < next_check: return
	next_check = Time.get_ticks_msec() + 1500
	check_update()

func target_from_manifest(manifest) -> String:
	if not manifest is Dictionary or manifest.get("schema") != 1: return ""
	var relative = str(manifest.get("target", ""))
	var pieces = relative.split("/")
	if pieces.size() != 3 or pieces[0] != "_revisions" or pieces[1].is_empty() or pieces[1].contains(".") or pieces[1].contains("\\") or pieces[2] != "assistant.gd": return ""
	var target = base_dir.path_join(relative)
	var files = manifest.get("files", {})
	if not files is Dictionary or not files.has("assistant.gd") or not files.has("resource_budget.gd") or not files.has("session_upgrade.gd"): return ""
	for file in files:
		if not file is String or file.get_file() != file or not file.ends_with(".gd"): return ""
		if not files[file] is String or files[file].length() != 64: return ""
		if FileAccess.get_sha256(target.get_base_dir().path_join(file)) != files[file]: return ""
	return target

func settled(bridge) -> bool:
	if bridge.busy or not bridge.results.is_empty(): return false
	if bridge.http == null or bridge.http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED: return false
	if bridge.api == null or int(bridge.api.pending_count) != 0 or bool(bridge.api.dungeon_start_pending): return false
	var main = bridge._main()
	if main != null and main.battle_flow != null and bool(main.battle_flow.in_combat): return false
	return true

func check_update() -> bool:
	var manifest_path = base_dir.path_join("session-upgrade.json")
	if not FileAccess.file_exists(manifest_path): return false
	var manifest = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	var target = target_from_manifest(manifest)
	if target.is_empty(): return false
	var matches: Array = []
	for node in get_tree().root.find_children("LocalBridge", "", true, false):
		var script = node.get_script()
		if script != null and script.resource_path.begins_with(base_dir + "/") and script.resource_path.get_file() == "assistant.gd": matches.append(node)
	if matches.size() != 1: return false
	var old = matches[0]
	if old.get_script().resource_path == target or not settled(old): return false
	# Immutable per-revision directories avoid reusing cached scripts from old code.
	var script = ResourceLoader.load(target, "GDScript", ResourceLoader.CACHE_MODE_IGNORE)
	if script == null or not script.can_instantiate(): return false
	var replacement = script.new()
	if not replacement is Node: return false
	for property in ["policy", "daily_guard", "inventory_options", "social_attempts", "capture_attempts"]:
		replacement.set(property, old.get(property).duplicate(true))
	replacement.last_id = old.last_id
	replacement.name = "LocalBridge"
	var parent = old.get_parent()
	old.timer.stop()
	parent.remove_child(old)
	old.queue_free()
	parent.add_child(replacement)
	print("[FanxiuAssistant] Own bridge updated without restarting game; PID=", OS.get_process_id())
	return true
