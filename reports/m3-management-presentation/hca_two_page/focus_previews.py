"""Focus the saved HCA previews; no analytical execution or source changes."""
from pathlib import Path
from lxml import html

folder = Path(__file__).parent


def clean(text):
    return '\n'.join(line.rstrip() for line in text.splitlines()) + '\n'


for source, output in [('web_full.html', 'web.html'), ('print_full.html', 'print.html')]:
    text = clean((folder / source).read_text(encoding='utf-8'))
    (folder / source).write_text(text, encoding='utf-8')
    page = html.fromstring(text)
    head = html.tostring(page.xpath('//head')[0], encoding='unicode')
    section = html.tostring(page.xpath('//*[@data-memo-section="management"]')[0], encoding='unicode')
    body = ('<body><article class="memo-paper"><div class="bo-four-section" '
            'data-run-id="ar_70066e79dd954e3c">' + section + '</div></article></body>')
    (folder / output).write_text(clean('<!doctype html><html lang="en">' + head + body + '</html>'), encoding='utf-8')

(folder / 'before_web.html').write_bytes((folder.parent / 'hca_saved/web.html').read_bytes())
assert (folder / 'web.html').read_bytes() == (folder / 'before_web.html').read_bytes(), 'Interactive preview changed'
