"""Explicitly fictional, scripted editorial acceptance example. No model calls."""
import copy

from app.prompts.competitive_positioning import OUTPUT_VERSION, POLICY_VERSION
from app.services.bo.offline import ScriptedBoBackend
from app.services.bo.runner import BusinessOverviewRunner
from tests import bo_helpers as h
from tests.integration.test_bo_v3_complete import _script as legacy_script


def claim(cid, category, section, text, refs, *, uncertainty=None, claim_type='fact'):
    result = h.claim(cid, category, section, text, refs, claim_type=claim_type,
                     parameter_result_ids=[], uncertainty=uncertainty, quoted_values=[])
    # This synthetic fixture shares one payer passage across the contract
    # findings. Agent 6 already carries both component passages. Avoid repeating
    # the same source when the offline resolver expands its anchors.
    evidence_refs = (['M1A6-H001'] if 'M1A6-H001' in refs else
                     list(dict.fromkeys('M1S1-H001' if hid.startswith(('M1S1-', 'M1S3-')) else hid
                                        for hid in refs)))
    result['evidence_ids'] = [{'$hypothesis_evidence': hid} for hid in evidence_refs]
    return result


def writer_output():
    return {
        'schema_version': OUTPUT_VERSION, 'policy_version': POLICY_VERSION,
        'overall_assessment': claim(
            'cp-lead', 'assessment', 'executive',
            'Managed-care contracts set negotiated rates and can be terminated on notice.',
            ['M1S1-H001', 'M1S3-H001'],
            uncertainty='Contract terms do not guarantee patient volumes; renewal outcomes are not established.'),
        'strengths': [], 'weaknesses': [],
        'key_drivers': [claim(
            'cp-contracts', 'driver', 'M1S1',
            'Multi-year managed-care agreements set negotiated rates.',
            ['M1S1-H001', 'M1S1-H002'])],
        'material_risks': [claim(
            'cp-workforce-interaction', 'risk', 'M1A6',
            'Competition for scarce clinical staff can raise costs and constrain service capacity.',
            ['M1A6-H001', 'M1S4-H001', 'M1S5-H001'], claim_type='inference',
            uncertainty='Qualified interaction: competitor staffing data are unavailable.')],
        'open_questions': ['Competitor staffing data are unavailable.'],
        'unresolved_contradictions': [], 'follow_up': ['Review competitor staffing data when admitted.'],
        'merged_duplicates': [],
        'selection_decisions': [
            {'hypothesis_id': 'M1S1-H001', 'decision': 'selected',
             'claim_ids': ['cp-lead', 'cp-contracts'],
             'reason': 'Negotiated revenue terms anchor the contract discussion.'},
            {'hypothesis_id': 'M1S1-H002', 'decision': 'merged', 'claim_ids': ['cp-contracts'],
             'reason': 'Multi-year duration and negotiated rates fit one contract-terms paragraph.'},
            {'hypothesis_id': 'M1S2-H001', 'decision': 'omitted', 'claim_ids': [],
             'reason': 'Stable historical admissions add little to the selected contract and workforce exposures; no volume guarantee is inferred.'},
            {'hypothesis_id': 'M1S3-H001', 'decision': 'selected', 'claim_ids': ['cp-lead'],
             'reason': 'Termination rights qualify the credit reading of negotiated rates.'},
            {'hypothesis_id': 'M1S4-H001', 'decision': 'omitted', 'claim_ids': [],
             'reason': 'Retained as component lineage for the selected Agent 6 interaction; a separate paragraph would repeat that operating exposure.'},
            {'hypothesis_id': 'M1S5-H001', 'decision': 'omitted', 'claim_ids': [],
             'reason': 'Retained as component lineage for the selected Agent 6 interaction; no standalone competitive advantage is inferred.'},
            {'hypothesis_id': 'M1A6-H001', 'decision': 'selected', 'claim_ids': ['cp-workforce-interaction'],
             'reason': 'The validated interaction explains how staff competition may transmit into costs and service capacity.'},
        ],
        'interaction_basis': [{'claim_id': 'cp-workforce-interaction', 'agent6_hypothesis_ids': ['M1A6-H001']}],
    }


def review(output=None, challenges=()):
    output = output or writer_output()
    return {
        'challenges': list(challenges), 'overall_outcome': 'accepted',
        'summary': 'Scripted independent review: source-backed wording, preserved qualifications and economically justified omissions; no new causal mechanism identified.',
        'editorial_review': {
            'policy_version': POLICY_VERSION,
            'reviewed_hypothesis_ids': [d['hypothesis_id'] for d in output['selection_decisions']],
            'reviewed_omitted_hypothesis_ids': [d['hypothesis_id'] for d in output['selection_decisions'] if d['decision'] == 'omitted'],
            'reviewed_interaction_claim_ids': [b['claim_id'] for b in output['interaction_basis']],
            'economic_support_reviewed': True, 'material_omissions_reviewed': True,
        },
    }


def script():
    answers = legacy_script()
    answers['m1_revenue_quality']['hypotheses'].append(h.hyp(
        'M1S1-H002', 'Managed-care agreements generally have multi-year terms.',
        'fact', 'neutral', 'supported', support=['managed care contracts'],
        quotes=[('managed care contracts', 'Our managed care contracts are generally multi-year agreements')]))
    answers['m1_customer_stickiness']['hypotheses'][0]['materiality'] = 'low'
    answers['orchestrate'] = writer_output()
    answers['challenge'] = review()
    return copy.deepcopy(answers)


def run(session, path, *, answers=None, metrics=None, **kwargs):
    backend = ScriptedBoBackend(answers or script())
    result = BusinessOverviewRunner(
        session, backend=backend, bo_roster='v3', sector=None,
        business_orchestrator_contract=OUTPUT_VERSION,
        data_root=path / 'data', output_root=path / 'out', **kwargs,
    ).run_prepared(h.CASE, h.evidence_snapshot(), h.metrics() if metrics is None else metrics, write_outputs=True)
    return result, backend


def sample_packet(session, result, backend):
    """Export actual isolated run records for the reviewable Milestone 2 sample."""
    from app.core.hashing import content_hash
    from app.models.orm import AgentRunRow, TopicConclusionRow
    from app.services.bo.synthesis import iter_claims
    from app.services.bo.workbench import bo_artifact

    audit = bo_artifact(session, result.analysis_run_id, 'audit')
    selection = audit['orchestrator']['editorial_selection']
    conclusion = session.get(TopicConclusionRow, selection['conclusion_id'])
    writer = session.query(AgentRunRow).filter_by(
        analysis_run_id=result.analysis_run_id, agent_id='business_orchestrator').one()
    challenger = session.query(AgentRunRow).filter_by(
        analysis_run_id=result.analysis_run_id, agent_id='business_challenge').one()
    claims = [c for _, c in iter_claims(conclusion.payload)]
    omitted_id = 'M1S2-H001'
    record = next(h for h in audit['hypotheses']['records'] if h['hypothesis_id'] == omitted_id)
    narrative = '\n\n'.join(c['text'] + ('\nQualification: ' + c['uncertainty'] if c.get('uncertainty') else '')
                             for c in claims)
    return {
        'schema_version': 'bo-competitive-positioning-offline-example-1.0.0',
        'example_only': True,
        'warning': 'Fictional Northfield Health Systems; scripted writer AND independent challenger responses. This proves offline workflow behavior, not live model analytical quality. M3 inputs are intentionally absent, so the full BO still requires human review.',
        'base_commit': '34d61e7b3e547228d6766ec4a7e916395821a906',
        'execution_mode': result.execution_mode,
        'identity': {'case_id': result.case_id, 'analysis_run_id': result.analysis_run_id,
                     'evidence_snapshot_version': result.snapshot_version,
                     'conclusion_id': conclusion.id, 'orchestrator_run_id': writer.run_id},
        'competitive_positioning_text': narrative,
        'original_model_response': writer.raw_response,
        'validated_writer_output': writer.parsed_response,
        'validated_conclusion': conclusion.payload,
        'editorial_selection': selection,
        'independent_challenger': {'agent_run_id': challenger.run_id, 'model_id': challenger.model_id,
                                   'rounds': audit['challenger']['rounds']},
        'source_findings_from_frozen_audit': [h for h in audit['hypotheses']['records'] if h['section'].startswith('M1')],
        'omission_proof': {
            'deliberately_omitted_hypothesis_id': omitted_id, 'source_claim': record['claim'],
            'in_frozen_audit': True, 'audit_record_id': record['record_id'],
            'in_handoff_accepted_finding_ids': omitted_id in result.handoff['accepted_finding_ids'],
            'in_narrative_hypothesis_ids': any(omitted_id in c['hypothesis_ids'] for c in claims),
            'source_claim_in_narrative_text': record['claim'] in narrative,
            'automatic_coverage_claim_ids': [c['claim_id'] for c in claims if c['claim_id'].startswith('COV-')],
            'in_challenger_reviewed_omissions': omitted_id in audit['challenger']['rounds'][0]['editorial_review']['reviewed_omitted_hypothesis_ids'],
        },
        'handoff_preservation': {
            **{key: copy.deepcopy(result.handoff[key]) for key in (
                'schema_version', 'accepted_finding_ids', 'operational_vulnerabilities',
                'canonical_references', 'content_hash', 'conclusion_status', 'human_review_status')},
        },
        'frozen_audit_sha256': content_hash(audit),
        'scripted_calls': {'writer': backend.calls('orchestrate'), 'challenger': backend.calls('challenge')},
    }
