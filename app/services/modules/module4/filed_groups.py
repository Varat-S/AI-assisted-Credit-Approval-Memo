"""Narrow, source-checked recovery of a debt category replaced by a component."""
import math
import re


def _contexts(snippets):
    for snippet in snippets:
        yield {**snippet, 'fact_ids': [snippet['fact_id']]}
    ordered = sorted([s for s in snippets if s.get('document_id') and isinstance(s.get('location'), int)],
                     key=lambda s: (s['document_id'], str(s.get('section')), s['location']))
    for left, right in zip(ordered, ordered[1:]):
        if (left['document_id'] == right['document_id'] and left.get('section') == right.get('section')
                and left['location'] + len(left['text']) == right['location']):
            yield {**left, 'text': left['text'] + right['text'], 'fact_ids': [left['fact_id'], right['fact_id']]}


def recover_filed_groups(output, inputs):
    """Use a tagged category amount only when the filing explains its components.

    Never fill a reconciliation gap from arithmetic alone, add invented notes,
    or overwrite an itemized schedule. The borrower and other legal terms stay
    as supplied; the existing Validator 8 still validates the complete result.
    """
    rows = output.deliverable_1.senior_notes_schedule
    if len(rows) != 1 or inputs.filed_total is None:
        return output, []
    row = rows[0]
    if not re.search(r'senior\s+unsecured\s+notes', row.senior_note_series, re.I) or re.search(r'\d|%', row.senior_note_series):
        return output, []
    facts = [f for f in inputs.structured_financials
             if str(f.get('concept', '')).split(':')[-1].split('}')[-1] == 'UnsecuredDebt'
             and f.get('period') == inputs.filed_total.period_end
             and any(str(k).endswith('LongtermDebtTypeAxis') and str(v).endswith('SeniorUnsecuredNotesMember')
                     for k, v in (f.get('dimensions') or {}).items())
             and str(f.get('unit', '')).lower() == 'usd_million'
             and isinstance(f.get('value'), (int, float)) and not isinstance(f.get('value'), bool)]
    values = {float(f['value']) for f in facts}
    if len(values) != 1:
        return output, []
    total = values.pop()
    if not math.isfinite(total) or total <= row.principal_amount_m:
        return output, []
    pattern = (r'senior\s+unsecured\s+notes\s+consist\s+of\s*\(i\)\s*\$([\d,.]+)\s+(billion|million)'
               r'\s+aggregate principal amount of senior notes[^.]{0,300}?'
               r'\s+and\s*\(ii\)\s*an aggregate principal amount of\s*\$([\d,.]+)\s+(billion|million)\s+debentures')
    for snippet in _contexts(inputs.sec_filing_snippets):
        text = ' '.join(snippet.get('text', '').split())
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        first = float(match[1].replace(',', '')) * (1000 if match[2].lower() == 'billion' else 1)
        second = float(match[3].replace(',', '')) * (1000 if match[4].lower() == 'billion' else 1)
        if not (math.isclose(first, row.principal_amount_m, abs_tol=1e-6, rel_tol=0)
                and math.isclose(first + second, total, abs_tol=1e-6, rel_tol=0)):
            continue
        corrected = output.model_copy(deep=True)
        corrected_row = corrected.deliverable_1.senior_notes_schedule[0]
        corrected_row.principal_amount_m = total
        corrected_row.senior_note_series = 'Senior Unsecured Notes and Debentures'
        # Preserve the category's latest disclosed maturity when the breakdown states both ranges.
        composition = text[match.start():match.end() + 100]
        ranges = re.findall(r'maturities ranging from (\d{4}) to (\d{4})', composition, re.I)
        if len(ranges) == 2:
            corrected_row.maturity_year = max(int(end) for _, end in ranges)
        return corrected, [{'field': 'deliverable_1.senior_notes_schedule[0].principal_amount_m',
                            'model_amount_m': row.principal_amount_m, 'filed_amount_m': total,
                            'fact_id': facts[0]['fact_id'], 'evidence_id': snippet['fact_id'],
                            'supporting_evidence_ids': snippet['fact_ids'],
                            'quote': composition, 'reason': 'Model used the notes component in place of the filed notes-and-debentures category.'}]
    return output, []
