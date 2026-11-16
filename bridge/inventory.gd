extends RefCounted
# Read only the current player's possessions. Icons are cached locally, never distributed.

static func _icon(path: String, directory: String) -> String:
	if directory.is_empty() or not path.begins_with("res://assets/") or not ResourceLoader.exists(path): return ""
	var filename = path.sha256_text() + ".png"
	var target = directory.path_join(filename)
	if not FileAccess.file_exists(target):
		var texture = load(path)
		if not texture is Texture2D: return ""
		var picture: Image = texture.get_image()
		if picture == null or picture.is_empty(): return ""
		if picture.is_compressed() and picture.decompress() != OK: return ""
		if picture.get_width() > 128 or picture.get_height() > 128:
			var ratio = 128.0 / maxf(picture.get_width(), picture.get_height())
			picture.resize(maxi(1,int(picture.get_width()*ratio)),maxi(1,int(picture.get_height()*ratio)),Image.INTERPOLATE_LANCZOS)
		DirAccess.make_dir_recursive_absolute(directory)
		var temporary = target + ".tmp.png"
		if picture.save_png(temporary) != OK: return ""
		if DirAccess.rename_absolute(temporary,target) != OK: return ""
	return filename

static func capture(bridge, directory: String, generation: int) -> Dictionary:
	var gm = bridge.gm
	var cfg = bridge.cfg
	var items: Array = []
	for key in gm.inventory.equipments:
		var eq = gm.inventory.equipments[key]
		items.append({"key":"equipment:%d" % int(eq.id),"kind":"equipment","id":int(eq.id),"trade_category":"equipment",
			"name":eq.get_display_name(),"quality":eq.quality,"level":eq.level,"count":1,"bound_count":1 if eq.bound else 0,
			"game_locked":bool(eq.locked),"equipped":int(eq.id) in gm.character.equip_slots,"icon":_icon(eq.get_icon_path(),directory)})
	var seen: Dictionary = {}
	for kind in ["material","herb","pill"]:
		for page in gm.get_storage_type_pages(kind):
			for cell in page.get("items",[]):
				var parts = str(cell.get("key", "")).split(":")
				if parts.size() == 2 and parts[0] == kind and parts[1].is_valid_int(): seen[str(cell.key)] = [kind,int(parts[1])]
	for info in cfg.get_all_materials():
		var mid = int(info.get("id",0))
		if gm.get_material_count(mid) + gm.get_consumable_count(mid) > 0: seen["material:%d" % mid] = ["material",mid]
	for key in seen:
		var kind: String = seen[key][0]
		var mid: int = seen[key][1]
		var count = bridge._owned_count(kind,mid)
		if count <= 0: continue
		var info: Dictionary = bridge._item_info(kind,mid)
		var category = "material"
		var name = cfg.get_localized_material_name(mid)
		var icon = cfg.get_material_icon_path(mid)
		if kind == "herb":
			name = cfg.get_localized_herb_name(mid)
			icon = load("res://scripts/systems/cave_system.gd").get_herb_icon_path(mid)
		elif kind == "pill":
			category = "consumable"
			name = cfg.get_localized_pill_name(mid)
			icon = load("res://scripts/data/pill_data.gd").get_pill_icon_path(mid)
		elif info.get("use_type", "") == "gongfa_page": category = "gongfa"
		elif info.get("category", "") in ["consumable","prop"] or not str(info.get("use_type", "")).is_empty(): category = "consumable"
		items.append({"key":key,"kind":kind,"id":mid,"trade_category":category,"name":name,
			"quality":str(info.get("rarity","")),"count":count,"bound_count":bridge._bound_count(kind,mid),"icon":_icon(icon,directory)})
	var pages: Dictionary = gm.inventory.get("gongfa_pages",{})
	var gd = load("res://scripts/data/gongfa_data.gd")
	for gid_text in pages:
		var gid = int(gid_text)
		var info: Dictionary = gd.get_gongfa_by_id(gid)
		for layer_text in pages[gid_text]:
			var layer = int(layer_text)
			var count = int(pages[gid_text][layer_text])
			if count <= 0: continue
			items.append({"key":"gongfa:%d:%d" % [gid,layer],"kind":"gongfa","id":gid,"layer":layer,"trade_category":"gongfa",
				"name":cfg.get_localized_gongfa_name(gid)+(" · 入门页" if layer==0 else " · 第%d层" % layer),"quality":str(info.get("rarity",info.get("quality",""))),
				"count":count,"bound_count":int(gm.inventory.get("bound_gongfa_pages",{}).get(str(gid),{}).get(str(layer),0)),"icon":_icon(gd.get_icon_path(gid),directory)})
	for key in gm.inventory.get("fashions",{}):
		var fashion = gm.inventory.fashions[key]
		items.append({"key":"fashion:%d" % int(fashion.id),"kind":"fashion","id":int(fashion.id),"trade_category":"fashion",
			"name":fashion.get_display_name(),"quality":cfg.get_fashion_quality(fashion.fashion_id),"count":1,"bound_count":1 if fashion.bound else 0,
			"icon":_icon(fashion.get_icon_path(),directory)})
	for item in items: item.merge(bridge._steam_info(str(item.kind), int(item.id), int(item.get("layer", -1))))
	return {"items":items,"generation":generation,"updated_at":Time.get_unix_time_from_system(),"complete":true}
