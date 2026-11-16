"""Explain dispatch gates without evaluating plans or changing cooldowns."""
from .readiness import waiting_message


def execution_status(state, config, *, connected, heartbeat_age, enabled,
                     pending, pending_seconds, retry_after, minimum_revision,
                     resume_requested=False):
    def result(code, title, message):
        return {'code': code, 'title': title, 'message': message}

    if not connected:
        return result('disconnected', '等待游戏连接', '保持当前游戏运行，等待本机连接；助手不会另开游戏或登录。')
    if heartbeat_age >= 8:
        return result('heartbeat_delayed', '等待新状态', '游戏心跳延迟，等待恢复后再执行，避免使用过期数据。')
    if state.get('bridge_revision', 0) < minimum_revision:
        return result('bridge_update', '等待桥接更新', '已经读到游戏数据，当前桥接仍是旧版；等待空闲时加载新版，保持游戏运行。')
    if state.get('network_blocked') or not state.get('ready'):
        return result('native_wait', '等待原客户端恢复', waiting_message(state))
    if pending:
        return result('settling', '等待游戏确认', f"{pending.get('label', '当前操作')}已安排，等待游戏结算（{max(0, int(pending_seconds))}秒）；暂停后也不重复提交。")
    if not enabled:
        if resume_requested:
            return result('resuming', '等待自动恢复', '已请求自动修炼，等待客户端状态满足恢复条件。')
        return result('paused', '自动修炼已暂停', '读取数据仍会继续。点击“开始自动修炼”后，才会派发已开启的任务；如曾有未确认结果，请先查看运行记录。')
    if state.get('client_update', {}).get('state') == 'required':
        return result('client_update', '游戏要求更新', '原游戏要求新版客户端，等待Steam更新；当前游戏与会话保持原样。')
    if not state.get('online') or not state.get('tutorial_finished'):
        return result('not_ready', '等待角色就绪', '请在原游戏中完成连接和新手引导，助手继续等待。')
    if retry_after > 0:
        return result('backoff', '服务器繁忙', f'所有任务共同等待{max(1, int(retry_after + .999))}秒，再按最新条件执行。')
    if state.get('battle') or state.get('battle_pending') or state.get('pending', 0):
        return result('native_busy', '等待当前游戏操作', '游戏正在处理操作或战斗，结算后继续自动任务。')
    if not any(config.get('tasks', {}).values()):
        return result('tasks_disabled', '没有开启自动任务', '自动修炼已开启，但所有任务开关均关闭；请开启需要的功能。')
    target = config.get('stop_at_level', 0)
    if target and state.get('character', {}).get('level', 0) >= target:
        return result('target_reached', '已达到目标等级', f'已达到设置的{target}级，后续自动任务等待调整目标；设为0可持续成长。')
    if state.get('multiplayer', {}).get('active'):
        message = ('正在按多人秘境设置处理原生状态，常规成长任务等待场次结束。'
                   if config.get('tasks', {}).get('multiplayer_realm') else
                   '角色仍在多人秘境中，当前多人托管开关关闭；常规任务等待该场结束。')
        return result('multiplayer', '多人秘境进行中', message)
    return result('running', '自动修炼正在运行', '按资源、保护规则与冷却调度。缺料时查看下方自动成长路线，已确认结果见运行记录。')
