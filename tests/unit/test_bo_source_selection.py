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
