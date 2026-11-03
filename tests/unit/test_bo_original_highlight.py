from lxml import html

from app.services.bo.original_highlight import highlighted_original
from app.services.bo.evidence_presentation import quotation_cards, html_index


def test_quote_across_inline_spans_and_typography_is_highlighted_without_rewriting():
    data = '<html><head><meta charset="utf-8"></head><body><p>Before. The physician’s <b>ownership</b> interest matters. After.</p></body></html>'.encode()
    content, csp = highlighted_original(data, "The physician's ownership interest matters.")
    root = html.fromstring(content)
    assert root.xpath('//p')[0].text_content() == 'Before. The physician’s ownership interest matters. After.'
    assert ''.join(root.xpath('//mark/text()')) == 'The physician’s ownership interest matters.'
    assert root.xpath('//*[@id="bo-original-quote-target"]')
    assert 'scrollIntoView' in content and "default-src 'none'" in csp


def test_multiple_occurrences_do_not_highlight_intervening_words():
    result = highlighted_original(b'<p>Exact quote. Unrelated sentence. Exact quote.</p>', 'Exact quote.')
    root = html.fromstring(result[0])
    assert root.xpath('//mark/text()') == ['Exact quote.', 'Exact quote.']
    assert root.xpath('//p')[0].text_content() == 'Exact quote. Unrelated sentence. Exact quote.'


def test_active_source_content_is_removed_and_only_nonce_script_remains():
    data = b'''<html><head><meta http-equiv="refresh" content="0;url=https://evil.invalid"></head>
    <body onload="evil()"><script>evil()</script><iframe src="https://evil.invalid"></iframe>
    <p onclick="evil()">Exact quotation.</p><a href="javascript:evil()">Bad link</a></body></html>'''
    content, csp = highlighted_original(data, 'Exact quotation.')
    root = html.fromstring(content)
    assert not root.xpath('//iframe|//meta[@http-equiv]|//*[@onclick]|//*[@onload]')
    assert not root.xpath('//a[@href]')
    assert len(root.xpath('//script')) == 1
    assert root.xpath('//script')[0].get('nonce') in csp
    assert 'evil()' not in content
    assert highlighted_original(data, 'Unwritten quotation') is None


def test_validator_equivalent_quotes_fix_empty_panel_without_recovering_other_words():
    text = 'State certificate of need (“CON”) laws restrict a facility’s expansion.'
    item = {'claim': {'evidence_ids': ['ev']}, 'hypotheses': [{'evidence_quotes': [
        {'evidence_id': 'ev', 'quote': 'State certificate of need ("CON") laws restrict a facility\'s expansion.'},
        {'evidence_id': 'ev', 'quote': 'Other unsupported claims.'}]}]}
    cards = quotation_cards(item, {'ev': {'document_id': 'doc', 'text': text}},
        {'doc': {'filename': 'report.htm'}}, {'doc': html_index(('<html><head><meta charset="utf-8"></head><body><p>'+text+'</p></body></html>').encode())}, '/cases/c/bo/runs/r/source')
    assert len(cards) == 1
    assert '/original/doc/' in cards[0]['original']
