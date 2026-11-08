"""Exact saved quotations and honest, reproducible HTML source locations."""
from hashlib import sha256
from difflib import SequenceMatcher
from pathlib import Path
import re
import textwrap
from urllib.parse import quote

from lxml import html

from app.models.orm import Document
from app.core.config import get_settings
from app.services.bo.hypotheses import normalise


def normalized(text):
    return normalise(text)


def html_index(data):
    root = html.fromstring(data, parser=html.HTMLParser(no_network=True))
    pages = [[]]
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        ancestors = [node, *node.iterancestors()]
        if any('display:none' in a.get('style', '').replace(' ', '').lower()
               or a.tag.lower().split(':')[-1] in {'script', 'style', 'hidden'} for a in ancestors):
            continue
        style = node.get('style', '').replace(' ', '').lower()
        if node.tag.lower() == 'hr' and 'page-break-after:always' in style:
            pages.append([])
        # SEC filers use both paragraph tags and leaf divs (including inline XBRL).
        # Never index wrapper divs as duplicate, whole-page paragraphs.
        tag = node.tag.lower()
        is_block = tag in {'p', 'li'} or (tag == 'div' and not node.xpath('.//div | .//p | .//table | .//li'))
        if is_block and normalized(node.text_content()):
            pages[-1].append((normalized(node.text_content()), style))
    result = []
    for page_index, blocks in enumerate(pages, 1):
        label = None
        if len(pages) > 1 and blocks and re.fullmatch(r'(?:F-)?\d+', blocks[-1][0], re.I) and 'text-align:center' in blocks[-1][1]:
            label = blocks.pop()[0]
        for paragraph, (text, _) in enumerate(blocks, 1):
            lines = textwrap.wrap(text, width=100, break_long_words=False, break_on_hyphens=False)
            result.append(dict(id=f'page-{page_index}-paragraph-{paragraph}', page=label,
                               paragraph=paragraph, text=text, lines=lines))
    return result


def verified_source_bytes(session, document, case_id):
    """Only admitted, checksum-matching local HTML is used; never retrieve a URL."""
    row = session.get(Document, document.get('document_id'))
    if not row or row.case_id != case_id or not row.storage_path:
        return None
    path = Path(row.storage_path).resolve()
    if not path.is_relative_to((Path(get_settings().data_dir) / 'raw').resolve()):
        return None
    try:
        if path.stat().st_size > 25_000_000:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if sha256(data).hexdigest() != document.get('sha256') or data.startswith(b'%PDF-'):
        return None
    if path.suffix.lower() not in {'.htm', '.html', '.xhtml'}:
        return None
    return data


def source_index(session, document, case_id):
    data = verified_source_bytes(session, document, case_id)
    return html_index(data) if data else None


def locate(quotation, index):
    needle = normalized(quotation)
    matches = [p for p in index or [] if needle and needle in p['text']]
    if len(matches) != 1 or matches[0]['text'].count(needle) != 1:
        return None
    paragraph = matches[0]
    start = paragraph['text'].index(needle)
    stop = start + len(needle)
    offset, lines = 0, []
    for number, line in enumerate(paragraph['lines'], 1):
        if offset < stop and offset + len(line) > start:
            lines.append(number)
        offset += len(line) + 1
    return {**paragraph, 'line': str(lines[0]) if len(lines) == 1 else f'{lines[0]}–{lines[-1]}'} if lines else None


def covering_passages(text, passages):
    """Require continuous verbatim coverage, allowing only whitespace at chunk seams."""
    target = normalized(text)
    if not target:
        return []
    spans = []
    for passage in passages:
        source = normalized(passage.get('text', ''))
        if target in source:
            return [passage['evidence_id']]
        match = SequenceMatcher(None, target, source, autojunk=False).find_longest_match()
        if len(source) >= 16 and match.size >= min(40, len(source)):
            spans.append((match.a, match.a + match.size, passage['evidence_id']))
    end, ids = 0, []
    for start, stop, eid in sorted(spans):
        if start > end and target[end:start].strip():
            return []
        if stop > end:
            end = stop
            ids.append(eid)
    return ids if not target[end:].strip() else []


def quotation_cards(item, passages, documents, indexes, base):
    candidates = []
    def collect(value):
        if isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, dict):
            text = value.get('quote') or value.get('raw_quote') or value.get('normalized_quote')
            if isinstance(text, str) and text.strip():
                candidates.append((text, value.get('evidence_id'), value.get('document_id'), value.get('supporting_evidence_ids')))
            for key, child in value.items():
                if key in {'model_stated', 'recovery', 'raw_response'}:
                    continue
                if isinstance(child, (list, dict)):
                    collect(child)
    # Selected finding quotes take precedence; component quotes supplement Agent 6.
    if item.get('hypotheses'):
        collect([h.get('evidence_quotes', []) for h in item['hypotheses']])
    else:
        collect(item.get('content'))
    cards, seen = [], set()
    allowed = set((item.get('claim') or {}).get('evidence_ids', []))
    for text, eid, doc_id, supporting_ids in candidates:
        if supporting_ids:
            support = [passages[e] for e in supporting_ids if e in passages and (not allowed or e in allowed)]
            if (len(support) != len(supporting_ids) or not doc_id
                    or any(p['document_id'] != doc_id for p in support)
                    or not covering_passages(text, support)):
                continue
            passage = support[0]
        elif eid:
            passage = passages.get(eid)
            if not passage or (allowed and eid not in allowed):
                continue
            if normalized(text) not in normalized(passage.get('text')):
                continue
            doc_id = passage['document_id']
        else:
            passage = next((p for p in passages.values() if p['document_id'] == doc_id
                            and normalized(text) in normalized(p.get('text'))), None)
            if not passage:
                continue
        document = documents.get(doc_id, {})
        key = (doc_id, normalized(text))
        if key in seen:
            continue
        seen.add(key)
        position = locate(text, indexes.get(doc_id))
        token = sha256(normalized(text).encode()).hexdigest()
        original = (base.rsplit('/source', 1)[0] + '/original/' + quote(doc_id, safe='') + '/' + token
                    if indexes.get(doc_id) else None)
        cards.append(dict(quote=text, filename=document.get('filename') or 'Recorded Source',
            document_id=doc_id, quote_token=token,
            section=passage.get('section') or 'Not Available', page=position['page'] if position else None,
            paragraph=position['paragraph'] if position else None, line=position['line'] if position else None,
            viewer=(base + '/' + quote(doc_id, safe='') + '#' + position['id']) if position else None,
            original=original))
    return cards
