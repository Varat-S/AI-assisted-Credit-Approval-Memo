"""Selection cannot rewrite prose, numbers, citations or source qualifications."""
from copy import deepcopy
import pytest

from app.prompts import source_selection as contract
from app.schemas.bo import Admissibility
from app.services.bo.source_selection import validate_plan, project
from app.services.bo.synthesis import iter_claims
from app.services.agents.registry import default_registry
from tests.unit.test_bo_competitive_positioning import editorial, packet


def plan(source):
    ids=[h['hypothesis_id'] for h in source['hypotheses']]
    return dict(schema_version=contract.OUTPUT_VERSION, policy_version=contract.POLICY_VERSION,
                selections=[dict(hypothesis_id=ids[0], placement='lead', reason='Material lead finding.')],
                omissions=[dict(hypothesis_id=hid, reason='Less material than selected lead.') for hid in ids[1:]])


def test_exact_source_copy_and_immutable_input(editorial):
    records,_=editorial
    records[0].claim='The company reports 44.5%: balance billing protections support access.'
    records[0].admissibility=Admissibility.ATTRIBUTED
    records[0].missing_information=['Future renewal outcomes are unknown.']
    source=packet(records); before=deepcopy(source)
    output=project(plan(source),source)
    claim=output['overall_assessment'];h=source['hypotheses'][0]
    assert claim['text']==h['claim']
    assert claim['parameter_result_ids']==h['parameter_result_ids']
    assert claim['quoted_values']==h['quoted_values']
    assert set(claim['evidence_ids'])==set(h['supporting_evidence_ids']) | {q['evidence_id'] for q in h['evidence_quotes']}
    assert 'Management-attributed' in claim['uncertainty']
    assert 'Future renewal outcomes are unknown.' in claim['uncertainty']
    assert source==before


@pytest.mark.parametrize('defect',['text','citation','number','unknown','duplicate','missing','no_lead','two_leads','reason'])
def test_reject_malformed_or_rewriting_selection(editorial,defect):
    records,_=editorial;source=packet(records);choice=plan(source)
    if defect in {'text','citation','number'}:
        choice['selections'][0][{'text':'text','citation':'evidence_ids','number':'quoted_values'}[defect]]='injected'
    elif defect=='unknown':choice['selections'][0]['hypothesis_id']='foreign-run-finding'
    elif defect=='duplicate':choice['selections'].append(deepcopy(choice['selections'][0]))
    elif defect=='missing':choice['omissions'].pop()
    elif defect=='no_lead':choice['selections'][0]['placement']='driver'
    elif defect=='two_leads':choice['selections'].append(dict(choice['omissions'].pop(),placement='lead'))
    else:choice['selections'][0]['reason']='   '
    assert validate_plan(choice,source)
    with pytest.raises(ValueError):project(choice,source)


def test_agent6_lineage_and_automatic_ledger(editorial):
    records,_=editorial;source=packet(records);choice=plan(source)
    interaction=next(h for h in source['hypotheses'] if h['agent_id']=='m1_resilience_integration')
    hid=interaction['hypothesis_id']
    choice['omissions']=[d for d in choice['omissions'] if d['hypothesis_id']!=hid]
    choice['selections'].append(dict(hypothesis_id=hid,placement='risk',reason='Material validated interaction.'))
    output=project(choice,source);claim=output['material_risks'][0]
    assert claim['text']==interaction['claim']
    assert claim['hypothesis_ids']==[hid,*interaction['component_hypothesis_ids']]
    assert output['interaction_basis']==[dict(claim_id=claim['claim_id'],agent6_hypothesis_ids=[hid])]
    assert len(output['selection_decisions'])==len(source['hypotheses'])
    for decision in output['selection_decisions']:
        if decision['decision']=='selected':
            assert set(decision['claim_ids'])=={c['claim_id'] for _,c in iter_claims(output) if decision['hypothesis_id'] in c['hypothesis_ids']}
    interaction['transmission_mechanism']=None
    assert validate_plan(choice,source)


def test_cache_and_specialist_definitions_separated():
    old=default_registry('v3',business_orchestrator_contract='bo-competitive-positioning-output-1.0.0')
    new=default_registry('v3',business_orchestrator_contract=contract.OUTPUT_VERSION)
    assert new.get('business_orchestrator').definition_hash()!=old.get('business_orchestrator').definition_hash()
    for agent in ['m1_revenue_quality','m1_customer_stickiness','m1_pricing_power','m1_operating_model','m1_competitive_durability','m1_resilience_integration']:
        assert new.get(agent).definition_hash()==old.get(agent).definition_hash()


@pytest.mark.parametrize('direction,disposition,admissibility', [
    ('positive', 'supported', 'established'),
    ('negative', 'qualified', 'qualified_narrative'),
    ('neutral', 'supported', 'established'),
])
def test_primary_costs_retained_alongside_agent6(editorial, direction, disposition, admissibility):
    from app.schemas.bo import HypothesisRecord
    from app.services.bo.competitive_presentation import grouped_findings, COST
    records, _ = editorial
    cost = next(h for h in records if h.agent_id == 'm1_operating_model')
    cost = HypothesisRecord.model_validate({**cost.model_dump(mode='json'),
        'direction': direction, 'disposition': disposition, 'admissibility': admissibility})
    records = [cost if h.hypothesis_id == cost.hypothesis_id else h for h in records]
    source = packet(records)
    choice = plan(source)
    interaction = next(h for h in source['hypotheses'] if h['agent_id'] == 'm1_resilience_integration')
    choice['omissions'] = [d for d in choice['omissions'] if d['hypothesis_id'] != interaction['hypothesis_id']]
    choice['selections'].append(dict(hypothesis_id=interaction['hypothesis_id'],
        placement='risk', reason='Supplementary interaction.'))
    before = deepcopy((choice, source))
    output = project(choice, source)
    claims = [c for _, c in iter_claims(output)]
    retained = next(c for c in claims if c['claim_id'] == 'selected:' + cost.hypothesis_id)
    assert retained['text'] == cost.claim
    assert retained['claim_type'] == cost.claim_type.value
    assert set(retained['evidence_ids']) == set(cost.evidence_ids())
    assert retained['quoted_values'] == cost.quoted_values
    assert retained['parameter_result_ids'] == cost.parameter_result_ids
    if disposition == 'qualified':
        assert 'Qualified source finding.' in retained['uncertainty']
    assert any(c['claim_id'] == 'selected:' + interaction['hypothesis_id'] for c in claims)
    decision = next(d for d in output['selection_decisions'] if d['hypothesis_id'] == cost.hypothesis_id)
    assert decision['decision'] == 'selected' and 'Mandatory primary cost coverage' in decision['reason']
    audit = dict(run={'analysis_run_id': 'run'}, hypotheses={'records': source['hypotheses']})
    provenance = dict(producer_records=[dict(agent_id=h.agent_id, agent_run_id=h.agent_run_id,
        validation_status='valid') for h in records])
    groups = grouped_findings([dict(claim=c, evidence={}) for c in claims], audit, provenance)
    assert [e['source_hypothesis_id'] for g in groups if g['title'] == COST for e in g['entries']] == [cost.hypothesis_id]
    assert (choice, source) == before


def test_retention_does_not_promote_unverified_costs(editorial):
    from app.schemas.bo import HypothesisRecord
    records, _ = editorial
    cost = next(h for h in records if h.agent_id == 'm1_operating_model')
    unverified = HypothesisRecord.model_validate({**cost.model_dump(mode='json'),
        'hypothesis_id': 'M1S4-H999', 'disposition': 'unverified', 'admissibility': 'audit_only'})
    source = packet([*records, unverified])
    assert 'M1S4-H999' not in {h['hypothesis_id'] for h in source['hypotheses']}
    output = project(plan(source), source)
    assert all('M1S4-H999' not in c['hypothesis_ids'] for _, c in iter_claims(output))


def _with_audit_only(records):
    from app.schemas.bo import HypothesisRecord
    cost = next(h for h in records if h.agent_id == 'm1_operating_model')
    return HypothesisRecord.model_validate({**cost.model_dump(mode='json'),
        'hypothesis_id': 'M1S4-H999', 'disposition': 'unverified', 'admissibility': 'audit_only'})


def _schema_errors(plan_, schema):
    import jsonschema
    return [e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(plan_)]


def test_request_schema_accepts_a_valid_plan_and_stays_within_the_contract(editorial):
    records, _ = editorial
    source = packet(records)
    narrowed = contract.writer_request_schema(h['hypothesis_id'] for h in source['hypotheses'])
    assert _schema_errors(plan(source), narrowed) == []
    assert _schema_errors(plan(source), contract.WRITER_SCHEMA) == []
    assert contract.WRITER_SCHEMA['properties']['schema_version'] == {'const': contract.OUTPUT_VERSION}


@pytest.mark.parametrize('defect', ['audit_only_omission', 'audit_only_selection', 'input_schema_version',
                                    'unknown_id'])
def test_request_schema_rejects_the_recorded_live_failure_modes(editorial, defect):
    """HCA live runs on gemini-3.1-flash-lite (2026-11-08): the selector echoed the input contract version,
    listed audit-only findings as omissions, and selected a finding that was not eligible."""
    records, _ = editorial
    source = packet([*records, _with_audit_only(records)])
    assert [h['hypothesis_id'] for h in source['audit_only_hypotheses']] == ['M1S4-H999']
    narrowed = contract.writer_request_schema(h['hypothesis_id'] for h in source['hypotheses'])
    choice = plan(source)
    if defect == 'audit_only_omission':
        choice['omissions'].append(dict(hypothesis_id='M1S4-H999', reason='Audit-only hypothesis excluded by policy.'))
    elif defect == 'audit_only_selection':
        choice['selections'].append(dict(hypothesis_id='M1S4-H999', placement='risk', reason='Material.'))
    elif defect == 'input_schema_version':
        choice['schema_version'] = contract.INPUT_VERSION
    else:
        choice['omissions'].append(dict(hypothesis_id='M1S9-H001', reason='Invented.'))
    assert _schema_errors(choice, narrowed)


def test_coverage_feedback_names_the_exact_ids(editorial):
    records, _ = editorial
    source = packet([*records, _with_audit_only(records)])
    choice = plan(source)
    missing = choice['omissions'].pop()['hypothesis_id']
    choice['omissions'].append(dict(hypothesis_id='M1S4-H999', reason='Audit-only hypothesis excluded by policy.'))
    choice['omissions'].append(deepcopy(choice['omissions'][0]))
    issue = next(i for i in validate_plan(choice, source) if i.startswith('selection_coverage:'))
    assert 'missing: ' + missing in issue
    assert 'M1S4-H999' in issue.split('not eligible')[1]
    assert 'duplicated: ' + choice['omissions'][0]['hypothesis_id'] in issue


def test_writer_prompt_keeps_audit_only_ids_out_of_both_lists():
    template = contract.WRITER_TEMPLATE
    assert 'never put their IDs in selections or in\nomissions' in template
    assert f'schema_version to\n{contract.OUTPUT_VERSION}' in template
