from types import SimpleNamespace

from app.schemas.module4 import ReconcilingItem, ReconcilingItemKind
from app.services.bo.m4_debt import build_debt_inputs
from app.services.modules.module4.debt_structure_validator import verify_reconciling_items

# Shaped like canonical-snapshot facts (CYH FY2025): name / normalized_value /
# raw_value / period_end, no value or period keys.
SCHEDULE = ("Long-term debt, net of unamortized debt issuance costs and discounts or "
            "premiums, consists of the following (in millions):\n9¾% Senior Secured "
            "Notes due 2034\n1,790\nOther\n25\nLess: Unamortized deferred debt "
            "issuance costs\n(217\n)\nTotal debt\n10,396")


def snapshot_facts():
    return [
        {'fact_id': 'tb', 'name': 'us-gaap:ScheduleOfDebtTableTextBlock',
         'raw_value': SCHEDULE, 'normalized_value': None, 'period_end': '2025-12-31',
         'source_refs': [{'document_id': 'doc-10k'}]},
        {'fact_id': 'num', 'name': 'us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths',
         'raw_value': '16', 'normalized_value': 16.0, 'normalized_unit': 'USD_millions',
         'period_end': '2025-12-31'},
    ]


def test_snapshot_fact_fields_reach_the_specialist():
    inputs = build_debt_inputs(SimpleNamespace(narrative_evidence=[], facts=snapshot_facts()))
    assert inputs.structured_financials == [{
        'fact_id': 'num',
        'concept': 'us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths',
        'value': 16.0, 'unit': 'USD_millions', 'period': '2025-12-31'}]


def test_debt_text_block_is_a_quotable_snippet():
    inputs = build_debt_inputs(SimpleNamespace(narrative_evidence=[], facts=snapshot_facts()))
    [snippet] = inputs.sec_filing_snippets
    assert snippet['fact_id'] == 'tb' and snippet['text'] == SCHEDULE
    assert snippet['document_id'] == 'doc-10k'
    assert not inputs.missing_critical_evidence

    item = ReconcilingItem(
        kind=ReconcilingItemKind.ISSUANCE_COSTS_AND_DISCOUNTS,
        label='Unamortized deferred debt issuance costs', amount_m=-217.0,
        quote='Less: Unamortized deferred debt issuance costs (217)', evidence_id='tb')
    [check] = verify_reconciling_items([item], inputs.filing_passages())
    assert check.verified, check.reason
