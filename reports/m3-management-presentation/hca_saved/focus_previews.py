"""Extract actual saved-run Management previews; never runs analytical code."""
from pathlib import Path
from lxml import html

folder = Path(__file__).parent
repository = folder.parents[2]
saved = repository / 'output/hca_live_saved/20261103_management'


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

# Use the previous saved live presentation as the comparison. Only incidental
# trailing whitespace in this report copy is cleaned; original files stay intact.
(folder / 'before_web.html').write_text(clean((saved / 'management_web.html').read_text(encoding='utf-8')), encoding='utf-8')
