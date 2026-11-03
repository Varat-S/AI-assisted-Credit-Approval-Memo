from copy import deepcopy

from app.services.bo.management_view import management_view


def test_conservative_projection_is_deterministic_and_source_preserving():
    source = {'citations': [{'citation_id': 'cite:1', 'source_id': 'pdf:p1', 'physical_page': 1, 'quote': 'source'}],
              'overall_assessment': {'policy': 'Recorded qualified assessment.', 'outcome': 'mixed', 'information_gaps': True},
              'coverage': {'missing': ['CFO']}, 'completion_status': 'partial', 'profiles': [{'name': 'Executive'}],
              'observations': [
                  {'observation_id': 'a', 'category': 'continuity', 'text': 'Internal succession recorded.', 'direction': 'positive', 'review_outcome': 'accepted', 'citation_ids': ['cite:1']},
                  {'observation_id': 'b', 'category': 'continuity', 'text': 'Internal succession recorded.', 'direction': 'positive', 'review_outcome': 'accepted', 'citation_ids': ['cite:1']},
                  {'observation_id': 'c', 'category': 'transition', 'text': 'Transition is untested.', 'direction': 'negative', 'review_outcome': 'qualified', 'review_reason': 'Outcomes unavailable.', 'uncertainties': ['Performance not established.'], 'citation_ids': ['cite:1']},
                  {'observation_id': 'd', 'category': 'integration', 'text': 'Rejected positive.', 'direction': 'positive', 'review_outcome': 'unsupported', 'citation_ids': ['cite:1']},
                  {'observation_id': 'e', 'category': 'other', 'text': 'Ambiguous.', 'direction': 'positive', 'review_outcome': 'accepted', 'citation_ids': ['cite:1']},
                  {'observation_id': 'f', 'category': 'continuity', 'text': 'Missing source.', 'direction': 'positive', 'review_outcome': 'accepted', 'citation_ids': ['missing']},
                  {'observation_id': 'g', 'category': 'information_gap', 'text': 'Governance evidence unavailable.', 'direction': 'unavailable', 'review_outcome': 'qualified', 'review_reason': 'Scope limited.', 'citation_ids': ['cite:1']}]}
    before = deepcopy(source)
    view = management_view(source)
    assert source == before
    assert view == management_view(source)
    leadership = next(c for c in view['categories'] if c['id'] == 'leadership_stability')
    assert [f['text'] for f in leadership['findings']] == ['Internal succession recorded.', 'Transition is untested.']
    assert leadership['findings'][0]['observation_ids'] == ['a', 'b']
    assert leadership['findings'][1]['limitations'] == ['Outcomes unavailable.', 'Performance not established.']
    assert all(c['status'] == 'insufficient_evidence' for c in view['categories'] if c['id'] != 'leadership_stability')
    assert [f['text'] for f in view['uncategorized']] == ['Ambiguous.']
    assert view['information_gaps'][0]['text'] == 'Governance evidence unavailable.'
    assert 'Rejected positive.' not in str(view['categories'])
    assert 'Missing source.' not in str(view['categories'])
    assert view['key_strengths'][0]['citation_ids'] == ['cite:1']
    assert len(view['categories']) == 5
    assert [c['id'] for c in view['assessment_gaps']] == [
        'financial_stewardship', 'operational_execution', 'governance_integrity', 'relevant_expertise']


def test_unclassified_reviewed_concern_is_not_lost_from_memo_selection():
    source = {'citations': [{'citation_id': 'c1'}], 'observations': [
        {'observation_id': 'uncategorized', 'category': 'unknown', 'text': 'Reviewed concern.',
         'direction': 'negative', 'review_outcome': 'qualified', 'review_reason': 'Limited scope.',
         'uncertainties': ['Outcomes unverified.'], 'citation_ids': ['c1']},
        {'observation_id': 'rejected', 'category': 'unknown', 'text': 'Rejected assertion.',
         'direction': 'positive', 'review_outcome': 'rejected', 'citation_ids': ['c1']}]}
    view = management_view(source)
    assert len(view['assessment_gaps']) == 5
    assert view['uncategorized'] == view['uncategorized_concerns'] == view['key_concerns']
    assert view['key_concerns'][0]['limitations'] == ['Limited scope.', 'Outcomes unverified.']
    assert view['key_concerns'][0]['observation_ids'] == ['uncategorized']
    assert 'Rejected assertion.' not in str(view)


def test_duplicate_wording_retains_distinct_citation_references_and_qualifications():
    first = {'observation_id': 'a', 'category': 'continuity', 'text': 'Reviewed wording.',
             'direction': 'positive', 'review_outcome': 'qualified', 'review_reason': 'Limited evidence.',
             'uncertainties': ['Outcome not proven.'], 'citation_ids': ['c1']}
    second = {**first, 'observation_id': 'b', 'citation_ids': ['c2']}
    source = {'citations': [{'citation_id': 'c1'}, {'citation_id': 'c2'}], 'observations': [first, second]}
    before = deepcopy(source)
    view = management_view(source)
    finding = view['categories'][3]['findings'][0]
    assert finding['citation_ids'] == ['c1', 'c2']
    assert finding['observation_ids'] == ['a', 'b']
    assert finding['limitations'] == ['Limited evidence.', 'Outcome not proven.']
    assert view['key_strengths'] == []
    assert view['key_concerns'] == [finding]
    assert source == before and management_view(source) == view


def test_missing_and_partial_management_cannot_become_positive():
    assert management_view(None) is None
    view = management_view({'completion_status': 'partial', 'overall_assessment': {'outcome': 'unavailable'}})
    assert len(view['categories']) == len(view['assessment_gaps']) == 5
    assert view['key_strengths'] == view['key_concerns'] == []
    assert view['overall_assessment']['status'] == 'unavailable'


def test_effective_review_qualifications_take_precedence_over_audit_history():
    source = {'overall_assessment': {'policy': 'Corrected recorded assessment.', 'outcome': 'neutral'},
              'validation': {'validator_7': {'overall': {'limitations': ['Superseded qualification.']}},
                             'explicit_review_corrections': {'corrected_overall': {'limitations': ['Effective qualification.']}}}}
    before = deepcopy(source)
    view = management_view(source)
    assert view['overall_assessment']['text'] == 'Corrected recorded assessment.'
    assert view['overall_assessment']['limitations'] == ['Effective qualification.']
    assert view['overall_assessment']['status'] == 'qualified'
    assert source == before


def test_print_selection_cap_keeps_remaining_qualified_observations_discoverable():
    source = {'citations': [{'citation_id': 'c1'}], 'observations': [
        {'observation_id': str(i), 'category': 'unclassified', 'text': f'Reviewed concern {i}.',
         'direction': 'negative', 'review_outcome': 'qualified', 'review_reason': 'Limited scope.',
         'citation_ids': ['c1']} for i in range(5)]}
    view = management_view(source)
    assert len(view['key_concerns']) == 3
    assert view['additional_concerns'] == 2
    assert len(view['uncategorized']) == len(view['reviewed_observations']) == 5
    assert all(f['limitations'] == ['Limited scope.'] for f in view['key_concerns'])
