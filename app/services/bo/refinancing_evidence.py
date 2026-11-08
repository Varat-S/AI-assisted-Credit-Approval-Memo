"""Select completed debt transactions, never contractual redemption options."""
from decimal import Decimal
import re

from app.services.bo.evidence_presentation import covering_passages, normalized
from app.services.bo.refinancing_view import source_pages

HISTORY = re.compile(
    r'\b(?:we|chs|(?:the )?company)(?: and chs)?\s+(?:also\s+)?(?:issued|repaid|redeemed|repurchased|'
    r'completed|entered into|exercised|terminated|amended|extinguished|used)\b|'
    r'\bwere\s+(?:used to (?:redeem|repay|repurchase)|redeemed|repaid|repurchased)\b|'
    r'\bwas amended and restated\b|\blenders have extended\b', re.I)
OPTION = re.compile(r'\b(?:may|might|could|will|would|can)\s+(?:also\s+)?(?:redeem|repay|repurchase)|'
                    r'\b(?:entitled|at (?:its|our) option|right to redeem)\b', re.I)
MONTHS = r'January|February|March|April|May|June|July|August|September|October|November|December'
MONEY = re.compile(r'\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million)?', re.I)


def amounts(text):
    return [Decimal(n.replace(',', '')) * (1000 if (unit or '').lower() == 'billion' else 1)
            for n, unit in MONEY.findall(text)]


def related(text, row):
    """Match a recorded transaction amount, including explicit component repayments."""
    value = row.get('principal_amount_m')
    if value is None:
        return False
    target = Decimal(str(value))
    values = amounts(text)
    if target in values:
        return True
    if row.get('transaction_category') == 'facility_amendment':
        date = re.search(r'[A-Z][a-z]+ \d{1,2}, \d{4}', row.get('execution_date_fiscal_period', ''))
        if date and date.group() in text and 'ABL' in text and 'ABL' in row.get('obligation_series_description', ''):
            return True
    return row.get('transaction_category') == 'repayment_at_maturity' and sum(values) == target


def matches_event(text, row):
    """Amount alone cannot make an issuance prove a redemption of the same size."""
    actions = {
        'new_issuance': r'\b(?:issued|completed (?:a private |an |the )?offering)\b',
        'early_redemption': r'\b(?:redeemed|repurchased|extinguished|exercised)\b|\bused\b.*?\bto (?:redeem|repurchase)\b',
        'repayment_at_maturity': r'\b(?:repaid|redeemed|paid|retired)\b.*?\bat maturity\b',
        'facility_amendment': r'\b(?:entered into|amended and restated|lenders have extended)\b',
        'tender_exchange': r'\b(?:redeemed|repurchased|extinguished|accepted for purchase|completed.*tender)\b',
    }
    if row.get('transaction_category') == 'early_redemption' and re.search(r'\bat maturity\b', text, re.I):
        return False
    maturity_years = set(re.findall(r'\b(?:19|20)\d{2}\b', row.get('original_retired_maturity') or ''))
    source_maturities = set(re.findall(r'(?:notes?|debentures?)\s+(?:due|maturing in)\s+((?:19|20)\d{2})', text, re.I))
    if maturity_years and source_maturities and not maturity_years & source_maturities:
        return False
    return related(text, row) and bool(re.search(actions.get(row.get('transaction_category'), r'(?!)'), text, re.I))


def historical_quotes(deliverable, citations, indexes):
    pages = source_pages((deliverable.get('extraction_source') or {}).get('page_references', []))
    rows = deliverable.get('refinancing_log') or []
    execution_years = {y for row in rows for y in re.findall(r'\b(?:19|20)\d{2}\b', row.get('execution_date_fiscal_period', ''))}
    by_document = {}
    for citation in citations:
        passage = citation['passage']
        by_document.setdefault(passage['document_id'], []).append(passage)
    quotes, seen = [], set()
    for document_id, passages in by_document.items():
        # Model page references are hints, not proof: scan the checksum-verified
        # source and still require continuous coverage by this run's debt evidence.
        paragraphs = sorted(indexes.get(document_id) or [], key=lambda p: str(p.get('page')) not in pages)
        for paragraph in paragraphs:
            # Split on sentence endings, not decimal coupon rates or dollar amounts.
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', paragraph['text'])
            historical = []
            for sentence in sentences:
                event = HISTORY.search(sentence)
                if not event or OPTION.search(sentence):
                    continue
                # Do not attach a subsequent-year redemption of the same amount
                # to an earlier transaction merely because both appear together.
                prefix = sentence[:event.start()]
                dated = set(re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December) '
                                       r'(?:\d{1,2}, )?((?:19|20)\d{2})\b', prefix, re.I))
                dated.update(re.findall(r'\b(?:during|in) ((?:19|20)\d{2})\b', prefix, re.I))
                if execution_years and dated and not dated & execution_years:
                    continue
                # Where a month is explicitly recorded, do not attach another
                # month's same-size transaction. Respect jointly dated events.
                row_months = {m.lower() for row in rows for m in re.findall(MONTHS, row.get('execution_date_fiscal_period', ''), re.I)}
                source_months = {m.lower() for m in re.findall(MONTHS, prefix, re.I)}
                if (dated and row_months and source_months and not row_months & source_months
                        and not any(re.search(r'/\s*Q[1-4]', row.get('execution_date_fiscal_period', '')) for row in rows)):
                    continue
                historical.append(sentence)
            # Keep the transaction's use-of-proceeds sentence with its issuance,
            # even when it states the retired amount rather than the issued amount.
            if not any(matches_event(s, row) for s in historical for row in rows):
                continue
            for sentence in historical:
                if not any(matches_event(sentence, row) for row in rows):
                    # Only linked use-of-proceeds / replaced-facility context;
                    # another event mentioned in the same paragraph is not support.
                    if not re.search(r'^(?:We used (?:the )?net proceeds|(?:The )?Proceeds (?:from|of)|We terminated)', sentence, re.I):
                        continue
                if not re.search(r'\b(notes|debentures|credit|facility|facilities|paper|loan|offering)\b', sentence, re.I):
                    continue
                key = (document_id, normalized(sentence))
                if key in seen:
                    continue
                support = covering_passages(sentence, passages)
                if not support:
                    continue
                seen.add(key)
                quotes.append({'quote': sentence, 'document_id': document_id,
                               'supporting_evidence_ids': support})
    return quotes
