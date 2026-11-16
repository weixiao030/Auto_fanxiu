"""Keep only bounded, non-secret failure metadata from native acknowledgements."""
import math
import re

_CODE = re.compile(r'[A-Za-z0-9_.-]{1,96}\Z')
_BUSY_CODES = {'SERVER_BUSY', 'RATE_LIMITED', 'TOO_MANY_REQUESTS', 'SERVICE_UNAVAILABLE'}


def failure_metadata(result):
    data = result.get('data') if isinstance(result, dict) else None
    raw = data.get('failure') if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for key in ('code', 'error_code'):
        value = raw.get(key)
        if isinstance(value, str) and _CODE.fullmatch(value):
            clean[key] = value
    status = raw.get('http_code')
    if type(status) is int and 400 <= status <= 599:
        clean['http_code'] = status
    delay = raw.get('retry_after_seconds')
    if type(delay) in (int, float) and math.isfinite(delay) and 0 < delay <= 86400:
        clean['retry_after_seconds'] = delay
    return clean


def shared_backoff(result):
    failure = failure_metadata(result)
    delay = failure.get('retry_after_seconds', 0)
    codes = {failure.get(key, '').upper() for key in ('code', 'error_code')}
    detail = str(result.get('detail', ''))
    busy = (failure.get('http_code') in (429, 503) or bool(codes & _BUSY_CODES)
            or 'server busy' in detail.lower() or '服务器繁忙' in detail)
    return max(30, delay) if busy else delay


def result_detail(result):
    value = result.get('detail')
    if isinstance(value, str) and value.strip():
        return value.strip()[:600]
    failure = failure_metadata(result)
    code = failure.get('code') or failure.get('error_code')
    if code:
        return '游戏请求失败：' + code
    if failure.get('http_code'):
        return f"游戏请求失败（HTTP {failure['http_code']}）"
    return '游戏已确认操作' if result.get('ok') else '操作失败，游戏未返回具体原因'
