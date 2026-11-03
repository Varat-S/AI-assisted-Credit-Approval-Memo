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
