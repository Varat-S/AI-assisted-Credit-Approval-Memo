"""Offline full-run acceptance of the selective editorial opt-in."""
import copy
import json

import pytest

from app.core.hashing import content_hash
from app.models.orm import AgentRunRow, AgenticAnalysisRun, TopicConclusionRow
from app.prompts.competitive_positioning import OUTPUT_VERSION, INPUT_VERSION, POLICY_VERSION
from app.schemas.bo import AcceptedBusinessOverview
from app.services.bo.competitive_positioning import M1_IDS
from app.services.bo.reporting import _m1_sections_with_further_findings, render_memo_html
from app.services.bo.synthesis import iter_claims
from app.services.bo.workbench import bo_artifact
from tests import competitive_positioning_helpers as cp


def test_select_merge_omit_interaction_and_frozen_audit(db_session, tmp_path):
    result, backend = cp.run(db_session, tmp_path)
    assert backend.calls('orchestrate') == backend.calls('challenge') == 1, result.record['agents']['business_orchestrator']
    selection = result.audit['orchestrator']['editorial_selection']
    assert selection['schema_version'] == OUTPUT_VERSION
    assert selection['policy_version'] == POLICY_VERSION
    assert result.audit['orchestrator']['history'][0]['status'] == 'accepted'
    conclusion = db_session.get(TopicConclusionRow, selection['conclusion_id'])
    assert selection['orchestrator_run_id'] == conclusion.orchestrator_run_id
    assert result.handoff['business_topic_conclusion_id'] == conclusion.id
    assert result.handoff['canonical_references']['editorial_selection_hash'] == content_hash(selection)
    assert result.handoff['human_review_status'] == 'pending'
    assert {c['claim_id'] for c in result.handoff['compound_business_risks']} == {'cp-workforce-interaction'}
    assert {c['claim_id'] for c in result.memo['cross_module_risk_interactions']} == {'cp-workforce-interaction'}
    # M3 sources deliberately absent; successful M1 review cannot upgrade the whole BO.
    assert result.conclusion_status == 'human_review_required'
    round_ = result.audit['challenger']['rounds'][0]
    assert round_['status'] == 'validated' and round_['outcome'] == 'accepted'
    assert round_['conclusion_id'] == conclusion.id
    assert 'M1S2-H001' in round_['editorial_review']['reviewed_omitted_hypothesis_ids']
    assert round_['editorial_selection'] == selection
    claims = [c for _, c in iter_claims(conclusion.payload)]
    assert not any('M1S2-H001' in c['hypothesis_ids'] for c in claims)
    assert not any(c['claim_id'].startswith('COV-') for c in claims)
    assert any(c['section'] == 'M1A6' for c in claims)
    records = result.audit['hypotheses']['records']
    omitted = next(h for h in records if h['hypothesis_id'] == 'M1S2-H001')
    assert omitted['claim'] == 'Admissions were stable during the year.'
    m1_sections = [s for s in result.memo['sections'] if s['code'].startswith('M1')]
    assert all(s['further_findings'] == [] for s in m1_sections)
    html = render_memo_html(result.memo)
    assert omitted['claim'] not in html
    # Rendering cannot put the old fallback back after fields are absent.
    no_further = copy.deepcopy(result.memo)
    for s in no_further['sections']:
        s.pop('further_findings', None)
    assert _m1_sections_with_further_findings(no_further) == no_further
    assert omitted['claim'] not in render_memo_html(no_further)
    frozen = bo_artifact(db_session, result.analysis_run_id, 'audit')
    assert frozen['orchestrator']['editorial_selection'] == selection
    rows = db_session.query(AgentRunRow).filter_by(analysis_run_id=result.analysis_run_id).all()
    writer = next(r for r in rows if r.agent_id == 'business_orchestrator')
    assert writer.raw_response and json.loads(writer.raw_response)['selection_decisions']
    assert writer.parsed_response['selection_decisions'] == selection['selection_decisions']
    run_row = db_session.get(AgenticAnalysisRun, result.analysis_run_id)
    assert run_row.model_configuration['business_orchestrator_contract'] == OUTPUT_VERSION
    writer_packet = next(p for method, p in backend.requests if method == 'orchestrate')
    assert writer_packet['schema_version'] == INPUT_VERSION
    assert {h['agent_id'] for h in writer_packet['hypotheses']} <= M1_IDS
    assert 'module_conclusions' not in writer_packet and 'cross_module_instruction' not in writer_packet
    assert writer_packet['indicators'] == []  # metrics existed but no M1 finding used them
    a6 = next(h for h in writer_packet['hypotheses'] if h['section'] == 'M1A6')
    assert a6['transmission_mechanism'] and a6['component_hypothesis_ids']
    challenger_packet = next(p for method, p in backend.requests if method == 'challenge')
    assert {h['hypothesis_id'] for h in challenger_packet['omitted_hypotheses']} == {
        d['hypothesis_id'] for d in selection['selection_decisions'] if d['decision'] == 'omitted'}
    assert {h['agent_id'] for h in challenger_packet['hypotheses_not_used']} <= M1_IDS


def test_downstream_sources_and_rms_vulnerabilities_survive_omission(db_session, tmp_path):
    from app.services.rms.inputs import load_bo

    answers = cp.script()
    # Omit an adverse contract finding; it must remain available to RMS.
    out = answers['orchestrate']
    out['overall_assessment'] = cp.claim('cp-lead', 'assessment', 'executive',
                                        'Managed-care agreements set negotiated rates.', ['M1S1-H001'])
    # Avoid repetitive overall/body prose, without changing analytical basis.
    out['key_drivers'][0]['text'] = 'The contracts generally run for multiple years.'
    for d in out['selection_decisions']:
        if d['hypothesis_id'] == 'M1S3-H001':
            d.update(decision='omitted', claim_ids=[], reason='Deliberate offline omission to test downstream retention.')
    answers['challenge'] = cp.review(out)
    result, _ = cp.run(db_session, tmp_path, answers=answers)
    assert result.handoff['business_topic_conclusion_id']
    handoff = AcceptedBusinessOverview.model_validate(result.handoff)
    assert {'M1S2-H001', 'M1S3-H001', 'M2-H001', 'M4-H001'} <= set(handoff.accepted_finding_ids)
    assert set(handoff.module_conclusions) == {'M1', 'M2', 'M3', 'M4'}
    source_risk = next(r for r in handoff.operational_vulnerabilities if r['claim_id'] == 'source:M1S3-H001')
    assert source_risk['text'] == 'Either party may terminate a managed-care agreement on notice.'
    assert source_risk['source_finding_only'] is True
    assert any(cid == 'source:M1S3-H001' for cid, _, _ in load_bo(result.handoff).vulnerabilities)
    assert all(c['claim_id'] != source_risk['claim_id'] for c in result.audit['orchestrator']['claims'])


@pytest.mark.parametrize('defect', ['unknown_hypothesis', 'invented_number', 'missing_interaction', 'missing_ledger'])
def test_invalid_output_fails_closed_without_coverage_repair(db_session, tmp_path, defect):
    answers = cp.script()
    out = answers['orchestrate']
    if defect == 'unknown_hypothesis':
        out['key_drivers'][0]['hypothesis_ids'].append('M2-H001')
    elif defect == 'invented_number':
        out['key_drivers'][0]['text'] += ' Revenue rises 99%.'
    elif defect == 'missing_interaction':
        out['material_risks'][0]['hypothesis_ids'].remove('M1A6-H001')
        out['interaction_basis'] = []
    else:
        out['selection_decisions'].pop(1)
    result, backend = cp.run(db_session, tmp_path, answers=answers)
    assert result.handoff['business_topic_conclusion_id'] is None
    assert backend.calls('orchestrate') == 2  # only the existing one repair attempt
    assert backend.calls('challenge') == 0
    assert all(h['status'] == 'rejected' for h in result.audit['orchestrator']['history'])
    assert not any(c['claim_id'].startswith('COV-') for c in result.audit['orchestrator']['claims'])


def test_incomplete_challenger_review_is_not_accepted(db_session, tmp_path):
    answers = cp.script()
    answers['challenge']['editorial_review']['reviewed_omitted_hypothesis_ids'] = []
    result, _ = cp.run(db_session, tmp_path, answers=answers)
    assert result.audit['challenger']['rounds'][0]['status'] == 'rejected'
    assert result.audit['challenger']['rounds'][0]['outcome'] == 'human_review_required'
    assert result.conclusion_status == 'human_review_required'


def test_omission_challenge_runs_only_bounded_writer_remediation(db_session, tmp_path):
    answers = cp.script()
    defect = {'challenge_id': 'omit-review', 'target': None, 'issue_type': 'other',
              'severity': 'material', 'reason': 'M1S2-H001 omission needs an explicit source-bound limitation.',
              'affected_agent_ids': ['business_orchestrator'], 'requires_reanalysis': True,
              'requested_rerun_scope': ['business_orchestrator']}
    first = cp.review(challenges=[defect])
    # Remains unresolved after the permitted pass: no automatic insertion.
    answers['challenge'] = [first, copy.deepcopy(first)]
    result, backend = cp.run(db_session, tmp_path, answers=answers)
    assert backend.calls('orchestrate') == backend.calls('challenge') == 2
    assert backend.calls('m1_customer_stickiness') == 1
    assert result.record['remediation']['round'] == 1
    assert result.conclusion_status == 'human_review_required'
    assert result.handoff['unresolved_challenges']
    assert not any(h['hypothesis_id'] == 'M1S2-H001'
                   for c in result.audit['orchestrator']['claims'] for h in c['hypotheses'])
    assert 'M1S2-H001' in result.handoff['unresolved_challenges'][0]['reason']


def test_semantic_defect_is_independently_challenged(db_session, tmp_path):
    answers = cp.script()
    answers['orchestrate']['key_drivers'][0]['text'] = 'Patient loyalty is assured by the multi-year rate agreements.'
    defect = {'challenge_id': 'unsupported-implication', 'target': 'cp-contracts',
              'issue_type': 'unsupported_causal_claim', 'severity': 'material',
              'reason': 'Negotiated rate terms do not establish patient loyalty or guaranteed volumes.',
              'requires_reanalysis': False, 'affected_agent_ids': ['business_orchestrator']}
    answers['challenge'] = cp.review(challenges=[defect])
    result, backend = cp.run(db_session, tmp_path, answers=answers)
    assert backend.calls('challenge') == 1
    assert result.conclusion_status == 'human_review_required'
    assert result.handoff['unresolved_challenges'][0]['issue_type'] == 'unsupported_causal_claim'


def test_no_eligible_findings_never_fabricates_a_lead(db_session, tmp_path):
    answers = cp.script()
    for agent in M1_IDS:
        answers[agent] = {'parameters': [], 'hypotheses': []}
    result, backend = cp.run(db_session, tmp_path, answers=answers)
    assert backend.calls('orchestrate') == backend.calls('challenge') == 0
    assert result.handoff['business_topic_conclusion_id'] is None
    assert result.conclusion_status in {'unavailable', 'human_review_required'}


def test_failed_primary_still_blocks_agent6(db_session, tmp_path):
    answers = cp.script()
    answers['m1_pricing_power']['hypotheses'][0]['disposition'] = 'invented'
    result, backend = cp.run(db_session, tmp_path, answers=answers)
    assert backend.calls('m1_resilience_integration') == 0
    assert result.handoff['module_conclusions']['M1']['status'] == 'incomplete'
    assert result.conclusion_status in {'unavailable', 'human_review_required'}


@pytest.mark.parametrize('defect', ['selection_hash', 'conclusion_binding', 'workflow_binding'])
def test_editorial_archive_identity_is_bound_to_handoff(db_session, tmp_path, defect):
    from app.models.orm import AcceptedBusinessOverviewRow
    from app.services.bo.reporting import handoff_content_hash
    from app.services.bo.workbench import verify_report_identity
    from app.services.pipeline.artifacts import ArtifactIntegrityError

    result, _ = cp.run(db_session, tmp_path)
    row = db_session.get(AcceptedBusinessOverviewRow, result.handoff['handoff_id'])
    payload = copy.deepcopy(result.audit)
    handoff = copy.deepcopy(row.payload)
    if defect == 'selection_hash':
        handoff['canonical_references']['editorial_selection_hash'] = 'wrong-hash'
    elif defect == 'conclusion_binding':
        payload['orchestrator']['editorial_selection']['conclusion_id'] = 'another-conclusion'
        # A correct hash does not excuse an incorrect conclusion identity.
        handoff['canonical_references']['editorial_selection_hash'] = content_hash(payload['orchestrator']['editorial_selection'])
    else:
        handoff['canonical_references'].pop('business_orchestrator_contract')
    handoff['content_hash'] = handoff_content_hash(handoff)
    row.payload, row.content_hash = handoff, handoff['content_hash']
    with pytest.raises(ArtifactIntegrityError):
        verify_report_identity(db_session, row, 'audit', payload)


def test_exploratory_opt_in_cannot_be_approved(db_session, tmp_path):
    from app.services.bo.handoff import review_handoff, HandoffError

    result, _ = cp.run(db_session, tmp_path, enforce_validators=False)
    assert result.handoff['validators_enforced'] is False
    assert result.conclusion_status == 'human_review_required'
    with pytest.raises(HandoffError, match='Exploratory'):
        review_handoff(db_session, result.handoff['handoff_id'], reviewer='Offline reviewer',
                       reason='Contract acceptance test', acknowledge_unresolved=True)


def test_failed_module2_does_not_enter_or_replace_editorial_input(db_session, tmp_path):
    answers = cp.script()
    answers['m2_industry']['hypotheses'][0]['disposition'] = 'invented'
    result, backend = cp.run(db_session, tmp_path, answers=answers)
    assert backend.calls('orchestrate') == backend.calls('challenge') == 1
    assert result.audit['orchestrator']['editorial_selection']
    assert result.handoff['module_conclusions']['M2']['status'] == 'incomplete'
    assert result.conclusion_status == 'human_review_required'


def test_referenced_deterministic_figure_survives_full_pipeline(db_session, tmp_path):
    from app.services.metrics.engine import MetricResult, MetricState
    from tests import bo_helpers as h

    metrics = h.metrics()
    metrics['operating_margin'] = MetricResult(
        metric_name='operating_margin', metric_definition_id='operating_margin',
        metric_definition_version=1, formula_id='operating_margin', engine_version='fixture',
        inputs={'operating_income': 200.0, 'revenue': 1000.0}, input_fact_ids=['f_rev'],
        state=MetricState.OK, result=0.2, units='ratio', period=h.PERIOD, fiscal_year=2025)
    answers = cp.script()
    quote = {'parameter_result_id': {'$indicator': 'operating_margin'}, 'value': 0.2,
             'unit': 'ratio', 'period': h.PERIOD, 'denominator': 'revenue'}
    cost = answers['m1_operating_model']['hypotheses'][0]
    cost['claim'] += ' Operating margin was 0.2.'
    cost['quoted_values'] = [copy.deepcopy(quote)]
    risk = answers['orchestrate']['material_risks'][0]
    risk['text'] += ' The disclosed operating margin was 0.2.'
    risk['quoted_values'] = [copy.deepcopy(quote)]
    risk['parameter_result_ids'] = [{'$indicator': 'operating_margin'}]
    result, backend = cp.run(db_session, tmp_path, answers=answers, metrics=metrics)
    assert result.handoff['business_topic_conclusion_id'], result.audit['orchestrator']['history']
    source = next(p for method, p in backend.requests if method == 'orchestrate')
    assert [t['parameter_id'] for t in source['indicators']] == ['operating_margin']
    assert source['indicators'][0]['value'] == 0.2
    assert source['indicators'][0]['numerator']['name'] == 'operating_income'
    assert backend.calls('challenge') == 1
