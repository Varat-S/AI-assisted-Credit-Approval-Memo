from app.schemas.module4 import ReconcilingItemKind
from app.services.modules.module4.filed_total import filed_debt_total


def fact(name, value, *, fid=None, period="2025-12-31", dims=None, unit="USD_million"):
    return {"fact_id": fid or f"{name}-{value}", "name": f"us-gaap:{name}", "normalized_value": value,
            "normalized_unit": unit, "period_end": period, "dimensions": dims or {}}


def test_hca_takes_the_combined_total_over_long_term_debt():
    """HCA FY2025: LongTermDebt 44,285 leaves out commercial paper; the combined total is the total."""
    total = filed_debt_total([
        fact("LongTermDebt", 44285.0),
        fact("DebtLongtermAndShorttermCombinedAmount", 46492.0, fid="combined"),
        fact("DebtInstrumentCarryingAmount", 46928.0),
        fact("DeferredFinanceCostsNet", 436.0, fid="costs"),
    ])
    assert (total.total_m, total.concept, total.fact_id) == (
        46492.0, "DebtLongtermAndShorttermCombinedAmount", "combined")
    assert total.face_m == 46928.0
    assert total.bridge.amount_m == -436.0 and total.bridge.evidence_id == "costs"
    assert total.bridge.kind is ReconcilingItemKind.ISSUANCE_COSTS_AND_DISCOUNTS


def test_cyh_bridges_a_negatively_tagged_cost():
    total = filed_debt_total([
        fact("DebtAndCapitalLeaseObligations", 10396.0),
        fact("DebtAndCapitalLeaseObligations", 1244.0, dims={"us-gaap:DebtInstrumentAxis": "x"}),
        fact("DebtInstrumentCarryingAmount", 10613.0),
        fact("DebtInstrumentUnamortizedDiscountPremiumAndDebtIssuanceCostsNet", -217.0),
    ])
    assert total.total_m == 10396.0 and total.bridge.amount_m == -217.0


def test_the_bridge_settles_a_concept_tagged_twice():
    """UHS FY2025 tags LongTermDebt as 4,752.551 and, from prose, 4,800."""
    total = filed_debt_total([
        fact("LongTermDebt", 4800.0),
        fact("LongTermDebt", 4752.551),
        fact("DebtInstrumentCarryingAmount", 4768.261),
        fact("DebtInstrumentUnamortizedDiscountPremiumAndDebtIssuanceCostsNet", 15.71),
    ])
    assert total.total_m == 4752.551 and total.bridge.amount_m == -15.71


def test_a_total_without_a_tagged_bridge_stands_alone():
    """EHC FY2025 tags no costs line, so only the total is fixed."""
    total = filed_debt_total([fact("DebtAndCapitalLeaseObligations", 2490.8)])
    assert total.total_m == 2490.8 and total.face_m is None and total.bridge is None


def test_an_unsettled_double_tag_is_passed_over():
    total = filed_debt_total([fact("LongTermDebt", 4800.0), fact("LongTermDebt", 4752.551)])
    assert total is None


def test_the_latest_period_is_the_total():
    total = filed_debt_total([fact("LongTermDebt", 43031.0, period="2024-12-31"),
                              fact("LongTermDebt", 44285.0)])
    assert total.total_m == 44285.0 and total.period_end == "2025-12-31"


def test_dollars_are_read_in_millions_and_non_dollar_facts_ignored():
    total = filed_debt_total([fact("LongTermDebt", 2_490_800_000, unit="USD"),
                              fact("DebtAndCapitalLeaseObligations", 3.0, unit="shares")])
    assert total.total_m == 2490.8 and total.concept == "LongTermDebt"


def test_no_tagged_total():
    assert filed_debt_total([fact("InterestExpense", 1900.0)]) is None
    assert filed_debt_total(None) is None
