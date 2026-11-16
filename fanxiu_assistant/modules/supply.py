"""SupplyPlans: single-step intentions, confirmed by the game bridge."""
import math
import time
from ..settings import QUALITIES
from ..protection import available, locked, trade_preserved, equipment_allowed, metadata, valid_lock, command_keys, keys_overlap
from ..breakthrough import preparation, current_stage

class SupplyPlans:
    def plan_collect(self, s):
        if not s.get("idle_collecting"):
            return {}, "", 75

    def plan_harvest(self, s):
        idle = s.get("idle", {})
        server_ms = time.time() * 1000 + idle.get("_server_clock_offset_ms", 0)
        if any(d.get("available_at", 0) <= server_ms for d in idle.get("drops", [])):
            return {}, "dungeon_idle", 12

    def plan_open_pack(self, s):
        for item in s.get("materials", []):
            if item.get('use_type') == 'resource_pack' and self.config['tasks'].get('resource_pack'): continue
            if available(self.config,s,'material',item['id'],selector=True,info=item,total=item.get('count',0),bound=item.get('bound_count',0)) > 0 and item.get("use_type") in ("equipment_box", "resource_pack"):
                return {"material_id": item["id"]}, "", 5

    def plan_mail(self, s):
        for mail in s.get('mails', []):
            if not mail.get('claimed') and mail.get('rewards'):
                return {'mail_id': int(mail['id'])}, 'mail', 10
        return {}, "", 300

    def plan_resource_pack(self, s):
        if s.get('bridge_revision', 0) < 12: return
        quota = s.get('resource_pack_remaining', 0)
        if quota <= 0: return
        for recipe in s.get('resource_pack_recipes', []):
            if locked(self.config,recipe['input_kind'],recipe['input_id']) or trade_preserved(self.config,recipe['input_kind'],metadata(s,recipe['input_kind'],recipe['input_id'])): continue
            if recipe.get('size') != int(self.config['resource_pack_size']) or recipe.get('cost', 0) <= 0: continue
            if self.config['resource_pack_materials'] and recipe['input_id'] not in self.config['resource_pack_materials']: continue
            held = (self.ledger(s).held(f"{recipe['input_kind']}:{recipe['input_id']}") if self.config['growth_linked']
                    else preparation(self.config, s)['reserved'].get(f"{recipe['input_kind']}:{recipe['input_id']}", 0))
            count = min(int((recipe.get('unbound_count', 0) - held - self.config['resource_pack_reserve']) // recipe['cost']),
                        int(quota), int(self.config['resource_pack_batch']))
            if count > 0:
                return {'kind':recipe['input_kind'], 'material_id':recipe['input_id'], 'size':recipe['size'], 'count':count}, 'storage', 60

    def plan_furnace_absorb(self, s):
        c = s.get('character', {})
        if s.get('features', {}).get('furnace') and s.get('furnace', {}).get('exp_pool', 0) >= self.config['furnace_min_exp'] and c.get('exp', 0) < c.get('exp_needed', 0):
            return {}, 'cave_result', 60
