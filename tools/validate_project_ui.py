"""Exercise the source UI with live read-only status and isolated browser storage."""
import io
import json
from pathlib import Path
import sys
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.local_http import open_local
from fanxiu_assistant.verification import source_fingerprint


def main():
    output = ROOT / 'runtime/exe-validation'
    output.mkdir(parents=True, exist_ok=True)
    with open_local('http://127.0.0.1:17321/api/status', timeout=5) as response:
        state = json.load(response)
    # Verify the deployed optional JSON uses the real HTTP response path.
    with open_local('http://127.0.0.1:17321/project-info.json', timeout=5) as response:
        assert json.load(response) == json.loads((ROOT / 'web/project-info.json').read_text(encoding='utf-8'))
    with open_local('http://127.0.0.1:17321/project-info.js', timeout=5) as response:
        assert response.read() == (ROOT / 'web/project-info.js').read_bytes()
    info = json.loads((ROOT / 'web/project-info.json').read_text(encoding='utf-8'))
    if info.get('appreciation_image'):
        with open_local('http://127.0.0.1:17321' + info['appreciation_image'], timeout=5) as response:
            assert response.read() == (ROOT / 'web/appreciation-code.webp').read_bytes()
    posts, errors, layouts = [], [], []
    fake = io.BytesIO()
    Image.new('RGB', (600, 600), 'white').save(fake, format='WEBP')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100})
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        def route(request):
            path = request.request.url.split('17321')[-1].split('?')[0]
            if request.request.method != 'GET':
                posts.append(request.request.method)
                return request.abort()
            if path == '/api/status':
                return request.fulfill(json=state)
            file = ROOT / 'web' / ('index.html' if path == '/' else path.lstrip('/'))
            if file.is_file() and file.parent == ROOT / 'web':
                mime = {'.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.html': 'text/html', '.webp': 'image/webp'}.get(file.suffix)
                return request.fulfill(body=file.read_bytes(), content_type=mime)
            request.abort()
        context.route('**/*', route)
        page.goto('http://127.0.0.1:17321', wait_until='networkidle')
        dialog = page.locator('#disclaimer-dialog')
        assert dialog.is_visible()
        assert page.locator('#disclaimer-acknowledge').is_disabled()
        page.locator('#disclaimer-later').click()
        assert page.evaluate("localStorage.getItem('fanxiu.disclaimer.read')") is None
        page.reload(wait_until='networkidle')
        assert dialog.is_visible()
        page.wait_for_function("!document.querySelector('#disclaimer-acknowledge').disabled")
        page.locator('#disclaimer-acknowledge').click()
        assert page.evaluate("localStorage.getItem('fanxiu.disclaimer.read')") == '2026-11-17.2'
        page.reload(wait_until='networkidle')
        assert not dialog.is_visible()
        page.locator('#project-info [data-open-disclaimer]').click()
        assert dialog.is_visible()
        page.keyboard.press('Escape')
        assert not dialog.is_visible()
        assert page.locator('#project-info [data-open-disclaimer]').evaluate('(el) => el === document.activeElement')
        assert page.locator('#reference-github, #appreciation-owner, #appreciation-dialog-owner').count() == 0
        assert 'Auto_Dps' not in page.locator('#project-info').inner_text()
        assert 'o3o' not in page.locator('#project-info').inner_text()
        assert page.locator('#project-github').get_attribute('href') == 'https://github.com/weixiao030/Auto_fanxiu'
        assert page.locator('#project-github').get_attribute('rel') == 'noopener noreferrer'

        if info.get('appreciation_image'):
            assert page.locator('#appreciation-preview').is_visible()
            assert page.locator('#appreciation-code').evaluate('(img) => img.naturalWidth >= 600')
            page.locator('#appreciation-preview').click()
            assert page.locator('#appreciation-dialog').is_visible()
            page.screenshot(path=str(output / 'appreciation-dialog.png'))
            page.locator('#appreciation-close').click()
        # An owner-supplied image is optional; failure leaves all game controls usable.
        context.route('**/project-info.json', lambda r: r.fulfill(json={
            'github_url': 'https://github.com/example/project',
            'appreciation_image': '/appreciation-code.webp',
            'appreciation_owner': '仅用于浏览器回归的测试图片'}))
        context.route('**/appreciation-code.webp', lambda r: r.fulfill(body=fake.getvalue(), content_type='image/webp'))
        page.reload(wait_until='networkidle')
        assert page.locator('#appreciation-preview').is_visible()
        assert page.locator('#project-github').is_visible()
        page.locator('#appreciation-preview').click()
        assert page.locator('#appreciation-dialog').is_visible()
        page.locator('#appreciation-close').click()
        context.unroute('**/project-info.json')
        context.unroute('**/appreciation-code.webp')
        page.reload(wait_until='networkidle')
        partner = state['state'].get('partner', {})
        state['state']['partner'] = dict(partner, self_is_captor=True)
        page.reload(wait_until='networkidle')
        assert page.locator('[data-rescue-status]').is_visible()
        assert '当前角色看管' in page.locator('[data-rescue-status]').inner_text()
        state['state']['partner'] = dict(partner, self_is_captor=False)
        page.reload(wait_until='networkidle')
        assert not page.locator('[data-rescue-status]').is_visible()
        state['state']['partner'] = partner
        multiplayer = state['state'].get('multiplayer', {})
        state['state']['multiplayer'] = dict(multiplayer, enabled=True, escape_supported=False)
        page.reload(wait_until='networkidle')
        assert not page.locator('[data-param="mp_escape_hp"]').is_visible()
        assert page.locator('[data-mp-capability]').is_visible()
        state['state']['multiplayer']['escape_supported'] = True
        page.reload(wait_until='networkidle')
        assert page.locator('[data-param="mp_escape_hp"]').is_visible()
        assert not page.locator('[data-mp-capability]').is_visible()
        # Refresh the same card across lifecycle transitions; no reload may clear stale text.
        def mp_status(value):
            state['state']['multiplayer'] = value
            page.evaluate("value => {status.state.multiplayer=value;render();}", value)
            return page.locator('[data-mp-status]').inner_text()
        assert '暂未开放' in mp_status(dict(enabled=False, suspended=True))
        assert '自动入场已关闭' in mp_status(dict(enabled=True, suspended=False, active=False))
        assert '暂停或未开放' not in page.locator('[data-feedback="multiplayer_realm"]').inner_text()
        assert '重复入场' in mp_status(dict(enabled=True, active=True, admission_pending=True, state='reserving'))
        assert '生命待同步' in mp_status(dict(enabled=True, active=True, state='in_combat', hp_known=False, hp_percent=None))
        assert '等待新状态' in mp_status(dict(enabled=True, active=True, state='exploring', stale=True))
        assert '生命 80%' in mp_status(dict(enabled=True, active=True, state='exploring', hp_known=True, hp_percent=80, elapsed_seconds=61, elapsed_source='observed'))
        assert '已观察 61' in page.locator('[data-mp-status]').inner_text()
        assert '原生事件策略' in mp_status(dict(enabled=True, active=True, state='choosing', event={'options':[]}))
        page.locator('[data-card="multiplayer_realm"]').screenshot(path=str(output / 'multiplayer-1440.png'))
        page.set_viewport_size({'width':390, 'height':1100})
        page.locator('[data-card="multiplayer_realm"]').screenshot(path=str(output / 'multiplayer-390.png'))
        state['state']['multiplayer'] = multiplayer
        page.reload(wait_until='networkidle')
        for width in (1920, 1440, 1024, 768, 390):
            page.set_viewport_size({'width': width, 'height': 1100})
            for theme in ('light', 'dark'):
                page.locator('#theme').select_option(theme)
                assert page.locator('#project-info').is_visible()
                dims = page.evaluate('''() => {
                  const main = document.querySelector('.workspace-main').getBoundingClientRect();
                  const rail = document.querySelector('#project-info').getBoundingClientRect();
                  return {scroll: document.documentElement.scrollWidth, width: innerWidth,
                    rail_right: rail.right, main_right: main.right, rail_left: rail.left};
                }''')
                assert dims['scroll'] <= width + 1, dims
                assert dims['rail_right'] <= width + 1, dims
                if width >= 1200:
                    assert dims['rail_left'] >= dims['main_right'], dims
                page.locator('#project-info [data-open-disclaimer]').click()
                box = dialog.bounding_box()
                assert box['width'] <= width and box['x'] >= 0, box
                page.screenshot(path=str(output / f'project-dialog-{theme}-{width}.png'))
                page.keyboard.press('Escape')
                page.locator('#project-info').screenshot(path=str(output / f'project-info-{theme}-{width}.png'))
                layouts.append({'theme': theme, **dims})
        assert not errors, errors
        assert not posts, posts
        browser.close()
    result = {'status': 'PASS', 'source_fingerprint': source_fingerprint(ROOT),
              'evidence_kind': 'source_ui_live_read_only_status_isolated_browser',
              'layouts': layouts, 'page_errors': errors, 'post_requests': posts,
              'actual_payment_image_configured': json.loads((ROOT / 'web/project-info.json').read_text(encoding='utf-8')).get('appreciation_image') is not None,
              'scope': 'Declaration timing, dismiss/acknowledge/reopen, focus, persistence, responsive rail and optional image. Synthetic white image only checks image-preview interaction; it is not payment or QR-scanning evidence.'}
    (output / 'project-ui.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
