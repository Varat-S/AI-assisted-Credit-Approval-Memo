"""Extract Management from the verified fixture HTML for visual inspection."""
from pathlib import Path

from lxml import html

folder = Path(__file__).parent


def clean(text):
    return '\n'.join(line.rstrip() for line in text.splitlines()) + '\n'


for source, output in (
    ('management_before_preview.html', 'management_before_focus.html'),
    ('management_web_preview.html', 'management_after_focus.html'),
    ('management_print_preview.html', 'management_print_focus.html'),
):
    source_text = clean((folder / source).read_text(encoding='utf-8'))
    (folder / source).write_text(source_text, encoding='utf-8')
    page = html.fromstring(source_text)
    head = html.tostring(page.xpath('//head')[0], encoding='unicode')
    section = html.tostring(page.xpath('//*[@data-memo-section="management"]')[0], encoding='unicode')
    body = ('<body style="max-width:1050px;margin:0 auto;padding:24px">'
            '<div class="bo-four-section">' + section + '</div></body>')
    (folder / output).write_text(clean('<!doctype html><html lang="en">' + head + body + '</html>'), encoding='utf-8')
