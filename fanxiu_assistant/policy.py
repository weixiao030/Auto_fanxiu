from __future__ import annotations
from copy import deepcopy
import time
import uuid
from .settings import DEFAULTS, LABELS, QUALITIES, CONFIG_FIELDS, validate_config
from .protection import available, command_keys, keys_overlap
from .breakthrough import preparation
from .growth import ResourceLedger
from .outcomes import shared_backoff
from .task_catalog import TASK_ORDER, TASK_BY_KIND, ordered_tasks
from .modules.supply import SupplyPlans
from .modules.equipment import EquipmentPlans
from .modules.cultivation import CultivationPlans
from .modules.world import WorldPlans
from .modules.social import SocialPlans


class Planner(SupplyPlans, EquipmentPlans, CultivationPlans, WorldPlans, SocialPlans):
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.due = {}
        self.challenges = {}
        self.last_action = 0
        self.server_busy_until = 0
        self.reason = "等待连接游戏"
        self.config = deepcopy(DEFAULTS)
        self.cursor = 0
        self.item_due = {}
        self.focus_streak = 0
        self._resource_ledger = None
        self._ledger_config = None
        self._ledger_state = None

    def protection_policy(self):
        return {k: deepcopy(self.config[k]) for k in (
            'preserve_steam_tradable', 'preserve_tradable', 'trade_rules',
            'manual_locks', 'protected_equipment')}

    def safe_flag(self, state, row, key='bound_only_safe'):
        if state.get('bridge_revision', 0) >= 21 and state.get('protection_policy') != self.protection_policy():
            return False  # Wait for flags computed with the latest protection rules.
        # Revision 13 computes this flag against category, quality and fixed locks.
        return row.get(key) is True if state.get('bridge_revision',0)>=13 else (not (self.config['preserve_tradable'] or self.config['preserve_steam_tradable']) or row.get(key) is True)

    def choose(self, state, only_kind=None):
        now = self.clock()
        self._resource_ledger = None
        self.reason = "等待下次调度"
        if not state.get("ready") or not state.get("online"):
            self.reason = "等待客户端就绪；助手不执行登录"
            return
        if state.get("network_blocked"):
            self.reason = "客户端连接已暂停，请在游戏中恢复会话"
            return
        if state.get('client_update', {}).get('state') == 'required':
            self.reason = '原游戏要求更新，等待Steam更新并恢复连接'
            return
        if not state.get("tutorial_finished"):
            self.reason = "等待完成新手引导"
            return
        if state.get("battle") or state.get("battle_pending") or state.get("pending", 0) > 0:
            self.reason = "等待游戏当前操作或战斗完成"
            return
        if now < self.server_busy_until:
            self.reason = f'服务器繁忙，等待{max(1, int(self.server_busy_until-now)+1)}秒后重试'
            return
        if now - self.last_action < self.config["interval"]:
            return
        character = state.get("character", {})
        if self.config["stop_at_level"] and character.get("level", 0) >= self.config["stop_at_level"]:
            self.reason = "已达到目标等级"
            return
        growth = self.growth_status(state)
        tasks, focused = ordered_tasks(self.cursor, state, self.config, growth, self.focus_streak)
        # Prefer a usable forge before ordinary refinement, without moving either
        # ahead of unrelated tasks or bypassing explicit single-task requests.
        if (self.config['growth_linked'] and self.config['tasks']['world_forge']
                and now >= self.due.get('world_forge', 0) and growth['world_forge']['ready']
                and self._world_candidates(state, 'world_forge', ['forge'])):
            ordinary = tasks.index('refine')
            if tasks.index('world_forge') > ordinary:
                tasks.remove('world_forge')
                tasks.insert(ordinary, 'world_forge')
        for kind in tasks:
            index = TASK_ORDER.index(kind)
            feature = TASK_BY_KIND[kind].feature
            if feature and state.get('features', {}).get(feature) is False:
                continue
            if only_kind is not None and kind != only_kind: continue
            if state.get('multiplayer', {}).get('active') and kind != 'multiplayer_realm':
                continue
            if not self.config["tasks"].get(kind) or now < self.due.get(kind, 0):
                continue
            candidate = getattr(self, "plan_" + kind)(state)
            if candidate:
                params, key, cooldown = candidate[:3]
                actual_kind = candidate[3] if len(candidate) > 3 else kind
                if now < self.due.get(actual_kind, 0): continue
                touched = command_keys(actual_kind,params,state)
                locks = self.config['manual_locks'] + [f'equipment:{eid}' for eid in self.config['protected_equipment']]
                if any(keys_overlap(a,b) for a in touched for b in locks):
                    continue
                self.due[kind] = now + cooldown
                self.due[actual_kind] = now + cooldown
                self.last_action = now
                self.cursor = (index + 1) % len(TASK_ORDER)
                self.focus_streak = self.focus_streak + 1 if kind in focused else 0
                self.reason = LABELS[kind] + (" · " + LABELS[actual_kind] if actual_kind != kind else "")
                return {"id": uuid.uuid4().hex, "kind": actual_kind, "params": params,
                        "result_key": key, "label": self.reason, "parent_kind": kind}
        self.reason = "修炼中，等待资源、等级或下一次任务"

    def observe_result(self, command, result, state):
        kind = command["kind"]
        if not result.get("ok"):
            retry = (self.config['challenge_retry_seconds'] if kind == 'challenge' else
                     self.config['realm_retry_seconds'] if kind == 'realm_challenge' else
                     self.config['pvp_retry_seconds'] if kind in ('partner_rescue', 'player_capture', 'player_occupy', 'bounty_claim') else 30)
            self.due[kind] = max(self.due.get(kind, 0), self.clock() + retry)
            delay = shared_backoff(result)
            if delay:
                # Pause dispatch; never replay an unconfirmed command or settlement here.
                deadline = self.clock() + delay
                self.server_busy_until = max(self.server_busy_until, deadline)
                self.due[kind] = max(self.due[kind], deadline)
        if not result.get('ok') and command.get('parent_kind') == 'breakthrough':
            self.due['breakthrough'] = max(self.due.get('breakthrough', 0), self.due.get(kind, 0), self.clock() + 30)
        if kind == 'world_events' and not result.get('ok'):
            self.due['world_sync'] = 0
        marker = command.get('params', {}).get('marker_id')
        if marker is not None:
            self.item_due[(kind, marker)] = self.clock() + (300 if kind in ('player_capture','player_occupy') and result.get('ok') else 10 if result.get('ok') else self.config['realm_retry_seconds'] if kind == 'realm_challenge' else self.config['pvp_retry_seconds'] if kind in ('player_capture','player_occupy') else 300)
        if kind in ('slave_escape', 'bounty_publish'):
            # A lost acknowledgement must never repeat a consumable or extend captivity again.
            self.item_due[(kind, str(command['params'].get('capture_id', '')))] = self.clock() + 86400
        if kind == 'partner_social':
            self.item_due[(kind, command['params'].get('target', ''))] = self.clock() + 86400
        if kind == 'bounty_claim':
            self.item_due[(kind, command['params']['event_id'])] = self.clock() + self.config['pvp_retry_seconds']
        if kind == "challenge":
            self.challenges[command["params"]["key"]] = {
                "at": self.clock(), "won": result.get("data", {}).get("won", False),
                "level": state.get("character", {}).get("level", 0),
            }

    def ledger(self, state):
        if self._resource_ledger is None or self._ledger_state is not state or self._ledger_config != self.config:
            self._resource_ledger = ResourceLedger(self.config, state)
            self._ledger_state = state
            self._ledger_config = deepcopy(self.config)
        return self._resource_ledger

    def growth_status(self, state):
        return self.ledger(state).public(self.safe_flag)

    def spendable(self, s, kind, item_id, consumer='background', **kwargs):
        if not self.config['growth_linked']:
            count = available(self.config, s, kind, item_id, **kwargs)
            held = preparation(self.config, s)['reserved'].get(f'{kind}:{int(item_id)}', 0)
            return max(0, count - held)
        return self.ledger(s).spendable(kind, item_id, consumer, **kwargs)
