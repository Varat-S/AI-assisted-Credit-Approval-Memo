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
from app.services.bo.management_view import management_view
from app.services.bo.handoff import read_handoff
from app.services.bo.workbench import bo_artifact, BoRunNotFoundError
from app.services.pipeline.artifacts import ArtifactIntegrityError

_env = Environment(loader=FileSystemLoader(str(Path(__file__).parents[2] / 'api' / 'templates')), autoescape=True)

NOTE_COLUMNS = [('senior_note_series', 'Senior note / series'), ('legal_borrower', 'Legal borrower'),
                ('principal_amount_m', 'Principal (US$ m)'), ('coupon_interest_rate', 'Coupon / rate'),
                ('maturity_year', 'Maturity'), ('collateral_security_status', 'Security'),
                ('guarantors_credit_support', 'Guarantors / credit support'), ('priority_ranking_tier', 'Priority tier')]
FACILITY_COLUMNS = [('obligation_facility', 'Obligation / facility'), ('legal_borrower', 'Legal borrower'),
                    ('principal_drawn_m', 'Drawn (US$ m)'), ('available_facility_limit_m', 'Undrawn availability (US$ m)'),
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
        block['evidence']['notices'] = list(block.get('visible_warnings', []))
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
        block['evidence']['notices'] = list(block.get('visible_warnings', []))
    from app.services.bo.industry_view import group_findings
    industry = group_findings((sections[3].get('content') or {}).get('findings', []))
    for entry in [entry for group in industry['groups'] for entry in group['findings']] + industry['exposures']:
        finding = entry['finding']
        entry['evidence'] = add(entry['title'], finding, claim=finding, source=sections[3]['source_ref'])
        entry['evidence']['assessment'] = {
            'specialist_interpretation': list((finding.get('interpretation') or {}).values()),
            'gaps': finding.get('missing_information') or [],
            'finding': {'label': (finding.get('claim_type') or 'inference').replace('_', ' ').title(),
                        'support': (finding.get('disposition') or 'Recorded').title(),
                        'reason': 'Selected-run industry finding reviewed by Validator 6.',
                        'support_reason': 'Supporting quotations are limited to this finding’s saved evidence.'},
            'scope_note': 'Recorded industry analysis; no new assessment is performed when opening this page.'}
    from app.services.bo.business_model import load_description
    business_model = load_description(session, analysis_run_id, saved)
    if business_model and business_model['status'] == 'complete':
        for paragraph in business_model['paragraphs']:
            ids = list(dict.fromkeys(citation['evidence_id'] for sentence in paragraph['sentences']
                                      for citation in sentence['evidence']))
            paragraph['evidence_panel'] = add('Business Model', deepcopy(paragraph),
                                             claim={'evidence_ids': ids})
    management = management_view(sections[1].get('content'), documents=documents, passages=passages,
                                 warnings=sections[1].get('visible_warnings', []))
    if management:
        # Project each selected item's saved citations through the same evidence
        # pipeline as Competitive Position; never substitute another finding's sources.
        collections = [g['findings'] for g in management['finding_groups']]
        collections += [management['executive_profiles'], management['reviewed_observations']]
        for collection in collections:
            for entry in collection:
                selected = [management['citations'][cid] for cid in entry.get('citation_ids', [])
                            if cid in management['citations']]
                quotes = []
                for citation in selected:
                    doc = documents.get(citation.get('document_id'), {})
                    passage = passages.get(citation.get('source_id'), {})
                    if (doc and passage and doc.get('sha256') == citation.get('source_sha256')
                            and doc.get('document_id') == passage.get('document_id')):
                        quotes.append({**citation, 'evidence_id': citation['source_id']})
                title = entry.get('name') or 'Management Finding'
                panel = add(title, {'citations': quotes},
                            claim={'evidence_ids': list(dict.fromkeys(c['evidence_id'] for c in quotes))},
                            source=sections[1]['source_ref'])
                panel['reviewed_record'] = deepcopy(entry)
                panel['assessment'] = {
                    'specialist_interpretation': [entry.get('text') or
                        (entry.get('name', '') + ' · ' + entry.get('position', ''))],
                    'gaps': entry.get('limitations', entry.get('uncertainties', [])),
                    'finding': {'label': 'Reviewed Management Finding',
                                'support': (entry.get('review_status') or entry.get('review_outcome') or 'Recorded').title(),
                                'reason': entry.get('review_reason') or 'See the saved reviewed statement above.',
                                'support_reason': 'The quotations shown are limited to this record’s saved citations.'},
                    'scope_note': 'Saved management review; no new assessment was performed.'}
                entry['evidence'] = panel
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
    from app.services.bo.debt_snapshot import build_snapshot, annotate_svg, format_date
    structure = sections[0]['structure']['content']
    snapshot = build_snapshot(structure, sections[0]['debt_obligations']['content'])
    snapshot_placed = False
    if snapshot:
        snapshot['as_of'] = artifact['identity']['as_of_date']
        snapshot['display_date'] = format_date(snapshot['as_of'])
        sections[0]['debt_obligations']['evidence']['snapshot_metadata'] = {
            'entity': snapshot['entity'], 'diagram_entity': snapshot['borrower']['display_name'],
            'mapping': snapshot['note'], 'scope': snapshot['scope_note'],
            'capacity_note': 'Undrawn availability is capacity, not additional debt.',
            'excluded_obligation_rows': snapshot['excluded_count']}
    if structure:
        from app.services.bo.m3_rebuild.structure import render_svg
        # Both deterministic SVG renderers escape source strings; no source SVG is trusted.
        rendered, snapshot_placed = annotate_svg(render_svg(structure, show_title=False), structure, snapshot)
        svg = Markup(rendered)
    from urllib.parse import quote
    from app.services.bo.evidence_presentation import source_index, quotation_cards
    selected_ids = {hid for entry in claims for hid in entry['claim'].get('hypothesis_ids', [])}
    sections[2]['evidence']['hypotheses'] = [hypotheses[hid] for hid in sorted(selected_ids) if hid in hypotheses]
    indexes = {did: source_index(session, doc, row.case_id) for did, doc in documents.items()}
    source_base = '/cases/' + quote(row.case_id, safe='') + '/bo/runs/' + quote(analysis_run_id, safe='') + '/source'
    for item in evidence:
        item['quotations'] = quotation_cards(item, passages, documents, indexes, source_base)
    if finding_groups is not None:
        from app.services.bo.finding_assessment import assessment
        by_id = {item['id']: item for item in evidence}
        for group in finding_groups:
            for entry in group['entries']:
                entry['evidence'] = by_id[entry['evidence']['id']]
                entry['assessment'] = assessment(hypotheses[entry['source_hypothesis_id']], entry['pointers'],
                    entry['claim'].get('uncertainty'), verified_quotes=entry['evidence']['quotations'])
                entry['pointers'][0]['classification'] = entry['assessment']['finding']
                entry['pointers'][1]['classification'] = entry['assessment']['implication']
                entry['evidence']['assessment'] = entry['assessment']
    from app.services.bo.roster_v3 import V3_AGENT_6_ID
    # The PDF export leaves out Agent 6's cross-dimensional insights and their evidence.
    cross_dimensional = {entry['evidence']['id'] for group in finding_groups or [] for entry in group['entries']
                         if entry['source_agent_id'] == V3_AGENT_6_ID}
    return {'memo': artifact, 'business_model': business_model, 'svg': svg, 'debt_snapshot': snapshot, 'snapshot_placed': snapshot_placed,
            'claims': claims, 'finding_groups': finding_groups, 'evidence': evidence,
            'cross_dimensional': cross_dimensional,
            'management': management, 'industry': industry,
            'structure_tree': next(iter(structure['companies'].values()))['plain_text_tree'] if structure else None,
            'review': public_record({'status': row.human_review_status,
                                      'reviewer': row.payload.get('reviewer'), 'reviewed_at': row.payload.get('reviewed_at')}),
            'note_columns': NOTE_COLUMNS, 'facility_columns': FACILITY_COLUMNS,
            'priority_columns': PRIORITY_COLUMNS, 'display': display, 'warning_text': warning_text}


def render_page(view, *, pdf=False):
    return _env.get_template('bo_four_section_page.html.j2').render(bo4=view, pdf=pdf)
