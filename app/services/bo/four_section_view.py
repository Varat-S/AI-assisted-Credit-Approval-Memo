"""Read-only presentation of the bound four-section artifact; no analytical work."""
from copy import deepcopy
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from sqlalchemy import select

from app.models.orm import AcceptedBusinessOverviewRow
from app.services.analysis_audit import public_record
from app.services.analysis_workspace import safe_url
from app.services.bo.four_section import load_saved_inputs
from app.services.bo.handoff import read_handoff
from app.services.bo.workbench import bo_artifact, BoRunNotFoundError
from app.services.pipeline.artifacts import ArtifactIntegrityError

_env = Environment(loader=FileSystemLoader(str(Path(__file__).parents[2] / 'api' / 'templates')), autoescape=True)

NOTE_COLUMNS = [('senior_note_series', 'Senior note / series'), ('legal_borrower', 'Legal borrower'),
                ('principal_amount_m', 'Principal (US$ m)'), ('coupon_interest_rate', 'Coupon / rate'),
                ('maturity_year', 'Maturity'), ('collateral_security_status', 'Security'),
                ('guarantors_credit_support', 'Guarantors / credit support'), ('priority_ranking_tier', 'Priority tier')]
FACILITY_COLUMNS = [('obligation_facility', 'Obligation / facility'), ('legal_borrower', 'Legal borrower'),
                    ('principal_drawn_m', 'Drawn (US$ m)'), ('available_facility_limit_m', 'Facility limit (US$ m)'),
                    ('interest_rate_terms', 'Interest terms'), ('maturity', 'Maturity'),
                    ('collateral_security_status', 'Security'), ('guarantors_credit_support', 'Guarantors / credit support'),
                    ('priority_ranking_tier', 'Priority tier')]
PRIORITY_COLUMNS = [('tier_1_direct_opco_secured_m', 'Direct operating company secured (US$ m)'),
                    ('tier_2_senior_unsecured_guaranteed_m', 'Senior unsecured guaranteed (US$ m)'),
                    ('tier_3_unguaranteed_holdco_m', 'Unguaranteed holding company (US$ m)'),
                    ('consolidated_total_indebtedness_m', 'Consolidated indebtedness (US$ m)'),
                    ('structural_subordination_drag_ratio', 'Structural subordination drag ratio'),
                    ('prospective_loan_secured_placement', 'Prospective secured loan placement'),
                    ('prospective_loan_senior_unsecured_placement', 'Prospective unsecured loan placement')]
LABELS = {'tier_1_direct_opco_secured': 'Tier 1 · Direct operating company secured',
          'tier_2_senior_unsecured_guaranteed': 'Tier 2 · Senior unsecured guaranteed',
          'tier_3_unguaranteed_holdco': 'Tier 3 · Unguaranteed holding company',
          'secured': 'Secured', 'unsecured': 'Unsecured'}


def display(value):
    if value is None:
        return 'Not recorded'
    if isinstance(value, str):
        return LABELS.get(value, value)
    return value


def load_view(session, analysis_run_id, case_id=None):
    """None means legacy absence; a present but invalid binding never falls back."""
    rows = list(session.scalars(select(AcceptedBusinessOverviewRow).where(
        AcceptedBusinessOverviewRow.analysis_run_id == analysis_run_id)))
    if not rows:
        raise BoRunNotFoundError('No handoff for the selected Business Overview run.')
    if len(rows) != 1:
        raise ArtifactIntegrityError('Selected Business Overview handoff is ambiguous.')
    row = rows[0]
    handoff = read_handoff(session, row.handoff_id)
    if case_id is not None and row.case_id != case_id:
        raise BoRunNotFoundError('Business Overview run does not belong to this case.')
    if 'four_section_memo' not in handoff.canonical_references:
        return None
    memo = bo_artifact(session, analysis_run_id, kind='four_section')
    saved = load_saved_inputs(session, analysis_run_id)
    # Display copies alone are redacted. Canonical objects/hashes stay untouched.
    artifact = public_record(deepcopy(memo))
    documents = {d['document_id']: d for d in saved.snapshot.get('documents', [])}
    passages = {p['evidence_id']: p for p in saved.snapshot.get('narrative_evidence', [])}
    hypotheses = {h['hypothesis_id']: h for h in saved.audit['hypotheses']['records']}
    parameters = {p.get('parameter_result_id'): p for p in saved.audit.get('parameters', [])}
    sources = {r['artifact_id']: r for r in artifact['sources']}
    evidence = []

    def warning_text(text):
        # Source-reference prefixes are evidence metadata, not analytical text.
        # The exact warning and canonical enum remain in the saved JSON/evidence.
        for hid in hypotheses:
            if text.startswith(hid + ': '):
                text = text[len(hid) + 2:]
                break
        return text.replace('qualified_narrative', 'qualified narrative')

    def add(title, content, *, claim=None, source=None):
        citations = []
        evidence_ids = (claim or {}).get('evidence_ids', [])
        if source == 'debt':
            evidence_ids = (saved.audit.get('module_conclusions', {}).get('M4', {})
                            .get('m4_debt_assessment') or {}).get('evidence_ids', [])
        for eid in evidence_ids:
            passage = passages.get(eid)
            if passage:
                doc = documents.get(passage.get('document_id'), {})
                citations.append(public_record({'evidence_id': eid, 'passage': passage, 'document': doc,
                                                'href': safe_url(doc.get('source_url'))}))
        item = public_record({'title': title, 'content': content, 'source': sources.get(source),
                              'claim': claim, 'citations': citations,
                              'hypotheses': [hypotheses[hid] for hid in (claim or {}).get('hypothesis_ids', []) if hid in hypotheses],
                              'parameters': [parameters[pid] for pid in (claim or {}).get('parameter_result_ids', []) if pid in parameters]})
        parameter_ids = set((claim or {}).get('parameter_result_ids', []))
        for hypothesis in item['hypotheses']:
            parameter_ids.update(hypothesis.get('parameter_result_ids', []))
        item['calculation_traces'] = public_record([c for c in saved.audit.get('calculations', [])
                                                    if c.get('parameter_result_id') in parameter_ids])
        if source == 'debt':
            item['validation'] = public_record((saved.audit.get('module_conclusions', {}).get('M4', {})
                .get('m4_debt_assessment') or {}).get('validator_report'))
        if source == 'structure':
            doc_id = ((saved.provenance.get('m3_packet') or {}).get('context') or {}).get('corporate_document_id')
            item['submitted_source'] = public_record([s for s in saved.snapshot.get('structured_evidence', [])
                                                       if s.get('document_id') == doc_id])
        item['id'] = 'bo-evidence-' + str(len(evidence) + 1)
        evidence.append(item)
        return item

    sections = artifact['sections']
    for key, title in [('structure', 'Corporate Structure'), ('debt_obligations', 'Debt Obligations')]:
        block = sections[0][key]
        block['evidence'] = add(title, block['content'], source=block['source_ref'])
    for index in (1, 2, 3):
        block = sections[index]
        details = {'artifact': block['content']}
        if index == 2:
            details.update(editorial_selection=block['editorial_selection'],
                           selection_source=sources.get(block['selection_source_ref']),
                           challenge_source=sources.get(block['challenge_source_ref']),
                           independent_challenge=(saved.audit.get('challenger', {}).get('rounds') or [])[-1:])
        if index == 3:
            details['recorded_module_status'] = saved.audit.get('module_conclusions', {}).get('M2', {})
        block['evidence'] = add(block['title'], details, source=block['source_ref'])
    cp = sections[2]['content'] or {}
    claims = []
    for category, group in [('Assessment', [cp.get('overall_assessment')]),
                            ('Business driver', cp.get('key_drivers', [])), ('Material risk', cp.get('material_risks', []))]:
        for claim in group:
            if claim:
                claims.append({'category': category, 'claim': claim,
                               'evidence': add(category, None, claim=claim, source=sections[2]['source_ref'])})
    finding_groups = None
    selection = sections[2].get('editorial_selection') or {}
    if selection.get('schema_version') in {'bo-source-selection-output-1.0.0', 'bo-source-selection-output-1.1.0'}:
        from app.services.bo.competitive_presentation import grouped_findings
        finding_groups = grouped_findings(claims, saved.audit, saved.provenance)
        titles = {entry['evidence']['id']: entry['topic'] for group in finding_groups for entry in group['entries']}
        for item in evidence:
            if item['id'] in titles:
                item['title'] = titles[item['id']]
    svg = None
    structure = sections[0]['structure']['content']
    if structure:
        from app.services.bo.m3_rebuild.structure import render_svg
        # Only the existing deterministic, escaping SVG generator supplies Markup.
        svg = Markup(render_svg(structure, show_title=False))
    return {'memo': artifact, 'svg': svg, 'claims': claims, 'finding_groups': finding_groups, 'evidence': evidence,
            'structure_tree': next(iter(structure['companies'].values()))['plain_text_tree'] if structure else None,
            'review': public_record({'status': row.human_review_status,
                                      'reviewer': row.payload.get('reviewer'), 'reviewed_at': row.payload.get('reviewed_at')}),
            'note_columns': NOTE_COLUMNS, 'facility_columns': FACILITY_COLUMNS,
            'priority_columns': PRIORITY_COLUMNS, 'display': display, 'warning_text': warning_text}


def render_page(view, *, pdf=False):
    return _env.get_template('bo_four_section_page.html.j2').render(bo4=view, pdf=pdf)
