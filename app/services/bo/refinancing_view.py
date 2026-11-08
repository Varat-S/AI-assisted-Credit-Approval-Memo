"""Display saved refinancing transactions without deriving new credit conclusions."""
from copy import deepcopy
from decimal import Decimal
import re


CATEGORIES = {
    'new_issuance': ('Notes issued', 'Principal issued'),
    'repayment_at_maturity': ('Scheduled repayment', 'Principal repaid'),
    'early_redemption': ('Early redemption', 'Principal retired'),
    'facility_amendment': ('Facility amendment', 'Facility amount'),
    'tender_exchange': ('Tender / exchange', 'Transaction principal'),
}


def maturity_outcome(row):
    """An issuance or retirement is not automatically a maturity extension."""
    old, new = row.get('original_retired_maturity'), row.get('new_extended_maturity')
    if new:
        old_years = [int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b', old or '')]
        new_years = [int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b', new)]
        if old_years and new_years and min(new_years) > max(old_years):
            return 'Debt maturity extended to ' + new
        return 'Debt maturity: ' + new
    return {
        'early_redemption': 'Debt maturity: Repaid Before Maturity',
        'repayment_at_maturity': 'Debt maturity: Repaid at maturity',
    }.get(row.get('transaction_category'), 'Debt maturity: Not recorded')


def refinancing_view(deliverable):
    """Preserve source order and dates; never invent execution dates or net amounts."""
    if not isinstance(deliverable, dict):
        return None
    entries = []
    for row in deliverable.get('refinancing_log') or []:
        category, amount_label = CATEGORIES.get(row.get('transaction_category'),
                                                ('Refinancing transaction', 'Recorded amount'))
        amount = row.get('principal_amount_m')
        formatted = format(Decimal(str(amount)), ',f') if amount is not None else None
        if formatted and '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        entries.append({
            'record': deepcopy(row),
            'category': category,
            'amount_label': amount_label,
            'amount': '$' + formatted + 'M' if formatted is not None else 'Not recorded',
            'original_maturity': row.get('original_retired_maturity') or 'Not recorded',
            'maturity_outcome': maturity_outcome(row),
            # Redemption records must not imply an unproven funding source or
            # strategic motive. The original specialist wording stays in audit.
            'summary': ('Repaid $' + formatted + 'M principal before maturity.'
                        if row.get('transaction_category') == 'early_redemption' and formatted is not None
                        else row.get('use_of_proceeds_impact', '')),
        })
    return {'entries': entries} if entries else None


def source_pages(references):
    """Expand the specialist's explicit printed page references, including F-pages."""
    pages = set()
    for reference in references:
        reference = re.sub(r'^Item\s+\d+\s*,?\s*(?:pp?\.?\s*)?', '', reference, flags=re.I)
        for match in re.finditer(r'(?<![\w-])(F-)?(\d+)(?:\s*[-–]\s*(?:F-)?(\d+))?', reference, re.I):
            prefix, start, end = match.groups()
            start, end = int(start), int(end or start)
            if 0 <= end - start <= 100:
                pages.update(('F-' if prefix else '') + str(n) for n in range(start, end + 1))
    return pages
