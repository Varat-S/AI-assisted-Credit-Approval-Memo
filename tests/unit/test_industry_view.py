from copy import deepcopy

from app.prompts.bo_prompts import bo_v3_prompt_catalogue
from app.services.bo.hypotheses import HypothesisValidator
from app.services.bo.indicators import IndicatorSet
from app.services.bo.industry_view import group_findings
from app.services.bo.roster_v3 import M2_INDUSTRY
from app.services.bo.synthesis import hypothesis_view


def item(category='headwind', direction='negative', kind='development'):
    return {'hypothesis_id': 'M2-H001', 'claim': 'Our revenues depend on regulated reimbursement rates.',
            'claim_type': 'fact', 'direction': direction, 'disposition': 'supported',
            'supporting_evidence_ids': ['e1'],
            'evidence_quotes': [{'evidence_id': 'e1', 'quote': 'Our revenues depend on regulated reimbursement rates.'}],
            'interpretation': {'implication': 'Payment changes affect revenue realization.',
                               'company_response': 'The company operates outpatient facilities.',
                               'watch_trigger': 'Changes in payment rules.'},
            'industry': {'kind': kind, 'category': category, 'title': 'Regulated reimbursement',
                         'state': 'structural', 'linked_development_ids': []}}


def validate(value):
    return HypothesisValidator(M2_INDUSTRY, passages={'e1': 'Our revenues depend on regulated reimbursement rates. The company operates outpatient facilities.'},
                               indicators=IndicatorSet()).validate({'hypotheses': [value]}, analysis_run_id='AR', agent_run_id='RUN')


def test_industry_fields_survive_validation_and_governed_handoff():
    result = validate(item());assert result.records
    view = hypothesis_view(result.records[0])
    assert view['industry']['category'] == 'headwind'
    assert view['interpretation']['company_response'] == 'The company operates outpatient facilities.'
    assert view['industry']['state'] == 'structural'


def test_invalid_category_direction_or_exposure_is_not_used():
    for value in [item(category='tailwind'), item(kind='exposure'), item(category='company_exposure')]:
        result = validate(value);assert result.records
        assert result.records[0].industry is None
        assert any('Industry metadata rejected' in n for n in result.records[0].validation_notes)


def test_unbound_response_numbers_are_withheld():
    value = item();value['interpretation']['company_response'] = 'The company reduced costs by 987654%.'
    result = validate(value)
    assert 'company_response' not in result.records[0].interpretation


def test_groups_keep_exposure_separate_and_never_fabricate_tailwinds():
    development = item();exposure = item('company_exposure', 'neutral', 'exposure')
    exposure['hypothesis_id'] = 'M2-H002';exposure['industry']['linked_development_ids'] = ['M2-H001', 'missing']
    original = deepcopy([development, exposure])
    view = group_findings([development, exposure])
    assert len(view['groups'][1]['findings']) == 1
    assert view['groups'][0]['findings'] == []
    assert len(view['exposures']) == 1 and view['exposures'][0]['links'] == [{'id': 'M2-H001', 'title': 'Regulated reimbursement'}]
    assert [development, exposure] == original


def test_only_industry_specialist_schema_gets_metadata_and_offset():
    prompts = {p['name']: p for p in bo_v3_prompt_catalogue()}
    m2 = prompts['m2_industry']
    assert 'company_exposure' in m2['template'] and 'do not force' in m2['template'].lower()
    props = m2['response_schema']['properties']['hypotheses']['items']['properties']
    assert 'industry' in props and 'company_response' in props['interpretation']['properties']
    assert 'industry' not in prompts['m1_revenue_quality']['response_schema']['properties']['hypotheses']['items']['properties']
