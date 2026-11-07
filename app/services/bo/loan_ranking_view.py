"""Conditional loan-ranking display of saved debt figures; no new credit assessment."""
from copy import deepcopy


def loan_ranking_view(debt):
    if not debt:
        return None
    framework = debt.get('creditor_priority_framework') or {}
    categories = []
    for field, label in [
        ('tier_1_direct_opco_secured_m', 'secured operating-company debt'),
        ('tier_2_senior_unsecured_guaranteed_m', 'senior unsecured guaranteed debt'),
        ('tier_3_unguaranteed_holdco_m', 'unguaranteed holding-company debt'),
    ]:
        value = framework.get(field)
        if value is not None:
            categories.append(f'US${value / 1000:,.2f}bn of {label}')
    summary = ('The saved assessment records ' + '; '.join(categories) + '.'
               if categories else 'Debt amounts by creditor category were not recorded.')
    return {
        'summary': summary,
        'scope': 'The position of a new loan depends on its borrower, collateral and guarantees. '
                 'The cases below are conditional; no proposed loan ranking has been confirmed.',
        'cases': [
            {'loan': 'Secured loan to the operating company',
             'position': 'Could rank ahead of unsecured creditors against its pledged collateral. '
                         'Its position relative to existing secured debt depends on lien priority.',
             'confirm': 'Available collateral, existing liens, and permission to grant security.'},
            {'loan': 'Unsecured loan to the operating company',
             'position': 'Would generally sit alongside comparable senior unsecured obligations of '
                         'the same borrower, behind secured claims against pledged assets.',
             'confirm': 'Borrower, guarantees, contractual ranking and any subordination terms.'},
            {'loan': 'Loan to the holding company without operating-company guarantees',
             'position': 'Relies on cash reaching the holding company. Operating-company creditors '
                         'have claims against those companies’ assets first.',
             'confirm': 'Where cash and assets sit, and whether subsidiaries provide guarantees.'},
        ],
        'to_confirm': [
            'The proposed borrowing entity and which companies would guarantee the loan.',
            'For a secured loan: the assets offered, existing liens and permitted lien priority.',
            'Restrictions in existing debt agreements on the proposed borrowing and guarantees.',
        ],
        'reconciliation': {
            'note_principal_m': sum(r['principal_amount_m'] for r in debt.get('senior_notes_schedule', [])),
            'other_drawn_m': sum(r['principal_drawn_m'] for r in debt.get('non_note_obligations_schedule', [])),
            'items': deepcopy(debt.get('reconciling_items', [])),
            'reported_total_m': framework.get('consolidated_total_indebtedness_m'),
        },
    }
