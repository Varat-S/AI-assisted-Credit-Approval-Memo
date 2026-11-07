from copy import deepcopy

from lxml import html

from app.services.bo.four_section_view import _env, display
from app.services.bo.loan_ranking_view import loan_ranking_view


def test_saved_debt_is_read_only_and_reconciliation_excludes_undrawn_capacity():
    debt = {'creditor_priority_framework': {
        'tier_1_direct_opco_secured_m': 1021, 'tier_2_senior_unsecured_guaranteed_m': 45907,
        'tier_3_unguaranteed_holdco_m': 0, 'consolidated_total_indebtedness_m': 46492,
        'structural_subordination_drag_ratio': 0.021960767443861308,
        'prospective_loan_secured_placement': 'Guaranteed first priority.'},
        'senior_notes_schedule': [{'principal_amount_m': 43700}],
        'non_note_obligations_schedule': [{'principal_drawn_m': 2207, 'available_facility_limit_m': None},
            {'principal_drawn_m': 0, 'available_facility_limit_m': 5779}, {'principal_drawn_m': 1021}],
        'reconciling_items': [{'label': 'Deferred Finance Costs Net', 'amount_m': -436}]}
    original = deepcopy(debt)
    view = loan_ranking_view(debt)
    assert 'US$1.02bn' in view['summary'] and 'US$45.91bn' in view['summary']
    r = view['reconciliation']
    assert r['note_principal_m'] + r['other_drawn_m'] + sum(i['amount_m'] for i in r['items']) == r['reported_total_m']
    for pdf in (False, True):
        page = html.fromstring(_env.get_template('bo_loan_ranking.html.j2').render(bo4={'loan_ranking': view}, pdf=pdf))
        text = page.text_content()
        assert len(page.xpath('//tbody/tr')) == 3
        assert 'conditional' in text and 'no proposed loan ranking has been confirmed' in text
        assert 'Guaranteed first priority.' not in text and 'drag ratio' not in text
        assert 'Tier 1' not in text and 'Tier 2' not in text
    assert debt == original


def test_missing_and_zero_figures_are_distinguished_and_reconciliation_is_in_evidence():
    assert loan_ranking_view(None) is None
    view = loan_ranking_view({'creditor_priority_framework': {'tier_1_direct_opco_secured_m': 0}})
    assert 'US$0.00bn of secured' in view['summary']
    assert 'senior unsecured' not in view['summary']
    item = {'title': 'Debt Obligations', 'id': 'debt', 'reconciliation': view['reconciliation']}
    template = _env.from_string("{% from 'bo_evidence.html.j2' import evidence with context %}{{ evidence(item) }}")
    page = html.fromstring(template.render(item=item, bo4={'memo': {'identity': {'analysis_run_id': 'test', 'evidence_snapshot_version': 1}}, 'display': display}, pdf=False))
    assert page.xpath('//details[@class="bo-evidence"]//h4[text()="Debt reconciliation"]')
    assert 'Not recorded' in page.text_content()
