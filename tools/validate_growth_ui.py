"""Headless browser checks against the current local client, with POSTs blocked."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.version import VERSION


def main():
    output = ROOT / 'runtime/exe-validation'
    errors, writes, layouts = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        page.on('pageerror', lambda error: errors.append(str(error)))
        def route(request):
            if request.request.method != 'GET':
                writes.append(request.request.method)
                request.abort()
            else:
                request.continue_()
        page.route('**/*', route)
        page.goto('http://127.0.0.1:17321', wait_until='networkidle')
        page.wait_for_function('version => status?.app_version === version && status.connected && status.state.ready', arg=VERSION, timeout=60000)
        if page.locator('#disclaimer-dialog').is_visible():
            page.locator('#disclaimer-later').click()
        assert page.locator('.function-card').count() == 43
        assert page.locator('#growth-steps li').count() == 6
        assert page.locator('#growth-needs tr').count() > 0
        assert page.locator('[data-card="resource_realm"]').count() == 1
        assert page.locator('[data-card="world_explore"] option[value="auto"]').count() == 1
        assert page.locator('#preserve-steam').is_checked()
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 1100})
            for theme in ('light', 'dark'):
                page.locator('#theme').select_option(theme)
                dimensions = page.evaluate('({width: innerWidth, scroll: document.documentElement.scrollWidth, border: getComputedStyle(document.querySelector("#growth-panel")).borderTopWidth})')
                assert dimensions['scroll'] <= width + 1, dimensions
                assert dimensions['border'] == '1px', dimensions
                page.locator('#growth-panel').screenshot(path=str(output / f'growth-{theme}-{width}.png'))
                layouts.append({'width': width, 'theme': theme, **dimensions})
            page.locator('[data-tab="settings"]').click()
            assert page.locator('[name="growth_linked"], [data-setting="growth_linked"], #global-fields input').count() > 0
            page.locator('[data-tab="overview"]').click()
        assert not errors, errors
        assert not writes, writes
        browser.close()
    result = {'status': 'PASS', 'app_version': VERSION, 'source_fingerprint': source_fingerprint(ROOT),
              'evidence_kind': 'headless_chromium_live_local_status', 'task_cards': 43,
              'layouts': layouts, 'page_errors': errors, 'post_requests': writes,
              'screenshots': [f'growth-{t}-{w}.png' for w in (1440, 390) for t in ('light', 'dark')]}
    (output / 'growth-ui.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
