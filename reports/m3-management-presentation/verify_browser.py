"""Verify local fixture previews with installed Chrome; no server or model calls.

Uses the environment's existing websockets and pdfplumber packages.
"""
import asyncio
import argparse
import base64
import json
from pathlib import Path
import subprocess
import re
from tempfile import TemporaryDirectory
import time
from urllib.request import urlopen

from lxml import html
import pdfplumber
import websockets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--saved-hca', action='store_true', help='Use the recorded real HCA previews, with no model calls.')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
folder = Path(__file__).parent.resolve() / 'hca_saved' if args.saved_hca else Path(__file__).parent.resolve()
jobs = ([('before_web.html', 'before.png', 1200, 1200), ('web.html', 'desktop.png', 1200, 1200),
         ('web.html', 'mobile.png', 390, 844)] if args.saved_hca else
        [('management_before_focus.html', 'management_before.png', 1200, 1200),
         ('management_after_focus.html', 'management_after.png', 1200, 1200),
         ('management_after_focus.html', 'management_mobile.png', 390, 844)])
print_file = 'print.html' if args.saved_hca else 'management_print_focus.html'
pdf_file = 'management.pdf' if args.saved_hca else 'management_sample.pdf'
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
        for filename, output, width, height in jobs:
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
            if filename == jobs[1][0]:
                await evaluate("document.querySelector('.bo-management-finding .source-cite a').click()")
                await asyncio.sleep(.1)
                metrics['citationOpensSupportingEvidence'] = await evaluate("document.querySelector('.bo-management-support').open")
                assert metrics['citationOpensSupportingEvidence'], metrics
                assert metrics['profileCollapsed'] and metrics['categoryCards'] == 1 and metrics['assessmentGaps'] == 4, metrics
            results.append({'file': output, **metrics})

        await call('Emulation.clearDeviceMetricsOverride')
        await navigate(print_file)
        pdf = await call('Page.printToPDF', {'printBackground': True, 'preferCSSPageSize': True,
                                           'displayHeaderFooter': False})
        (folder / pdf_file).write_bytes(base64.b64decode(pdf['data']))
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

def normalized(text):
    return ' '.join(re.sub(r'(?<=-)\s*\n\s*(?=\w)', '', text).split())


with pdfplumber.open(folder / pdf_file) as pdf:
    text = normalized('\n'.join(page.extract_text() or '' for page in pdf.pages))
    preview = html.fromstring((folder / print_file).read_text(encoding='utf-8'))
    overall = normalized(preview.xpath('//*[@class="bo-management-assessment-text"]')[0].text_content())
    qualifications = preview.xpath('//*[@class="bo-management-qualifications"]//li')
    source_text = ' '.join(node.text_content() for node in preview.xpath('//*[@class="bo-management-sources"]//li'))
    locators = re.findall(r'Passage offset \d+|Page \d+|Recorded passage', source_text)
    result = {'renderer': 'Installed Chrome via DevTools printToPDF', 'pages': len(pdf.pages),
              'records': 'Real saved HCA run ar_70066e79dd954e3c' if args.saved_hca else 'Synthetic Northfield fixture',
              'overall_present': overall in text,
              'qualifications_present': all(normalized(q.text_content()) in text for q in qualifications),
              'sources_present': bool(locators) and all(locator in text for locator in locators),
              'source_hashes_not_in_narrative': not bool(re.search(r'\b[a-f0-9]{64}\b', text)),
              'biographies_absent': 'Appointment:' not in text and 'Recorded tenure:' not in text,
              'assessment_gaps_present': 'Areas Requiring Further Assessment' in text}
    if args.saved_hca:
        result['qualified_positive_supporting_factor'] = 'Supporting Factor' in text and 'Qualified' in text and 'Credit Concerns' not in text
        result['html_has_no_physical_page_claims'] = 'Page 1' not in text and 'p. 1' not in text
    assert result['pages'] == 1 and all(value for key, value in result.items() if key not in ('renderer', 'pages', 'records')), result
    pdf.pages[0].to_image(resolution=120).save(folder / ('pdf_page1.png' if args.saved_hca else 'management_sample_page1.png'))
    (folder / 'pdf_verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
