from app.services.bo.evidence_presentation import covering_passages, quotation_cards
from app.services.bo.refinancing_evidence import historical_quotes


def passage(eid, text, doc='filing'):
    return {'evidence_id': eid, 'document_id': doc, 'text': text}


def test_completed_repayment_crossing_chunks_is_kept_but_options_are_not():
    actual = 'We repaid at maturity all $2.600 billion of senior notes and $1.400 billion of senior notes.'
    option = 'CHS may redeem $4.000 billion of notes at a redemption price equal to the principal redeemed.'
    right = 'CHS is entitled, at its option, to redeem notes previously issued for $4.000 billion.'
    entries = [{'principal_amount_m': 4000, 'transaction_category': 'repayment_at_maturity'}]
    chunks = [passage('a', actual[:58]), passage('b', actual[55:])]
    citations = [{'passage': p} for p in chunks + [passage('c', option), passage('d', right)]]
    indexes = {'filing': [{'page': '23', 'text': t} for t in [actual, option, right]]}
    quotes = historical_quotes({'extraction_source': {'page_references': ['23']},
                                'refinancing_log': entries}, citations, indexes)
    assert [q['quote'] for q in quotes] == [actual]
    assert set(quotes[0]['supporting_evidence_ids']) == {'a', 'b'}
    # The normal quotation renderer independently checks all supporting chunks.
    cards = quotation_cards({'content': quotes}, {p['evidence_id']: p for p in chunks},
                            {'filing': {'filename': '10k.htm'}}, {}, '/source')
    assert [c['quote'] for c in cards] == [actual]


def test_chunk_coverage_never_bridges_missing_text_or_other_documents():
    text = 'We redeemed $500 million of outstanding senior notes during the year and repaid the facility in full.'
    assert not covering_passages(text, [passage('a', text[:50]), passage('b', text[65:])])
    p = passage('a', text, 'other-company')
    assert not quotation_cards({'content': {'quote': text, 'document_id': 'filing',
                               'supporting_evidence_ids': ['a']}}, {'a': p}, {}, {}, '/source')


def test_unrelated_completed_transaction_and_future_option_are_excluded():
    texts = ['CHS completed an offering of $700 million of senior notes.',
             'CHS completed an offering of $900 million of senior notes.',
             'CHS may redeem $700 million of the notes issued in 2025.']
    citations = [{'passage': passage(str(i), t)} for i, t in enumerate(texts)]
    quotes = historical_quotes({'extraction_source': {'page_references': ['67']},
        'refinancing_log': [{'principal_amount_m': 700, 'transaction_category': 'new_issuance'}]},
        citations, {'filing': [{'page': '67', 'text': t} for t in texts]})
    assert [q['quote'] for q in quotes] == [texts[0]]


def test_execution_year_filter_does_not_confuse_note_maturity_with_event_date():
    actual = 'Approximately $584 million of notes due 2028 were redeemed in May 2025 via a tender offer.'
    later = 'On February 2, 2026, the Company redeemed $584 million of the notes.'
    citations = [{'passage': passage(str(i), t)} for i, t in enumerate([actual, later])]
    quotes = historical_quotes({'extraction_source': {'page_references': ['67']},
        'refinancing_log': [{'principal_amount_m': 584, 'transaction_category': 'tender_exchange',
                             'execution_date_fiscal_period': 'May 2025 (FY2025)'}]},
        citations, {'filing': [{'page': '67', 'text': t} for t in [actual, later]]})
    assert [q['quote'] for q in quotes] == [actual]
