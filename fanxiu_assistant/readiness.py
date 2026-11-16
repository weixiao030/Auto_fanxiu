"""Display only native readiness facts; this module never initiates a login."""

def waiting_message(state):
    queue = state.get('login_queue', {})
    if queue.get('active'):
        if queue.get('claiming'):
            return '原客户端正在申请入场，等待服务器确认。'
        ahead = queue.get('ahead_count')
        detail = f'前方 {ahead} 人；' if type(ahead) is int and ahead >= 0 else ''
        seconds = queue.get('next_poll_seconds')
        poll = f'下次查询 {seconds} 秒后（不是入场预计时间）。' if type(seconds) is int and seconds >= 0 else '等待原客户端按服务器间隔查询。'
        return '原客户端排队中：' + detail + poll
    if queue.get('manual_only'):
        return '原客户端等待手动处理登录，请查看游戏窗口。'
    if state.get('network_blocked'):
        return '原客户端连接中断，正在按原生流程恢复；连接恢复后继续自动任务。'
    recovery = state.get('battle_recovery', {})
    if recovery.get('state') in ('pending', 'replaying', 'blocked'):
        return recovery.get('message') or '正在核对服务器战斗结算，确认后继续自动任务。'
    return '等待原客户端进入角色并同步资源；助手不执行登录。'
