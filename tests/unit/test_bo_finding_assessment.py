from copy import deepcopy

import pytest

from app.services.bo.finding_assessment import assessment, POLICY


def source(kind='fact', **changes):
    return dict(claim_type=kind, disposition='supported', admissibility='established',
                hypothesis_id='M1S5-H002', agent_id='m1_competitive_durability',
                credit_mechanism='The saved credit mechanism.',
                interpretation={'implication': 'The saved interpretation.'},
                review_flags=[], validation_notes=[], missing_information=[], **changes)


def pointers(parts=True):
    return [dict(parts=[]), dict(parts=[{'text': 'The saved credit mechanism.'}] if parts else [])]


@pytest.mark.parametrize('kind,label', [('fact','Fact'), ('calculated_fact','Fact'),
    ('inference','Inference'), ('assumption','Assumption'), ('management_claim','Assumption')])
def test_three_display_labels_and_explicit_field_level_limitations(kind, label):
    s = source(kind); before = deepcopy(s)
    result = assessment(s, pointers())
    assert result['finding']['label'] == label
    assert result['policy_version'] == POLICY
    assert result['implication']['label'] == ('Assumption' if label == 'Assumption' else 'Inference')
    assert 'field-level' in result['implication']['reason']
    assert result['original_claim_type'] == kind
    assert result['specialist_interpretation'] == ['The saved credit mechanism.', 'The saved interpretation.']
    assert s == before


def test_quote_coverage_flag_overrides_stale_fact_badge_without_changing_record():
    s = source()
    description = 'The verified quotation does not establish the claim.'
    s.update(disposition='qualified', admissibility='qualified_narrative',
             review_flags=[{'rule_id':'quote_does_not_cover_claim','description':description}],
             validation_notes=['quote_does_not_cover_claim: ' + description])
    before = deepcopy(s)
    result = assessment(s, pointers(), 'Qualified source finding.')
    assert result['finding']['label'] == result['implication']['label'] == 'Assumption'
    assert 'does not establish' in result['finding']['reason']
    assert result['gaps'] == [description]
    assert result['original_claim_type'] == 'fact' and s == before


def test_hypothetical_events_not_presented_as_occurred_facts():
    s = source()
    s['review_flags'] = [{'rule_id':'generic_risk_disclosure_only'}]
    result = assessment(s, pointers())
    assert result['finding']['label'] == 'Assumption'
    assert 'not evidence that the event occurred' in result['finding']['reason']


def test_missing_interpretation_and_gaps_are_not_invented():
    s = source()
    s.update(credit_mechanism=None, interpretation={})
    result = assessment(s, pointers(False))
    assert result['implication'] is None
    assert result['specialist_interpretation'] == result['gaps'] == []
