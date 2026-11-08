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
        for paragraph in indexes.get(document_id) or []:
            if str(paragraph.get('page')) not in pages:
                continue
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
                                       r'\d{1,2}, ((?:19|20)\d{2})\b', prefix, re.I))
                dated.update(re.findall(r'\b(?:during|in) ((?:19|20)\d{2})\b', prefix, re.I))
                if execution_years and dated and not dated & execution_years:
                    continue
                historical.append(sentence)
            # Keep the transaction's use-of-proceeds sentence with its issuance,
            # even when it states the retired amount rather than the issued amount.
            if not any(related(s, row) for s in historical for row in rows):
                continue
            for sentence in historical:
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
