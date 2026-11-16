extends Node
# Load across game versions; runtime operations still require valid game responses.
func _ready() -> void:
	var bridge_script = load(get_script().resource_path.get_base_dir().path_join("assistant.gd"))
	if bridge_script != null:
		var bridge = bridge_script.new()
		bridge.name = "LocalBridge"
		add_child(bridge)
