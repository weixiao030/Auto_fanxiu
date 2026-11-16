extends Node
var checks = 0
var failures: Array = []

class FakeApi extends RefCounted:
	var pending_count = 0
	var dungeon_start_pending = false

func check(condition, message):
	checks += 1
	if not condition: failures.append(message)

func write(path, text):
	var file = FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()

func _ready():
	var base = "user://fanxiu-upgrade-test"
	DirAccess.make_dir_recursive_absolute(base)
	var old_source = "extends Node\nvar busy=false\nvar results=[]\nvar http\nvar timer\nvar api\nvar main={\"battle_flow\":{\"in_combat\":false}}\nvar policy={}\nvar daily_guard={}\nvar inventory_options={}\nvar social_attempts={}\nvar capture_attempts={}\nvar last_id=\"\"\nfunc _main(): return main\n"
	write(base.path_join("assistant.gd"), old_source)
	for name in ["session_upgrade.gd", "resource_budget.gd"]:
		write(base.path_join(name), FileAccess.get_file_as_string("res://" + name))
	var old = load(base.path_join("assistant.gd")).new()
	old.name = "LocalBridge"; old.api = FakeApi.new()
	old.http = HTTPRequest.new(); old.add_child(old.http)
	old.timer = Timer.new(); old.add_child(old.timer)
	old.policy = {"manual_locks":["material:1"],"preserve_steam_tradable":true}
	old.last_id = "already-acknowledged"
	add_child(old)
	var native = Node.new(); native.name = "NativeSessionFixture"; add_child(native)
	var native_id = native.get_instance_id()
	check(not get_tree().root.has_node("FanxiuSessionUpgrade"), "watcher existed before late load")
	load(base.path_join("resource_budget.gd"))
	await get_tree().process_frame
	var watcher = get_tree().root.get_node_or_null("FanxiuSessionUpgrade")
	check(watcher != null, "late budget load failed to install watcher")
	watcher.set_process(false)
	var relative = "_revisions/fixturehash/assistant.gd"
	var target_dir = base.path_join(relative).get_base_dir()
	DirAccess.make_dir_recursive_absolute(target_dir)
	write(target_dir.path_join("assistant.gd"), old_source + "var upgraded=true\n")
	for name in ["session_upgrade.gd", "resource_budget.gd"]:
		write(target_dir.path_join(name), FileAccess.get_file_as_string(base.path_join(name)))
	var hashes: Dictionary = {}
	for name in ["assistant.gd", "session_upgrade.gd", "resource_budget.gd"]: hashes[name] = FileAccess.get_sha256(target_dir.path_join(name))
	var manifest = {"schema":1,"target":relative,"files":hashes}
	write(base.path_join("session-upgrade.json"), JSON.stringify(manifest))
	check(watcher.target_from_manifest(manifest) == base.path_join(relative), "valid staged scripts rejected")
	for path in ["../assistant.gd", "_revisions/../assistant.gd", "C:/assistant.gd", "_revisions/a/other.gd", "_revisions/a\\b/assistant.gd"]:
		var invalid = manifest.duplicate(true); invalid.target = path
		check(watcher.target_from_manifest(invalid).is_empty(), "unsafe target accepted")
	var invalid = manifest.duplicate(true); invalid.files["assistant.gd"] = "0".repeat(64)
	check(watcher.target_from_manifest(invalid).is_empty(), "corrupt script accepted")
	old.busy = true; check(not watcher.check_update(), "busy action interrupted"); old.busy = false
	old.results = [{"id":"unacknowledged"}]; check(not watcher.check_update(), "unacknowledged result lost"); old.results = []
	old.api.pending_count = 1; check(not watcher.check_update(), "native request interrupted"); old.api.pending_count = 0
	old.api.dungeon_start_pending = true; check(not watcher.check_update(), "native start interrupted"); old.api.dungeon_start_pending = false
	old.main.battle_flow.in_combat = true; check(not watcher.check_update(), "native battle interrupted"); old.main.battle_flow.in_combat = false
	check(watcher.check_update(), "idle own bridge failed to update")
	var replacement = get_node("LocalBridge")
	check(replacement.upgraded, "replacement was not loaded from immutable directory")
	check(replacement.policy.manual_locks == ["material:1"], "fixed locks lost across update")
	check(replacement.policy.preserve_steam_tradable, "Steam protection lost across update")
	check(replacement.last_id == "already-acknowledged", "deduplication cursor lost")
	check(native.get_instance_id() == native_id and is_instance_valid(native), "native session replaced")
	check(not watcher.check_update(), "same revision repeatedly replaced")
	print("SESSION_UPGRADE_CHECKS=", checks, " FAILURES=", JSON.stringify(failures))
	get_tree().quit(0 if failures.is_empty() else 1)
