"""Safe, read-only annotation of a checksum-verified original HTML filing."""
from secrets import token_urlsafe
from urllib.parse import urljoin

from lxml import html

from app.services.analysis_workspace import safe_url
from app.services.bo.hypotheses import normalise, _TRANSLATE


def highlighted_original(data, quotation, source_url=None):
    root = html.document_fromstring(data, parser=html.HTMLParser(no_network=True))
    # Never execute source-provided active content in the application origin.
    for node in list(root.iter()):
        if not isinstance(node.tag, str):
            continue
        tag = node.tag.lower().split(':')[-1]
        if tag in {'script', 'iframe', 'object', 'embed', 'base', 'link'} or (tag == 'meta' and node.get('http-equiv')):
            node.drop_tree()
            continue
        for attr in list(node.attrib):
            if attr.lower().startswith('on') or attr.lower() in {'srcdoc', 'action', 'formaction'}:
                del node.attrib[attr]
            elif attr.lower() in {'href', 'src', 'xlink:href'}:
                target = safe_url(urljoin(source_url or '', node.attrib[attr]))
                if target:
                    node.attrib[attr] = target
                else:
                    del node.attrib[attr]
    body = root.find('body')
    if body is None:
        return None
    slots, chars, positions = [], [], []
    def append(text, slot=None):
        for offset, char in enumerate(text or ''):
            value = char.translate(_TRANSLATE)
            if value.isspace():
                value = ' '
            if not value or (value == ' ' and (not chars or chars[-1] == ' ')):
                continue
            chars.append(value)
            positions.append((slot, offset) if slot is not None else None)
    blocks = {'p', 'div', 'td', 'th', 'tr', 'table', 'br', 'h1', 'h2', 'h3', 'h4', 'li'}
    def walk(node):
        if not isinstance(node.tag, str):
            return
        tag = node.tag.lower().split(':')[-1]
        if tag in {'script', 'style', 'hidden'} or 'display:none' in node.get('style', '').replace(' ', '').lower():
            return
        if tag in blocks:
            append(' ')
        if node.text:
            slot = len(slots); slots.append((node, 'text', node.text)); append(node.text, slot)
        for child in list(node):
            walk(child)
            if child.tail:
                slot = len(slots); slots.append((child, 'tail', child.tail)); append(child.tail, slot)
        if tag in blocks:
            append(' ')
    walk(body)
    haystack, needle = ''.join(chars), normalise(quotation)
    if not needle or needle not in haystack:
        return None
    start, ranges, count = 0, {}, 0
    while (start := haystack.find(needle, start)) >= 0:
        occurrence = {}
        for pos in positions[start:start+len(needle)]:
            if pos:
                slot, offset = pos
                occurrence.setdefault(slot, []).append(offset)
        for slot, offsets in occurrence.items():
            ranges.setdefault(slot, []).append((min(offsets), max(offsets)+1))
        count += 1
        start += len(needle)
    mark_number = 0
    for slot in sorted(ranges, reverse=True):
        node, kind, original = slots[slot]
        bounds = sorted(set(ranges[slot]))
        marks = []
        for i, (begin, end) in enumerate(bounds):
            mark = html.Element('mark', {'class': 'bo-original-highlight'})
            mark.text = original[begin:end]
            mark.tail = original[end:bounds[i+1][0] if i+1 < len(bounds) else len(original)]
            mark.set('id', 'bo-original-highlight-' + str(mark_number))
            mark_number += 1
            marks.append(mark)
        if kind == 'text':
            node.text = original[:bounds[0][0]]
            for index, mark in enumerate(marks):
                node.insert(index, mark)
        else:
            node.tail = original[:bounds[0][0]]
            for mark in reversed(marks):
                node.addnext(mark)
    # Choose the first mark in document order, even when quotation spans nodes.
    first = root.xpath('//mark[@class="bo-original-highlight"]')[0]
    first.set('id', 'bo-original-quote-target')
    nonce = token_urlsafe(24)
    head = root.find('head')
    if head is None:
        head = html.Element('head'); root.insert(0, head)
    style = html.Element('style')
    style.text = '.bo-original-highlight{background:#ffe36b!important;color:#111!important;outline:1px solid #c48b13!important;scroll-margin-top:64px}#bo-original-notice{position:sticky;top:0;z-index:2147483647;padding:10px 16px;background:#f5f8f7;color:#344955;border:1px solid #c7d5d4;font:14px Arial,sans-serif}'
    head.append(style)
    notice = html.Element('div', id='bo-original-notice')
    notice.text = 'Original 10-K · Verified Local Copy · Quotation Highlighted' + (f' · {count} Matching Occurrences' if count > 1 else '')
    body.insert(0, notice)
    script = html.Element('script', nonce=nonce)
    script.text = "document.getElementById('bo-original-quote-target').scrollIntoView({block:'center'});"
    body.append(script)
    csp = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-" + nonce +
           "'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return html.tostring(root, encoding='unicode', doctype='<!doctype html>'), csp
