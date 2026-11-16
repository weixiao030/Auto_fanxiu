"""EquipmentPlans: single-step intentions, confirmed by the game bridge."""
import math
import time
from ..settings import QUALITIES
from ..protection import available, locked, trade_preserved, equipment_allowed, source_blocked, metadata, valid_lock, command_keys, keys_overlap
from ..breakthrough import preparation, current_stage

class EquipmentPlans:
    def score(self, item):
        return sum(float(item.get("stats", {}).get(k, 0)) * w for k, w in self.config["weights"].items())

    @staticmethod
    def fixed_upgrade(candidate,current):
        if current is None:return True
        new,old=candidate.get('fixed_stats'),current.get('fixed_stats')
        if not isinstance(new,dict) or not isinstance(old,dict):return False
        keys=set(new)|set(old)
        return bool(keys) and all(new.get(k,0)>=old.get(k,0) for k in keys) and any(new.get(k,0)>old.get(k,0) for k in keys)

    def plan_equip(self, s):
        c = s.get("character", {})
        items = {int(e["id"]): e for e in s.get("equipment", [])}
        slots = s.get("slots", [])
        equipped = c.get("equip_slots", [])
        options = []
        for idx, slot in enumerate(slots):
            old_id = int(equipped[idx]) if idx < len(equipped) else -1
            old=items.get(old_id)
            if locked(self.config,'equipment',old_id) or old and old.get('locked'):
                continue
            old_score = self.score(items.get(old_id, {}))
            matching = [e for e in items.values() if equipment_allowed(self.config,e) and e.get("level", 999) <= c.get("level", 0)
                        and (e['id'] not in equipped or e['id']==old_id)
                        and (not self.config['equip_keep_weapon_type'] or slot!='weapon' or old is None or e.get('slot')==old.get('slot'))
                        and ("weapon" if e.get("slot", "").startswith("weapon_") else e.get("slot")) == slot]
            if not matching:
                continue
            if not self.config['equip_use_weights']:
                best=old
                for item in sorted(matching,key=lambda e:e['id']):
                    if self.fixed_upgrade(item,best):best=item
                if best is not None and best['id']!=old_id:
                    return {'item_id':best['id'],'slot_idx':idx},'equip',5
                continue
            best = max(matching, key=lambda e: (self.score(e), e.get("level", 0), -e["id"]))
            gain = self.score(best) - old_score
            if best["id"] != old_id and gain > max(0.001, abs(old_score) * self.config["equip_min_gain"]):
                options.append((gain, {"item_id": best["id"], "slot_idx": idx}))
        if options:
            return max(options, key=lambda x: x[0])[1], "equip", 3

    def plan_upgrade(self, s):
        c = s.get("character", {})
        max_level = c.get("level", 0) - self.config["upgrade_level_gap"]
        items = [e for e in s.get("equipment", []) if e["id"] in c.get("equip_slots", [])
                 and equipment_allowed(self.config,e) and self.safe_flag(s,e) and e.get("upgrade_enough") and e.get("level", 999) < min(max_level, s.get('max_upgrade_level', 90))
                 and e["id"] not in self.config["protected_equipment"]]
        # An unaffordable low-level item must not block other equipped items.
        items = [e for e in items if all(
            self.spendable(s,r['kind'],int(r['id']), consumer='upgrade') - int(r["count"]) >= self.config["upgrade_reserve"]
            for r in e.get("upgrade_needs", []))]
        if items:
            item = min(items, key=lambda e: (e["level"], -self.score(e)))
            return {"item_id": item["id"]}, "equipment_upgrade", 10

    def _synthesis_candidates(self, s):
        order = ["common", "fine", "rare", "epic", "legend", "myth", "perfect", "innate", "treasure"]
        cap = order.index(self.config["synth_max_quality"])
        c = s.get("character", {})
        excluded = set(c.get("equip_slots", [])) | set(self.config["protected_equipment"])
        groups = {}
        best = {}
        for e in s.get("equipment", []):
            slot = e.get("slot")
            if equipment_allowed(self.config, e) and e.get("level", 0) <= c.get("level", 0) and (slot not in best or self.score(e) > self.score(best[slot])):
                best[slot] = e
        if self.config['equip_use_weights']:
            excluded.update(e["id"] for e in best.values())
        else:
            # Preserve the fixed-stat Pareto frontier, one representative per tie.
            candidates = [e for e in s.get('equipment',[]) if equipment_allowed(self.config,e) and e.get('level',999)<=c.get('level',0)]
            for e in candidates:
                peers=[x for x in candidates if x.get('slot')==e.get('slot') and x['id']!=e['id']]
                if not any(self.fixed_upgrade(x,e) or (x.get('fixed_stats')==e.get('fixed_stats') and x['id']<e['id']) for x in peers): excluded.add(e['id'])
        for e in s.get("equipment", []):
            if not equipment_allowed(self.config,e) or e["id"] in excluded or e.get("quality") not in order[:cap+1]:
                continue
            if e.get('level', 0) >= s.get('max_equip_level', 80): continue
            groups.setdefault(e["quality"], []).append(e["id"])
        return groups

    def synthesis_status(self, s):
        groups = self._synthesis_candidates(s)
        required = max(1, int(s.get('synth_count', 5)))
        equipment = s.get('equipment', [])
        preserved = sum(e.get('bound') is not True and trade_preserved(self.config,'equipment',e) for e in equipment)
        counts = {quality: len(groups.get(quality, [])) for quality in QUALITIES}
        ready = any(count >= required for count in counts.values()) and s.get('features', {}).get('synth') is not False
        if not equipment:
            message = '等待游戏同步背包装备。'
        elif s.get('features', {}).get('synth') is False:
            message = '等待角色解锁装备合成。'
        elif ready:
            message = f'已有同品质{required}件合格原料；穿戴、锁定、保护及各类最佳装备已排除。'
        elif preserved == len(equipment):
            message = f'背包{len(equipment)}件均为可交易或绑定未知；交易保护开启，当前可合成0组。'
        else:
            detail = '、'.join(f'{QUALITIES[q]}{n}件' for q,n in counts.items() if n) or '0件'
            message = f'同品质需{required}件；当前可用{detail}。交易保护保留{preserved}件，并排除穿戴、锁定、手动保护、各类最佳及品质上限外装备。'
        return {'ready': ready, 'required': required, 'total': len(equipment), 'preserved_tradable_or_unknown': preserved,
                'eligible_by_quality': counts, 'max_quality': self.config['synth_max_quality'], 'message': message}

    def plan_synth(self, s):
        if s.get('features', {}).get('synth') is False: return
        groups = self._synthesis_candidates(s)
        required = max(1, int(s.get("synth_count", 5)))
        for group in groups.values():
            if len(group) >= required:
                return {"item_ids": group[:required]}, "synth", 20

    def plan_material_synth(self, s):
        if not s.get('features', {}).get('synth'): return
        needs = {}
        cap = min(s.get('max_upgrade_level', 90), s.get('character', {}).get('level', 0) - self.config['upgrade_level_gap'])
        for e in s.get('equipment', []):
            if (self.config['growth_linked'] or not self.config['tasks']['upgrade'] or not equipment_allowed(self.config, e)
                    or e.get('level', cap) >= cap or e['id'] not in s.get('character', {}).get('equip_slots', [])): continue
            for req in e.get('upgrade_needs', []):
                if req.get('kind', 'material') == 'material':
                    mid = int(req['id']); needs[mid] = needs.get(mid, 0) + int(req['count'])
        needs = {mid: amount + self.config['upgrade_reserve'] for mid, amount in needs.items()}
        if self.config['growth_linked']:
            for row in self.ledger(s).rows():
                if row['kind'] == 'material' and any(owner in row['owners'] for owner in ('upgrade', 'material_synth')):
                    needs[row['id']] = max(needs.get(row['id'], 0), row['need'])
        for r in s.get('material_synthesis', []):
            if not r.get('unlocked') or not self.safe_flag(s,r): continue
            if self.config['material_synth_demand_only'] and source_blocked(self.config, s, 'material', r['output_id']): continue
            deficit = max(0, needs.get(r['output_id'], 0) - available(self.config,s,'material',r['output_id']))
            if self.config['material_synth_demand_only'] and deficit <= 0: continue
            count = min(int((self.spendable(s,'material',r['input_id'],consumer='material_synth',total=r.get('count',0)) - self.config['material_synth_reserve']) // max(1, r['required_count'])), self.config['material_synth_batch'])
            if self.config['material_synth_demand_only']: count = min(count, int(deficit))
            if count > 0: return {'material_id': r['input_id'], 'count': count}, 'synth', 30
