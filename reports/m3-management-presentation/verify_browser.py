"""Verify local fixture previews with installed Chrome; no server or model calls.

Uses the environment's existing websockets and pdfplumber packages.
"""
import asyncio
import base64
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
from urllib.request import urlopen

from lxml import html
import pdfplumber
import websockets

folder = Path(__file__).parent.resolve()
repository = folder.parents[1]
chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')


async def verify(port):
    with urlopen(f'http://127.0.0.1:{port}/json', timeout=5) as response:
        targets = json.load(response)
        target = next(t for t in targets if t['type'] == 'page' and t['url'] == 'about:blank')
    async with websockets.connect(target['webSocketDebuggerUrl'], max_size=None) as socket:
        sequence = 0

        async def call(method, params=None):
            nonlocal sequence
            sequence += 1
            await socket.send(json.dumps({'id': sequence, 'method': method, 'params': params or {}}))
            while True:
                try:
                    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                except TimeoutError:
                    raise RuntimeError(f'Chrome did not respond to {method}') from None
                if message.get('id') == sequence:
                    if 'error' in message:
                        raise RuntimeError(message['error'])
                    return message.get('result', {})

        async def evaluate(expression):
            result = await call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
            if 'exceptionDetails' in result:
                raise RuntimeError(result['exceptionDetails'])
            return result['result'].get('value')

        async def navigate(filename):
            # All styles are inline. Load the exact preview bytes into a blank
            # page, avoiding browser policy restrictions on file navigation.
            await evaluate("history.replaceState(null, '', location.href.split('#')[0]); true")
            tree = await call('Page.getFrameTree')
            await call('Page.setDocumentContent', {
                'frameId': tree['frameTree']['frame']['id'],
                'html': (folder / filename).read_text(encoding='utf-8')})
            for _ in range(50):
                await asyncio.sleep(.1)
                if await evaluate('document.readyState === "complete"'):
                    await evaluate('document.fonts.ready.then(() => true)')
                    await evaluate('scrollTo(0, 0); true')
                    return
            raise RuntimeError(f'Local preview did not load: {filename}')

        await call('Page.enable')
        await asyncio.sleep(.5)
        results = []
        for filename, output, width, height in (
            ('management_before_focus.html', 'management_before.png', 1200, 1200),
            ('management_after_focus.html', 'management_after.png', 1200, 1200),
            ('management_after_focus.html', 'management_mobile.png', 390, 844),
        ):
            await call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                       'deviceScaleFactor': 1, 'mobile': width < 500})
            await navigate(filename)
            metrics = await evaluate('''JSON.parse(JSON.stringify({
                viewport: innerWidth, documentWidth: document.documentElement.scrollWidth,
                profileCollapsed: !document.querySelector('.bo-management-support')?.open,
                categoryCards: document.querySelectorAll('.bo-management-card').length,
                assessmentGaps: document.querySelectorAll('.bo-management-assessment-gaps li').length
            }))''')
            assert metrics['documentWidth'] <= metrics['viewport'], metrics
            layout = await call('Page.getLayoutMetrics')
            screenshot = await call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True,
                'clip': {'x': 0, 'y': 0, 'width': width, 'height': max(height, layout['cssContentSize']['height']), 'scale': 1}})
            (folder / output).write_bytes(base64.b64decode(screenshot['data']))
            if filename == 'management_after_focus.html':
                await evaluate("document.querySelector('.bo-management-finding .source-cite a').click()")
                await asyncio.sleep(.1)
                metrics['citationOpensSupportingEvidence'] = await evaluate("document.querySelector('.bo-management-support').open")
                assert metrics['citationOpensSupportingEvidence'], metrics
                assert metrics['profileCollapsed'] and metrics['categoryCards'] == 1 and metrics['assessmentGaps'] == 4, metrics
            results.append({'file': output, **metrics})

        await call('Emulation.clearDeviceMetricsOverride')
        await navigate('management_print_focus.html')
        pdf = await call('Page.printToPDF', {'printBackground': True, 'preferCSSPageSize': True,
                                           'displayHeaderFooter': False})
        (folder / 'management_sample.pdf').write_bytes(base64.b64decode(pdf['data']))
        (folder / 'browser_verification.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        await call('Browser.close')


with TemporaryDirectory(prefix='.chrome-verify-', dir=repository, ignore_cleanup_errors=True) as profile:
    process = subprocess.Popen([str(chrome), '--headless=new', '--disable-gpu', '--disable-background-networking',
        '--disable-extensions', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
        '--user-data-dir=' + profile, 'about:blank'], creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        active = Path(profile) / 'DevToolsActivePort'
        for _ in range(100):
            if active.exists():
                break
            time.sleep(.1)
        port = int(active.read_text(encoding='utf-8').splitlines()[0])
        asyncio.run(verify(port))
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)

with pdfplumber.open(folder / 'management_sample.pdf') as pdf:
    text = ' '.join(' '.join(page.extract_text() or '' for page in pdf.pages).split())
    preview = html.fromstring((folder / 'management_print_focus.html').read_text(encoding='utf-8'))
    overall = ' '.join(preview.xpath('//*[@class="memo-claim bo-management-overall"]/p[1]')[0].text_content().split())
    qualifications = preview.xpath('//*[@class="qualification"]')
    result = {'renderer': 'Installed Chrome via DevTools printToPDF', 'pages': len(pdf.pages),
              'overall_present': overall in text,
              'qualifications_present': all(' '.join(q.text_content().split()) in text for q in qualifications),
              'sources_present': 'mgmt-page-2' in text and 'p. 2' in text,
              'biographies_absent': 'Appointment:' not in text and 'Recorded tenure:' not in text,
              'assessment_gaps_present': 'Areas Requiring Further Assessment' in text}
    assert result['pages'] == 1 and all(value for key, value in result.items() if key not in ('renderer', 'pages')), result
    pdf.pages[0].to_image(resolution=120).save(folder / 'management_sample_page1.png')
    (folder / 'pdf_verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
