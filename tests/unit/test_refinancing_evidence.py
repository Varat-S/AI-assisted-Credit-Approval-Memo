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


def test_each_event_gets_its_own_action_not_another_transaction_of_same_amount():
    issued = 'We issued $1.500 billion of senior notes due 2035.'
    redeemed = 'We redeemed all $1.500 billion of senior notes due 2026.'
    texts = [issued, redeemed]
    citations = [{'passage': passage(str(i), t)} for i, t in enumerate(texts)]
    index = {'filing': [{'page': '23', 'text': t} for t in texts]}
    for category, expected in [('new_issuance', issued), ('early_redemption', redeemed)]:
        result = historical_quotes({'extraction_source': {'page_references': ['23']},
            'refinancing_log': [{'principal_amount_m': 1500, 'transaction_category': category}]}, citations, index)
        assert [q['quote'] for q in result] == [expected]


def test_div_based_ehc_events_each_get_actual_completed_transaction_quote():
    from app.services.bo.evidence_presentation import html_index
    from app.services.bo.original_highlight import highlighted_original
    text = ('In August and November 2024, we redeemed $150 million and $100 million, respectively, '
            'of the outstanding principal balance of our 2025 Notes using cash on hand. '
            'Pursuant to the terms of the 2025 Notes, these optional redemptions were made at a price of par. '
            'In September 2025, we redeemed the remaining $100 million of the outstanding principal balance '
            'of our 2025 Notes at maturity using cash on hand and capacity under our revolving credit facility.')
    source = ('<html><body><div>'+text+'</div><div style="text-align:center">F-31</div>'
              '<hr style="page-break-after:always"><div>Next page</div></body></html>').encode()
    index = {'filing': html_index(source)}
    passages = {'ev': passage('ev', text)}
    for date, amount, category in [('August 2024',150,'early_redemption'),
                                   ('November 2024',100,'early_redemption'),
                                   ('September 2025',100,'repayment_at_maturity')]:
        row = dict(principal_amount_m=amount,transaction_category=category,
                   execution_date_fiscal_period=date,original_retired_maturity='September 15, 2025')
        quotes = historical_quotes({'extraction_source':{'page_references':['F-31']},
                                    'refinancing_log':[row]}, [{'passage':passages['ev']}],index)
        cards = quotation_cards({'content':quotes},passages,{'filing':{'filename':'ehc.htm'}},index,'/source')
        assert len(cards) == 1
        card = cards[0]
        assert card['page'] == 'F-31' and card['paragraph'] == 1
        assert card['viewer'].endswith('#page-1-paragraph-1')
        assert highlighted_original(source,card['quote']) is not None
        assert ('at maturity' in card['quote']) == (category == 'repayment_at_maturity')


def test_repayment_of_other_maturity_does_not_support_same_amount():
    text = 'We redeemed $100 million of notes due 2030.'
    row = dict(principal_amount_m=100,transaction_category='early_redemption',original_retired_maturity='2025')
    assert not historical_quotes({'extraction_source':{'page_references':['1']},'refinancing_log':[row]},
        [{'passage':passage('ev',text)}],{'filing':[{'page':'1','text':text}]})


def test_same_amount_from_a_different_execution_year_or_month_is_not_reused():
    texts = ['In August and November 2024, we redeemed $150 million and $100 million of our 2025 Notes.',
             'In August 2025, we redeemed $100 million of our 2025 Notes.',
             'In September 2025, we redeemed $100 million of our 2025 Notes.']
    row = dict(principal_amount_m=100,transaction_category='early_redemption',
               execution_date_fiscal_period='September 2025',original_retired_maturity='2025')
    citations = [{'passage':passage(str(i),text)} for i,text in enumerate(texts)]
    quotes = historical_quotes({'extraction_source':{'page_references':['99']},'refinancing_log':[row]},
        citations,{'filing':[{'page':'1','text':text} for text in texts]})
    # Inaccurate model page references cannot discard an exact source match.
    assert [q['quote'] for q in quotes] == [texts[-1]]
