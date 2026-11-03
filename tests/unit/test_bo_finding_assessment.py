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
    ('inference','Inference'), ('assumption','Assumption'), ('management_claim','Fact')])
def test_three_display_labels_and_explicit_field_level_limitations(kind, label):
    s = source(kind); before = deepcopy(s)
    result = assessment(s, pointers())
    assert result['finding']['label'] == label
    assert result['policy_version'] == POLICY
    assert result['implication']['label'] == 'Inference'
    assert result['implication']['support'] == 'Qualified'
    assert 'field-level' in result['implication']['support_reason']
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
    assert result['finding']['label'] == result['implication']['label'] == 'Inference'
    assert result['finding']['support'] == result['implication']['support'] == 'Unsupported'
    assert 'does not state' in result['finding']['reason']
    assert result['gaps'] == [description]
    assert result['original_claim_type'] == 'fact' and s == before


def test_hypothetical_events_not_presented_as_occurred_facts():
    s = source()
    s['review_flags'] = [{'rule_id':'generic_risk_disclosure_only'}]
    result = assessment(s, pointers())
    assert result['finding']['label'] == 'Fact'
    assert result['finding']['support'] == 'Qualified'
    assert 'not evidence that the event occurred' in result['finding']['support_reason']


def test_missing_interpretation_and_gaps_are_not_invented():
    s = source()
    s.update(credit_mechanism=None, interpretation={})
    result = assessment(s, pointers(False))
    assert result['implication'] is None
    assert result['specialist_interpretation'] == result['gaps'] == []


def test_unsupported_does_not_make_an_explicit_assumption_an_inference():
    s = source('assumption')
    s['review_flags'] = [{'rule_id':'quote_does_not_cover_claim'}]
    result = assessment(s, pointers())
    assert result['finding']['label'] == 'Assumption'
    assert result['finding']['support'] == 'Unsupported'
    assert result['implication']['label'] == 'Inference'


def test_field_types_are_independent_and_directly_quoted_implication_can_be_fact():
    s = source('assumption')
    quotation = {'quote': 'The saved credit mechanism.'}
    result = assessment(s, pointers(), verified_quotes=[quotation])
    assert result['finding']['label'] == 'Assumption'
    assert result['implication']['label'] == 'Fact'
    assert result['implication']['support'] == 'Supported'
    assert assessment(s, pointers())['implication']['label'] == 'Inference'


def test_qualified_does_not_reclassify_disclosed_or_calculated_facts():
    for kind in ('fact','calculated_fact','management_claim'):
        s = source(kind)
        s.update(disposition='qualified', admissibility='attributed')
        result = assessment(s, pointers())
        assert result['finding']['label'] == 'Fact'
        assert result['finding']['support'] == 'Qualified'


def test_assumption_implication_requires_explicit_adoption_not_future_language():
    p = pointers(); p[1]['parts'][0]['text'] = 'Assumption: No acquisitions during the forecast period.'
    result = assessment(source(), p)
    assert result['finding']['label'] == 'Fact'
    assert result['implication']['label'] == 'Assumption'
    p[1]['parts'][0]['text'] = 'Costs may increase if wages rise.'
    assert assessment(source(), p)['implication']['label'] == 'Inference'


def test_verified_literal_finding_retains_fact_despite_unresolved_heuristic():
    s = source(); s['claim'] = 'The reported revenue is 100.'
    s['review_flags'] = [{'rule_id':'quote_does_not_cover_claim'}]
    result = assessment(s, pointers(), verified_quotes=[{'quote': s['claim']}])
    assert result['finding']['label'] == 'Fact'
    assert result['finding']['support'] == 'Qualified'
