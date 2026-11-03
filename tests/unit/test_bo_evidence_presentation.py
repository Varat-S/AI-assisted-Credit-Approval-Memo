from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

from app.services.bo.evidence_presentation import html_index, locate, quotation_cards, source_index


SOURCE = b'''<html><body><p>A heading</p><p>Actual quoted words from the report.</p>
<p style="text-align:center">57</p><hr style="page-break-after:always">
<p>Another page.</p><p style="text-align:center">58</p></body></html>'''


def test_real_footer_pages_and_explicit_viewer_paragraph_lines():
    index = html_index(SOURCE)
    position = locate('Actual quoted words from the report.', index)
    assert (position['page'], position['paragraph'], position['line']) == ('57', 2, '1')
    assert position['id'] == 'page-1-paragraph-2'
    assert locate('Words never written', index) is None


def test_missing_page_labels_and_ambiguous_quotes_not_invented():
    index = html_index(b'<html><p>Same wording.</p><p>Same wording.</p></html>')
    assert index[0]['page'] is None
    assert locate('Same wording.', index) is None
    assert locate('Same wording.', html_index(b'<p>Same wording. Same wording.</p>')) is None


def test_line_numbers_refer_to_deterministic_viewer_wrapping():
    text = ' '.join(['prefix'] * 20) + ' Exact quotation spanning the following lines in the viewer.'
    position = locate('Exact quotation spanning the following lines in the viewer.', html_index(('<p>'+text+'</p>').encode()))
    assert position['line'] == '2–3'
    assert all(len(line) <= 100 for line in position['lines'])


def test_only_source_bound_canonical_quotes_are_shown_and_inputs_unchanged():
    q = 'Actual quoted words from the report.'
    item = {'claim': {'evidence_ids': ['ev']}, 'hypotheses': [
        {'evidence_quotes': [{'evidence_id': 'ev', 'quote': q}, {'evidence_id': 'ev', 'quote': q},
                            {'evidence_id': 'ev', 'quote': 'Invented words'},
                            {'evidence_id': 'foreign', 'quote': q}],
         'model_stated': {'evidence_quotes': [{'evidence_id': 'ev', 'quote': 'Actual quoted'}]}}]}
    passages = {'ev': {'document_id': 'doc', 'text': q, 'section': 'Item 7'}}
    docs = {'doc': {'filename': 'report.htm', 'source_url': 'https://www.sec.gov/report.htm'}}
    before = deepcopy((item, passages, docs))
    cards = quotation_cards(item, passages, docs, {'doc': html_index(SOURCE)}, '/source')
    assert len(cards) == 1
    assert cards[0]['quote'] == q and cards[0]['page'] == '57'
    assert cards[0]['viewer'] == '/source/doc#page-1-paragraph-2'
    assert '/original/doc/' in cards[0]['original']
    assert cards[0]['original'].endswith(cards[0]['quote_token'])
    assert (item, passages, docs) == before


def test_local_source_requires_case_path_and_hash(monkeypatch, tmp_path):
    from app.services.bo import evidence_presentation as ep
    raw = tmp_path/'raw'; raw.mkdir()
    path = raw/'report.htm'; path.write_bytes(SOURCE)
    monkeypatch.setattr(ep, 'get_settings', lambda: SimpleNamespace(data_dir=tmp_path))
    row = SimpleNamespace(case_id='case', storage_path=str(path))
    session = SimpleNamespace(get=lambda *args: row)
    doc = {'document_id': 'doc', 'sha256': sha256(SOURCE).hexdigest()}
    assert source_index(session, doc, 'case')
    assert source_index(session, doc, 'other-case') is None
    path.write_bytes(SOURCE+b'tampered')
    assert source_index(session, doc, 'case') is None
    path = tmp_path/'outside.htm'; path.write_bytes(SOURCE); row.storage_path = str(path)
    assert source_index(session, doc, 'case') is None
