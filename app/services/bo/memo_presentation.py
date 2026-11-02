"""Read-only memo labels/formatting. Never changes an analytical artifact."""
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

PRIORITY_LABELS = {
    'tier_1_direct_opco_secured': 'Tier 1 · Direct operating-company secured',
    'tier_2_senior_unsecured_guaranteed': 'Tier 2 · Senior unsecured, guaranteed',
    'tier_3_unguaranteed_holdco': 'Tier 3 · Unguaranteed holding-company debt',
}
TRANSACTION_LABELS = {'new_issuance':'New issuance','repayment_at_maturity':'Repayment at maturity',
    'early_redemption':'Early redemption','facility_amendment':'Facility amendment','tender_exchange':'Tender / exchange'}
SECURITY_LABELS = {'secured':'Secured', 'unsecured':'Unsecured'}
STATUS_LABELS = {'pending':'Pending','accepted':'Accepted','rejected':'Rejected',
                 'complete':'Complete','incomplete':'Incomplete','missing':'Missing',
                 'mixed':'Mixed','unavailable':'Unavailable','qualified':'Qualified',
                 'supported':'Supported','not_recorded':'Not recorded'}
NOTICE_PREFIXES = {'generic_risk_disclosure_only','quote_does_not_cover_claim'}
DEBT_SUMMARY_FIELDS = frozenset({'senior_note_series','obligation_facility','legal_borrower',
    'principal_amount_m','principal_drawn_m','amount_m','label','maturity_year','maturity',
    'collateral_security_status','priority_ranking_tier'})


def classification(value, kind='status'):
    if value is None or value == '':return 'Not recorded'
    mapping = PRIORITY_LABELS if kind == 'priority' else SECURITY_LABELS if kind == 'security' else TRANSACTION_LABELS if kind == 'transaction' else STATUS_LABELS
    if isinstance(value,str) and value.casefold() in mapping:return mapping[value.casefold()]
    # Unknown taxonomy must never be promoted to an invented creditor ranking.
    return 'Ranking not recognised — see details' if kind == 'priority' else 'Classification not recognised — see details'


def amount(value):
    """Group digits without rounding, changing signs or stripping recorded decimals."""
    if value is None or isinstance(value,bool):return 'Not recorded'
    try:
        number = Decimal(str(value))
        return format(number, ',f') if number.is_finite() else 'Not recorded'
    except (InvalidOperation, ValueError):
        return str(value)  # Non-numeric source wording is preserved, not interpreted.


def notice(value):
    if not isinstance(value,str):return value
    if value == 'Validator 7 used a saved/offline reviewer response; this execution does not verify live reviewer model performance.':
        return 'Review used a saved offline response; live reviewer performance was not verified.'
    if value.startswith('Missing designated content: '):
        path=value.removeprefix('Missing designated content: ')
        names={'module_conclusions.M3.m3_rebuild.structure.artifact':'Corporate structure',
            'module_conclusions.M3.m3_rebuild.management.artifact':'Management assessment',
            'module_conclusions.M4.m4_analysis.deliverable_1':'Debt obligations',
            'module_conclusions.M4.m4_analysis.deliverable_2':'Refinancing history',
            'module_conclusions.M4.m4_analysis.deliverable_4':'Credit conclusion',
            'module_conclusions.M2.findings':'Industry analysis'}
        return names.get(path,'Required source content')+' is not available for this run. See Audit & Review for details.'
    prefix,separator,text=value.partition(':')
    return text.lstrip() if separator and prefix in NOTICE_PREFIXES else value


def audit_url(bo, job=None, evidence_id=None):
    """Only create anchors supported by the exact selected run's existing audit page."""
    run,case=bo['analysis_run_id'],bo['case_id']
    if job:
        ids=(job.get('run_ids') or {}).get('bo') or (((job.get('result') or {}).get('bo') or {}).get('summary') or {}).get('analysis_run_id')
        if job.get('case_id') == case and ids == run:
            href='/analysis/'+quote(job['job_id'],safe='')+'/audit'
            if evidence_id:
                from app.services.analysis_workspace import anchor
                href+='#'+anchor('evidence',evidence_id)
            return href
    return '/cases/'+quote(case,safe='')+'/bo/runs/'+quote(run,safe='')+'/audit.html'


def configure(env):
    from app.services.analysis_workspace import safe_url
    env.filters.update(bo_amount=amount,bo_classification=classification,bo_notice=notice,bo_safe_url=safe_url)
    env.globals.update(bo_audit_url=audit_url,bo_debt_summary_fields=DEBT_SUMMARY_FIELDS)
