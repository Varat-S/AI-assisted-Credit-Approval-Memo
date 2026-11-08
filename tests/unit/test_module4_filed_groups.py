from dataclasses import replace
from app.schemas.module4 import Module4Output
from app.services.modules.module4.specialist import Module4Inputs
from app.services.modules.module4.filed_groups import recover_filed_groups
from app.services.modules.module4.filed_total import FiledDebtTotal
from tests.fixtures.hca_module4 import hca_module4_output


def case():
    output = Module4Output.model_validate(hca_module4_output())
    row = output.deliverable_1.senior_notes_schedule[0].model_copy(update={
        'senior_note_series': 'Senior Unsecured Notes Payable', 'principal_amount_m': 43250})
    output.deliverable_1.senior_notes_schedule = [row]
    inputs = Module4Inputs(sec_filing_snippets=[{'fact_id': 'composition', 'text':
        'Senior unsecured notes consist of (i) $43.250 billion aggregate principal amount of senior notes '
        'with maturities ranging from 2026 to 2064 and (ii) an aggregate principal amount of $450 million '
        'debentures with maturities ranging from 2027 to 2095.'}],
        structured_financials=[{'fact_id': 'category', 'concept': 'us-gaap:UnsecuredDebt',
            'period': '2025-12-31', 'value': 43700, 'unit': 'USD_million',
            'dimensions': {'us-gaap:LongtermDebtTypeAxis': '{issuer}SeniorUnsecuredNotesMember'}}],
        filed_total=FiledDebtTotal(total_m=46492, concept='Debt', fact_id='total', period_end='2025-12-31'))
    return output, inputs


def test_missing_debentures_recovered_from_tagged_category_and_explicit_breakdown():
    output, inputs = case()
    repaired, audit = recover_filed_groups(output, inputs)
    assert repaired.deliverable_1.senior_notes_schedule[0].principal_amount_m == 43700
    assert repaired.deliverable_1.senior_notes_schedule[0].maturity_year == 2095
    assert repaired.deliverable_1.senior_notes_schedule[0].senior_note_series == 'Senior Unsecured Notes and Debentures'
    assert output.deliverable_1.senior_notes_schedule[0].principal_amount_m == 43250
    assert audit[0]['fact_id'] == 'category' and audit[0]['evidence_id'] == 'composition'
    assert not recover_filed_groups(repaired, inputs)[1]


def test_no_repair_for_missing_conflicting_old_or_unrelated_source_evidence():
    output, inputs = case()
    for changed in [replace(inputs, sec_filing_snippets=[]), replace(inputs, structured_financials=[]),
                    replace(inputs, structured_financials=[{**inputs.structured_financials[0], 'period':'2024-12-31'}]),
                    replace(inputs, structured_financials=[{**inputs.structured_financials[0], 'value':44000}]),
                    replace(inputs, structured_financials=[{**inputs.structured_financials[0], 'dimensions':{}}]),
                    replace(inputs, structured_financials=[{**inputs.structured_financials[0], 'unit':'EUR_million'}])]:
        result, audit = recover_filed_groups(output, changed)
        assert not audit and result is output
    output.deliverable_1.senior_notes_schedule *= 2
    assert not recover_filed_groups(output, inputs)[1]


def test_breakdown_spanning_adjacent_canonical_chunks_is_recovered_without_bridging_a_gap():
    output, inputs = case(); text = inputs.sec_filing_snippets[0]['text']; split = 70
    inputs.sec_filing_snippets = [
        {'fact_id':'left','text':text[:split],'document_id':'filing','section':'Item 8','location':0},
        {'fact_id':'right','text':text[split:],'document_id':'filing','section':'Item 8','location':split}]
    repaired, audit = recover_filed_groups(output, inputs)
    assert repaired.deliverable_1.senior_notes_schedule[0].principal_amount_m == 43700
    assert audit[0]['supporting_evidence_ids'] == ['left','right']
    inputs.sec_filing_snippets[1]['location'] += 1
    assert not recover_filed_groups(output, inputs)[1]


def test_recovered_schedule_passes_real_specialist_and_all_validator_checks(db_session):
    from app.prompts.registry import PromptRegistry
    from app.schemas.module4 import ReconcilingItem, ReconcilingItemKind
    from app.services.llm.client import FakeLLMBackend, LLMClient
    from app.services.modules.module4.specialist import Module4Specialist
    output, inputs = case()
    # Carrying-value bridge is a reconciling line, never a drawn debt instrument.
    output.deliverable_1.non_note_obligations_schedule = [
        r for r in output.deliverable_1.non_note_obligations_schedule if r.principal_drawn_m >= 0]
    bridge = ReconcilingItem(kind=ReconcilingItemKind.ISSUANCE_COSTS_AND_DISCOUNTS,
        label='Debt issuance costs and discounts', amount_m=-436,
        quote='Debt issuance costs and discounts (436)', evidence_id='bridge')
    inputs.filed_total = replace(inputs.filed_total, face_m=46928, bridge=bridge)
    inputs.sec_filing_snippets.append({'fact_id':'bridge','text':bridge.quote})
    inputs.structured_financials.extend([{'fact_id':str(value), 'value':value,'unit':'USD_million'}
                                       for value in [2207,1021,4000,8000,46492,436]])
    prompts = PromptRegistry(db_session); prompts.register_catalogue()
    backend = FakeLLMBackend();backend.register('analyze', output.model_dump(mode='json'))
    result = Module4Specialist(LLMClient(backend,prompts=prompts,session=db_session), case_id='TEST').run(inputs)
    assert result.validated, [c.detail for c in result.validator8.failures]
    assert result.filed_total['schedule_group_corrections'][0]['filed_amount_m'] == 43700
