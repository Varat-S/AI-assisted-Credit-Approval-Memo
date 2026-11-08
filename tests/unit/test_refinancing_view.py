from copy import deepcopy

from app.services.bo.refinancing_view import refinancing_view, source_pages


def test_printed_financial_page_ranges_do_not_match_numeric_pages():
    assert source_pages(['69-70', 'F-22-F-23']) == {'69', '70', 'F-22', 'F-23'}
    assert source_pages(['F-22–23', '70']) == {'F-22', 'F-23', '70'}


def test_timeline_preserves_source_period_and_facility_scope_without_netting():
    original = {'refinancing_log': [
        {'transaction_category': 'facility_amendment', 'principal_amount_m': 8000,
         'execution_date_fiscal_period': 'FY2025'},
        {'transaction_category': 'repayment_at_maturity', 'principal_amount_m': 4416,
         'execution_date_fiscal_period': 'FY2025'},
    ]}
    before = deepcopy(original)
    view = refinancing_view(original)
    assert original == before
    assert [entry['record'] for entry in view['entries']] == original['refinancing_log']
    assert [(entry['amount'], entry['amount_label']) for entry in view['entries']] == [
        ('$8,000M', 'Facility amount'), ('$4,416M', 'Principal repaid')]
    view['entries'][0]['record']['execution_date_fiscal_period'] = 'changed'
    assert original == before
    assert refinancing_view({'refinancing_log': []}) is None
    assert refinancing_view(None) is None


def test_extension_is_distinguished_from_issuance_and_retirement():
    from app.services.bo.refinancing_view import maturity_outcome
    assert maturity_outcome({'original_retired_maturity': '2026-2028', 'new_extended_maturity': '2030'}) == 'Debt maturity extended to 2030'
    assert maturity_outcome({'new_extended_maturity': '2028-2055'}) == 'Debt maturity: 2028-2055'
    assert maturity_outcome({'transaction_category': 'early_redemption'}) == 'Debt maturity: Repaid Before Maturity'
    assert maturity_outcome({'transaction_category': 'repayment_at_maturity'}) == 'Debt maturity: Repaid at maturity'
    assert maturity_outcome({}) == 'Debt maturity: Not recorded'
