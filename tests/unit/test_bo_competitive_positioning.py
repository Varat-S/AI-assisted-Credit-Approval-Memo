"""Source, number, ledger, interaction and cache boundaries, without inference."""
import copy

import pytest

from app.core.hashing import content_hash
from app.prompts.competitive_positioning import OUTPUT_VERSION, WRITER_SCHEMA, prompt_catalogue
from app.schemas.agentic import ParameterResult, AcceptanceState
from app.schemas.bo import HypothesisRecord, CalculationTrace, Admissibility
from app.services.agents.cache import CacheIdentity
from app.services.agents.registry import default_registry, AgentRegistryError
from app.services.bo.competitive_positioning import (
    M1_IDS, build_input, validate_output, validate_review, evidence_ids,
)
from app.services.bo.hypotheses import HYPOTHESIS_VALIDATOR_VERSION
from app.services.bo.indicators import IndicatorSet
from app.services.bo.roster_v3 import V3_SPEC_BY_AGENT
from app.services.bo.runner import BusinessOverviewRunner
from app.services.bo.synthesis import iter_claims
from tests import competitive_positioning_helpers as cp


@pytest.fixture
def editorial():
    records = []
    for agent, response in cp.script().items():
        if agent not in M1_IDS:
            continue
        for raw in response['hypotheses']:
            spec = V3_SPEC_BY_AGENT[agent]
            hid = raw['hypothesis_id']
            record = HypothesisRecord(
                hypothesis_id=hid, analysis_run_id='run', agent_id=agent,
                agent_run_id='producer:' + agent, section=spec.code, claim=raw['claim'],
                claim_type=raw['claim_type'], direction=raw['direction'],
                disposition=raw['disposition'],
                admissibility='qualified_narrative' if raw['claim_type'] == 'inference' else 'established',
                materiality=raw['materiality'], supporting_evidence_ids=['ev:' + hid],
                evidence_quotes=[{'evidence_id': 'ev:' + hid, 'quote': q['quote']} for q in raw.get('evidence_quotes', [])],
                component_hypothesis_ids=raw.get('component_hypothesis_ids', []),
                interaction_kind=raw.get('interaction_kind'),
                transmission_mechanism=raw.get('transmission_mechanism'),
                validator_id=spec.validator_id, validator_version=HYPOTHESIS_VALIDATOR_VERSION)
            records.append(record)
    output = cp.writer_output()
    by_id = {h.hypothesis_id: h for h in records}
    for _, c in iter_claims(output):
        c['evidence_ids'] = sorted({eid for hid in c['hypothesis_ids'] for eid in evidence_ids(by_id[hid])})
    return records, output


def validate(records, output, *, indicators=None, parameters=()):
    return validate_output(output, hypotheses=records, indicators=indicators or IndicatorSet(), parameters=parameters)


def packet(records, *, parameters=(), indicators=None, **kwargs):
    return build_input(
        identity={'case_id': 'case', 'analysis_run_id': 'run', 'evidence_snapshot_version': 1,
                  'evidence_snapshot_hash': '0' * 64, 'as_of_date': None, 'evidence_cutoff_timestamp': None},
        hypotheses=records, parameters=parameters, indicators=indicators or IndicatorSet(),
        validated_runs={a: 'producer:' + a for a in M1_IDS}, coverage={a: {'status': 'validated'} for a in M1_IDS},
        **kwargs)


def test_valid_editorial_contract_and_independent_review(editorial):
    records, output = editorial
    assert validate(records, output) == []
    assert validate_review(cp.review(output), output, [h.hypothesis_id for h in records]) == []


def test_builder_excludes_modules_2_4_and_retains_canonical_agent6(editorial):
    records, _ = editorial
    outside = records[0].model_copy(update={'agent_id': 'm2_industry', 'section': 'M2', 'hypothesis_id': 'M2-H1'})
    source = packet([*records, outside])
    assert len(source['hypotheses']) == len(records)
    assert all(h['agent_id'] in M1_IDS for h in source['hypotheses'])
    assert not {'module_conclusions', 'cross_module_instruction', 'score', 'evidence'} & source.keys()
    a6 = next(h for h in source['hypotheses'] if h['section'] == 'M1A6')
    original = next(h for h in records if h.section == 'M1A6')
    assert a6 == original.model_dump(mode='json')


def test_cross_run_record_is_rejected(editorial):
    records, _ = editorial
    records[0] = records[0].model_copy(update={'analysis_run_id': 'foreign-run'})
    with pytest.raises(ValueError, match='another run'):
        packet(records)


def test_identity_cannot_smuggle_extra_module_inputs(editorial):
    records, _ = editorial
    identity = packet(records)['identity']
    identity['module_conclusions'] = {'M4': {'unrelated_number': 99}}
    with pytest.raises(ValueError, match='exactly'):
        build_input(identity=identity, hypotheses=records, parameters=[], indicators=IndicatorSet(),
                    validated_runs={}, coverage={})


def test_duplicate_metadata_must_agree_with_selection_decisions(editorial):
    records, output = editorial
    output['merged_duplicates'] = [{'kept_hypothesis_id': 'M1S1-H001',
                                    'merged_hypothesis_ids': ['M1S1-H002'],
                                    'reason': 'Consolidated overlapping contract terms.'}]
    assert validate(records, output) == []
    output['merged_duplicates'][0]['merged_hypothesis_ids'] = ['M1S2-H001']
    assert any('editorial_duplicates' in issue for issue in validate(records, output))


@pytest.mark.parametrize('change', [
    {'acceptance_state': 'superseded'}, {'disposition': 'unverified'},
    {'disposition': 'rejected'}, {'admissibility': 'audit_only'},
    {'validator_id': 'wrong-validator'}, {'validator_version': None},
    {'agent_run_id': 'old-producer'},
])
def test_only_current_validated_findings_are_eligible(editorial, change):
    records, _ = editorial
    # Use the independent extra contract finding, not an Agent 6 component.
    index = next(i for i, h in enumerate(records) if h.hypothesis_id == 'M1S1-H002')
    raw = records[index].model_dump(mode='json'); raw.update(change)
    records[index] = HypothesisRecord.model_validate(raw)
    source = packet(records)
    assert 'M1S1-H002' not in {h['hypothesis_id'] for h in source['hypotheses']}
    assert 'M1S1-H002' in {h['hypothesis_id'] for h in source['audit_only_hypotheses']}


def test_invalid_agent6_component_cannot_cross_input_boundary(editorial):
    records, _ = editorial
    a6 = next(h for h in records if h.section == 'M1A6')
    a6.component_hypothesis_ids.append('M2-H001')
    with pytest.raises(ValueError, match='components'):
        packet(records)


def test_parameter_input_requires_current_m1_ownership(editorial):
    records, _ = editorial
    p = ParameterResult(
        parameter_result_id='p:1', analysis_run_id='run', parameter_id='pricing_power_assessment',
        topic='business', value='bounded', value_type='category', method='llm', status='ok',
        agent_id='m1_revenue_quality', agent_run_id='producer:m1_revenue_quality',
        prompt_id='fixture', model_id='fixture', input_hash='fixture')
    wrong_owner = p.model_copy(update={'parameter_result_id': 'p:2', 'parameter_id': 'capex_strategy_assessment'})
    outside = p.model_copy(update={'parameter_result_id': 'p:3', 'agent_id': 'm4_strategy_capital'})
    superseded = p.model_copy(update={'parameter_result_id': 'p:4', 'acceptance_state': AcceptanceState.SUPERSEDED})
    assert [x['parameter_result_id'] for x in packet(records, parameters=[p, wrong_owner, outside, superseded])['parameters']] == ['p:1']
    with pytest.raises(ValueError, match='another run'):
        packet(records, parameters=[p.model_copy(update={'analysis_run_id': 'foreign'})])


@pytest.mark.parametrize('defect', ['duplicate', 'missing', 'unknown', 'blank_reason', 'omitted_claim', 'false_selected', 'false_merged'])
def test_ledger_is_complete_and_consistent(editorial, defect):
    records, output = editorial
    decisions = output['selection_decisions']
    if defect == 'duplicate':
        decisions.append(copy.deepcopy(decisions[0]))
    elif defect == 'missing':
        decisions.pop()
    elif defect == 'unknown':
        decisions[0]['hypothesis_id'] = 'M2-H1'
    elif defect == 'blank_reason':
        decisions[0]['reason'] = '   '
    elif defect == 'omitted_claim':
        decisions[2]['claim_ids'] = ['cp-lead']
    elif defect == 'false_selected':
        decisions[0]['claim_ids'] = ['unknown']
    else:
        decisions[3].update(decision='merged')  # is merged in the lead: make it standalone instead
        output['overall_assessment']['hypothesis_ids'] = ['M1S3-H001']
    assert any('editorial_ledger' in issue for issue in validate(records, output))


@pytest.mark.parametrize('defect', ['no_agent6', 'unknown_agent6', 'missing_component', 'missing_mechanism', 'wrong_basis', 'duplicate_basis'])
def test_causal_interactions_require_exact_agent6_basis(editorial, defect):
    records, output = editorial
    risk = output['material_risks'][0]
    if defect == 'no_agent6':
        risk['hypothesis_ids'].remove('M1A6-H001'); output['interaction_basis'] = []
    elif defect == 'unknown_agent6':
        output['interaction_basis'][0]['agent6_hypothesis_ids'] = ['invented']
    elif defect == 'missing_component':
        risk['hypothesis_ids'].remove('M1S5-H001')
    elif defect == 'missing_mechanism':
        next(h for h in records if h.section == 'M1A6').transmission_mechanism = None
    elif defect == 'wrong_basis':
        output['interaction_basis'][0]['claim_id'] = 'unknown'
    else:
        output['interaction_basis'] *= 2
    assert any('editorial_interaction' in x or 'editorial_causal' in x for x in validate(records, output))


def test_mixed_sources_still_require_qualification_and_attribution(editorial):
    records, output = editorial
    next(h for h in records if h.hypothesis_id == 'M1S1-H002').admissibility = Admissibility.QUALIFIED_NARRATIVE
    assert any('editorial_qualification' in x for x in validate(records, output))
    next(h for h in records if h.hypothesis_id == 'M1S1-H002').admissibility = Admissibility.ATTRIBUTED
    assert any('editorial_attribution' in x for x in validate(records, output))


def metric(pid, value):
    result = ParameterResult(parameter_result_id=pid, analysis_run_id='run', parameter_id=pid,
                             topic='business', value=value, value_type='ratio', method='deterministic', status='ok',
                             formula_id='fixture', formula_version='1')
    trace = CalculationTrace(parameter_result_id=pid, parameter_id=pid, label=pid, value=value,
                             units='ratio', period='2025', formula_id='fixture', definition_version='1',
                             calculation_state='ok')
    return result, trace


def test_only_referenced_traces_and_bound_figures_are_available(editorial):
    records, output = editorial
    primary = next(h for h in records if h.hypothesis_id == 'M1S1-H001')
    primary.parameter_result_ids = ['m1:ratio']
    primary.quoted_values = [{'parameter_result_id': 'm1:ratio', 'value': 0.05, 'unit': 'ratio', 'period': '2025'}]
    pairs = [metric('m1:ratio', 0.05), metric('m4:unrelated', 99)]
    indicators = IndicatorSet(results=[r for r, _ in pairs], traces=[t for _, t in pairs])
    source = packet(records, indicators=indicators)
    assert [t['parameter_result_id'] for t in source['indicators']] == ['m1:ratio']
    c = output['key_drivers'][0]
    c['text'] += ' The disclosed ratio is 0.05.'
    c['parameter_result_ids'] = ['m1:ratio']
    c['quoted_values'] = copy.deepcopy(primary.quoted_values)
    assert validate(records, output, indicators=indicators) == []
    c['quoted_values'][0]['value'] = 99
    c['text'] = 'The ratio is 99%.'
    issues = validate(records, output, indicators=indicators)
    assert any('editorial_quoted_value' in x for x in issues)
    assert any('editorial_number' in x for x in issues)


@pytest.mark.parametrize('field,value', [('period', '2024'), ('unit', 'USD'), ('denominator', 'cash')])
def test_numerical_scope_cannot_be_relabelled(editorial, field, value):
    records, output = editorial
    h = next(h for h in records if h.hypothesis_id == 'M1S1-H001')
    h.quoted_values = [{'parameter_result_id': 'metric', 'value': 0.05, 'unit': 'ratio', 'period': '2025', 'denominator': 'revenue'}]
    output['key_drivers'][0]['quoted_values'] = [dict(h.quoted_values[0], **{field: value})]
    assert any('editorial_quoted_value' in x for x in validate(records, output))


def test_foreign_evidence_and_unrelated_parameters_fail(editorial):
    records, output = editorial
    output['key_drivers'][0]['evidence_ids'].append('foreign-source')
    output['key_drivers'][0]['parameter_result_ids'].append('foreign-param')
    assert any('editorial_evidence' in x for x in validate(records, output))
    assert any('editorial_parameter' in x for x in validate(records, output))


@pytest.mark.parametrize('field', ['reviewed_hypothesis_ids', 'reviewed_omitted_hypothesis_ids', 'reviewed_interaction_claim_ids'])
def test_review_attestation_must_cover_current_selection(editorial, field):
    records, output = editorial
    answer = cp.review(output); answer['editorial_review'][field] = []
    assert validate_review(answer, output, [h.hypothesis_id for h in records])


def test_opt_in_is_v3_only_and_changes_writer_cache_not_specialists(db_session):
    legacy = default_registry('v3')
    new = default_registry('v3', business_orchestrator_contract=OUTPUT_VERSION)
    for agent in M1_IDS:
        assert legacy.get(agent).definition_hash() == new.get(agent).definition_hash()
    for agent in ('business_orchestrator', 'business_challenge'):
        assert legacy.get(agent).definition_hash() != new.get(agent).definition_hash()
        assert legacy.get(agent).prompt != new.get(agent).prompt
    assert legacy.registry_hash() != new.registry_hash()
    assert set(new.get('business_orchestrator').dependencies) == M1_IDS
    for roster in ('v1', 'v2'):
        with pytest.raises(AgentRegistryError):
            default_registry(roster, business_orchestrator_contract=OUTPUT_VERSION)
    with pytest.raises(ValueError):
        BusinessOverviewRunner(db_session, bo_roster='v2', business_orchestrator_contract=OUTPUT_VERSION)
    with pytest.raises(ValueError):
        BusinessOverviewRunner(db_session, bo_roster='v3', business_orchestrator_contract='future')
    identity = dict(case_id='case', evidence_snapshot_version=1,
                    agent_id='business_orchestrator', model_id='fixture', model_config={},
                    router_version='router', packet_hash='packet', response_schema_hash='legacy', prompt_hash='legacy')
    old = CacheIdentity(**identity, agent_definition_hash=legacy.get('business_orchestrator').definition_hash())
    current = CacheIdentity(**{**identity, 'response_schema_hash': content_hash(WRITER_SCHEMA),
                              'prompt_hash': content_hash(prompt_catalogue()[0])},
                            agent_definition_hash=new.get('business_orchestrator').definition_hash())
    assert old.key() != current.key()
