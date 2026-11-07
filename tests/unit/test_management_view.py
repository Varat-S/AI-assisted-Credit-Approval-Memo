from copy import deepcopy
import pytest

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
    assert view['key_strengths'] == [finding]
    assert view['key_concerns'] == []
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


@pytest.mark.parametrize('direction,status,group,label', [
    ('positive', 'accepted', 'supporting_factors', 'Positive'),
    ('positive', 'qualified', 'supporting_factors', 'Positive'),
    ('negative', 'accepted', 'credit_concerns', 'Negative'),
    ('negative', 'qualified', 'credit_concerns', 'Negative'),
    ('mixed', 'qualified', 'mixed_uncertain', 'Mixed'),
    ('neutral', 'accepted', 'mixed_uncertain', 'Neutral'),
    (None, 'qualified', 'mixed_uncertain', 'Unassessed'),
])
def test_direction_and_review_are_independent(direction, status, group, label):
    observation = {'observation_id': 'o1', 'category': 'continuity', 'direction': direction,
                   'review_outcome': status, 'text': 'Original finding.', 'review_reason': 'Limited scope.',
                   'uncertainties': ['Performance unverified.'], 'citation_ids': ['c1']}
    source = {'citations': [{'citation_id': 'c1'}], 'observations': [observation]}
    before = deepcopy(source)
    view = management_view(source)
    populated = [g for g in view['finding_groups'] if g['findings']]
    assert len(populated) == 1 and populated[0]['id'] == group
    finding = populated[0]['findings'][0]
    assert (finding['direction'], finding['review_status'], finding['direction_label']) == (direction, status, label)
    assert finding['text'] == observation['text']
    assert any(q['text'] == 'Performance unverified.' for q in view['qualifications'])
    if direction is None:
        assert view['uncategorized'] == [finding]
    if direction == 'positive':
        assert view['categories'][3]['status'] == 'supporting_factor'
    assert source == before


def test_overall_prefers_effective_review_and_retains_original_wording():
    source = {'overall_assessment': {'policy': 'Recorded wording.', 'outcome': 'positive'},
              'model_assessment': {'explanation': 'Original model wording.'},
              'validation': {'validator_7': {'overall': {'text': 'Superseded reviewed wording.'}},
                'explicit_review_corrections': {'corrected_overall': {'text': 'Effective reviewed wording.',
                                                                     'limitations': ['Material qualification.']}}}}
    before = deepcopy(source)
    view = management_view(source)
    assert view['overall_assessment']['text'] == 'Effective reviewed wording.'
    assert view['overall_assessment']['original_text'] == 'Original model wording.'
    assert view['overall_assessment']['recorded_text'] == 'Recorded wording.'
    assert view['overall_assessment']['status'] == 'qualified'
    assert source == before


def test_no_replacement_does_not_rewrite_qualified_recorded_assessment():
    source = {'overall_assessment': {'policy': 'Original positive wording.', 'outcome': 'positive', 'information_gaps': True},
              'limitations': ['Financial outcomes are unverified.']}
    view = management_view(source)
    assert view['overall_assessment']['text'] == 'Original positive wording.'
    assert view['overall_assessment']['wording_label'] == 'Recorded assessment'
    assert view['overall_assessment']['status'] == 'qualified'
    assert view['qualifications'][0]['text'] == 'Financial outcomes are unverified.'


def test_qualification_deduplication_keeps_all_origins_without_semantic_merging():
    observations = [{'observation_id': str(i), 'category': 'continuity', 'direction': 'positive',
                     'review_outcome': 'accepted', 'text': f'Claim {i}', 'citation_ids': ['c1'],
                     'uncertainties': [text]} for i, text in enumerate(['Outcome evidence missing.', 'Outcome  evidence\nmissing.', 'Turnover evidence missing.'])]
    source = {'citations': [{'citation_id': 'c1'}], 'observations': observations,
              'model_assessment': {'uncertainties': ['Outcome evidence missing.']}}
    before = deepcopy(source)
    view = management_view(source)
    assert len(view['qualifications']) == 2
    assert view['qualifications'][0]['observation_ids'] == ['0', '1']
    assert view['qualifications'][0]['origins'] == ['overall', 'observation_uncertainty']
    assert view['qualifications'][1]['text'] == 'Turnover evidence missing.'
    assert source == before


def test_html_source_metadata_and_duplicate_locations_without_invented_pages():
    citation = {'citation_id': 'c1', 'source_id': 'a'*64, 'source_sha256': 'hash',
                'document_id': 'd1', 'physical_page': 1, 'passage_offset': 120}
    source = {'company': 'Recorded Company', 'source': {'path': 'sec-inline-xbrl:d1'},
              'citations': [citation, {**citation, 'citation_id': 'c2', 'span_start': 20}],
              'observations': [{'observation_id': 'o1', 'category': 'continuity', 'direction': 'positive',
                                'review_outcome': 'qualified', 'text': 'Recorded claim.', 'citation_ids': ['c1', 'c2']}]}
    documents = {'d1': {'document_id': 'd1', 'sha256': 'hash', 'parser': 'inline_xbrl',
                         'filename': 'filing.htm', 'form': '10-K', 'report_date': '2025-12-31'}}
    view = management_view(source, documents=documents)
    assert len(view['sources']) == 1
    assert view['sources'][0]['locator'] == 'Passage offset 120'
    assert view['sources'][0]['citation_ids'] == ['c1', 'c2']
    assert view['sources'][0]['label'] == 'Recorded Company · Form 10-K · 2025-12-31'
    assert len(view['key_strengths'][0]['references']) == 1
    foreign = {'d1': {**documents['d1'], 'sha256': 'foreign', 'filename': 'FOREIGN.htm', 'form': 'FOREIGN'}}
    fallback = management_view(source, documents=foreign)
    assert fallback['sources'][0]['label'] == 'Recorded management source'
    assert 'FOREIGN' not in str(fallback)


def test_processing_notices_do_not_hide_unknown_material_limitations():
    source = {'overall_assessment': {'policy': 'Recorded wording.', 'outcome': 'positive'},
              'limitations': ['Company and fiscal period were confirmed from the admitted SEC filing metadata (form 10-K, CIK 1), not from cover-page text. HTML passages have no pages; citations give page 1 and the passage offset.',
                             'Unknown material governance limitation.', 'Offline fixture; model quality not tested.'],
              'validation': {'claim_results': [{'outcome': 'unsupported'}]}}
    view = management_view(source)
    assert any(q['text'] == 'Unknown material governance limitation.' for q in view['qualifications'])
    assert any('withheld 1 evidence claim' in q['text'] for q in view['qualifications'])
    assert view['methodology_notices'] == ['Offline fixture; model quality not tested.']
    assert view['technical_notes'] == [source['limitations'][0]]


def test_material_reason_with_internal_ids_is_not_discarded_as_technical():
    reason = 'Supporting fact f_01 was rejected; a material governance concern remains unresolved.'
    source = {'citations': [{'citation_id': 'c1'}], 'observations': [
        {'observation_id': 'o1', 'category': 'continuity', 'direction': 'negative',
         'review_outcome': 'qualified', 'text': 'Reviewed concern.', 'review_reason': reason, 'citation_ids': ['c1']}],
        'validation': {'judgment_results': [{'judgment_id': 'o1', 'removed_fact_ids': ['f_01']}]}}
    view = management_view(source)
    assert any(q['text'] == reason for q in view['qualifications'])
    assert view['key_concerns'][0]['review_status'] == 'qualified'


def test_explicit_information_gap_is_separate_from_direction_groups():
    view = management_view({'citations': [{'citation_id': 'c1'}], 'observations': [
        {'observation_id': 'gap', 'category': 'information_gap', 'direction': 'unavailable',
         'review_outcome': 'qualified', 'text': 'Outcome evidence is missing.', 'citation_ids': ['c1']}]})
    assert [g['id'] for g in view['finding_groups'] if g['findings']] == ['information_gaps']
    assert not view['key_strengths'] and not view['key_concerns']


def test_pdf_inventory_recovers_all_eligible_uncategorized_findings_without_padding():
    observations = [{'observation_id': str(i), 'category': 'unknown', 'direction': 'positive',
                     'review_outcome': 'qualified', 'text': f'Reviewed finding {i}.',
                     'uncertainties': ['Outcome unproven.'], 'citation_ids': ['c1']} for i in range(5)]
    source = {'citations': [{'citation_id': 'c1'}], 'observations': observations,
              'validation': {'judgment_results': [{'judgment_id': 'withheld', 'outcome': 'unsupported',
                                                   'original_text': 'Rejected conclusion.', 'reason': 'Unsupported.'}]}}
    before = deepcopy(source)
    view = management_view(source)
    assert len(view['key_strengths']) == 3  # Existing compact web projection is unchanged.
    assert len(view['pdf']['finding_groups'][0]['findings']) == 5
    assert view['pdf']['finding_count'] == 5
    assert view['pdf']['finding_limit_notice'] is None
    assert view['pdf']['eligible_excluded_by_categorization'] == 0
    assert [i['eligible'] for i in view['pdf']['inventory']] == [True]*5 + [False]
    assert 'Rejected conclusion.' not in str(view['pdf']['finding_groups'])
    assert source == before and management_view(source) == view


def test_pdf_exec_context_selects_one_admitted_role_and_recorded_transitions_only():
    source = {'citations': [{'citation_id': 'c1'}, {'citation_id': 'c2'}], 'roster_date': '2026-02-01',
              'profiles': [{'name': 'Recorded CFO', 'position': 'Chief Financial Officer', 'appointment_date': '2024-05-01',
                            'recency': 'recent', 'succession': 'internal', 'citation_ids': ['c1'],
                            'prior_internal_roles': [{'position': 'Finance role', 'start_date': '2023-01',
                                                      'end_date': '2024-04', 'citation_ids': ['c2']},
                                                     {'position': 'Older role', 'citation_ids': ['c2']}]},
                           {'name': 'Recorded legal officer', 'position': 'Legal officer', 'citation_ids': ['c1'],
                            'prior_internal_roles': [{'position': 'Unadmitted role', 'citation_ids': ['missing']}]}],
              'model_assessment': {'missing_information': ['Recent performance evidence.']},
              'limitations': ['Recent performance evidence.']}
    before = deepcopy(source)
    pdf = management_view(source)['pdf']
    assert pdf['executives'][0]['experience']['position'] == 'Finance role'
    assert 'Older role' not in str(pdf['executives']) and 'Unadmitted role' not in str(pdf['executives'])
    assert pdf['executives'][0]['transition'] == 'Recent appointment'
    assert pdf['executives'][0]['appointment_date'] == '2024-05-01'
    assert pdf['executives'][1]['experience'] is None
    assert pdf['follow_up'] == ['Recent performance evidence.']
    assert pdf['qualifications'] == []  # Printed once as a page-2 follow-up.
    assert pdf['monitoring_priorities'] == []
    assert '0 distinct reviewed findings' in pdf['finding_limit_notice']
    assert source == before


def test_three_part_findings_use_final_referenced_claims_and_do_not_borrow_rejected_facts():
    source = {'citations': [{'citation_id': 'c1'}, {'citation_id': 'c2'}],
        'observations': [{'observation_id': 'j1', 'category': 'continuity', 'direction': 'positive',
            'review_outcome': 'accepted', 'text': 'Internal succession supports continuity.',
            'citation_ids': ['c1'], 'supporting_fact_ids': ['old'],
            'uncertainties': ['Execution remains unproven.', 'Execution remains unproven.']}],
        'validation': {'judgment_results': [{'judgment_id': 'j1', 'supporting_claim_ids': ['good', 'bad', 'foreign', 'role']}],
            'claim_results': [
                {'claim_id': 'good', 'kind': 'fact', 'outcome': 'qualified', 'statement': 'Supported subset.', 'citation_ids': ['c1'], 'original_statement': 'Unsupported full statement.'},
                {'claim_id': 'bad', 'kind': 'fact', 'outcome': 'unsupported', 'statement': 'Rejected fact.', 'citation_ids': ['c1']},
                {'claim_id': 'foreign', 'kind': 'fact', 'outcome': 'accepted', 'statement': 'Another finding.', 'citation_ids': ['c2']},
                {'claim_id': 'role', 'kind': 'prior_internal_role', 'outcome': 'accepted', 'statement': 'Repeated role detail.', 'citation_ids': ['c1']}]}}
    before = deepcopy(source)
    view = management_view(source)
    f = view['key_strengths'][0]
    assert [p['text'] for p in f['finding_parts']] == ['Supported subset.']
    assert f['finding_classification']['label'] == 'Fact'
    assert f['credit_implication'] == 'Internal succession supports continuity.'
    assert f['implication_classification']['label'] == 'Inference'
    assert f['display_limitations'] == ['Execution remains unproven.']
    assert view['pdf']['finding_groups'][0]['findings'][0]['credit_implication'] == f['credit_implication']
    assert source == before
