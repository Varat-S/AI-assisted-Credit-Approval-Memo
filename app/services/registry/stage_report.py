"""Versioned read-only presentation of one artifact. No analytical calculation."""
from __future__ import annotations
from app.services.analysis_workspace import anchor, safe_url

CONTRACT_VERSION = 'pipeline-node-details-2.0'


def states(entry, payload=None):
    """Legacy manifest status conflates execution, validation and governance."""
    doc = payload if isinstance(payload, dict) else {}
    agent = doc.get('agent') or doc.get('validation') or {}
    agent = agent if isinstance(agent, dict) else {}
    explicit = str(doc.get('execution_status') or agent.get('execution_status') or '').lower()
    legacy = entry.status.value
    execution = explicit if explicit in {'completed', 'running', 'failed', 'skipped', 'absent'} else {
        'absent': 'absent', 'skipped': 'skipped', 'error': 'failed',
    }.get(legacy, 'completed' if entry.file_location else 'absent')
    if agent.get('status') in {'failed', 'error', 'running'}:
        execution = agent['status'] if agent['status'] != 'error' else 'failed'
    if any(run.get('error_state') for run in agent.get('runs', []) if isinstance(run, dict)):
        execution = 'failed'
    validation = str(entry.validation_status or '').lower()
    if validation in {'valid', 'validated', 'passed', 'pass'}: validation = 'passed'
    elif validation in {'failed', 'fail', 'rejected', 'invalid'}: validation = 'failed'
    elif validation in {'qualified', 'accepted_with_qualification'}: validation = 'qualified'
    else: validation = 'unavailable'
    if doc.get('passed') is True: validation = 'passed'
    elif doc.get('passed') is False: validation = 'failed'
    review = entry.human_review_status.value
    governance = {'accepted': 'accepted', 'rejected': 'rejected', 'pending': 'pending',
                  'escalated': 'pending'}.get(review, 'not_applicable')
    return dict(execution=execution, validation=validation, governance=governance,
                completeness='partial' if legacy == 'incomplete' else legacy, review_status=review)


SECTIONS = {
    'specialist': [('hypotheses', 'Analytical findings'), ('parameters', 'Supporting measures and factors'),
                   ('agent', 'Execution and qualifications')],
    'structure': [('companies', 'Corporate structure and entity relationships'),
                  ('source', 'Source and simulation provenance'), ('provenance', 'Provenance'),
                  ('limitations', 'Limitations')],
    'management': [('overall_assessment', 'Management credit assessment'),
                   ('key_strengths', 'Supporting management findings'), ('key_concerns', 'Management concerns'),
                   ('qualifications', 'Qualifications and limitations'), ('executive_profiles', 'Executive continuity'),
                   ('summary', 'Management findings'), ('credit_assessment', 'Management credit assessment'),
                   ('management_assessment', 'Management findings'), ('executives', 'Executive continuity'),
                   ('findings', 'Findings'), ('limitations', 'Limitations')],
    'debt': [('summary', 'Debt and refinancing assessment'), ('debt_obligations', 'Debt schedules'),
             ('deliverable_1', 'Debt schedules and creditor priority'),
             ('deliverable_2', 'Refinancing analysis'), ('deliverable_3', 'Capital allocation'),
             ('deliverable_4', 'Recorded credit synthesis'),
             ('senior_notes', 'Senior notes'), ('facilities', 'Facilities'),
             ('creditor_priority', 'Creditor priority'), ('refinancing_analysis', 'Refinancing analysis'),
             ('validator_report', 'Validation checks')],
    'financial': [('composite', 'Provisional financial score'), ('metrics', 'Financial measures and calculations'),
                  ('precheck', 'Pre-checks'), ('triggers', 'Triggers'), ('escalations', 'Escalations')],
    'validator': [('validation', 'Checks and affected findings'), ('checks', 'Checks performed'),
                  ('issues', 'Failures and qualifications'), ('validation_issues', 'Validation issues')],
    'challenger': [('challenge', 'Challenges, disagreements and resolutions'),
                   ('unresolved_items', 'Unresolved challenges'), ('rejected_items', 'Rejected items')],
    'synthesis': [('synthesis', 'Cross-module synthesis'), ('conclusion', 'Recorded conclusion'),
                  ('overall_assessment', 'Overall assessment'), ('strengths', 'Supporting factors'),
                  ('weaknesses', 'Vulnerabilities'), ('unresolved_challenges', 'Unresolved challenges')],
    'rms': [('verdict', 'Provisional recommendation'), ('grade', 'Risk grade'),
            ('capacity', 'Debt capacity and supporting calculations'), ('request', 'Proposed terms'),
            ('gates', 'Blocking gates'), ('warnings', 'Gate warnings and recorded waivers'),
            ('fo_decisions', 'Recorded financial decisions'), ('sources', 'Exact source bindings')],
    'final': [('sections', 'Memo sections'), ('governance', 'Governance and completeness'),
              ('final_conclusion', 'Final synthesis'), ('canonical_references', 'Bound reports')],
}


def family(info):
    producer, aid = info['producer'], info['artifact_id']
    if producer.get('module') == 'RMS': return 'rms'
    if producer.get('validator') or info['artifact_type'] == 'validation_report': return 'validator'
    if 'challenger' in aid: return 'challenger'
    if 'synthesis' in aid: return 'synthesis'
    if producer.get('agent') == 'm3_structure_conversion': return 'structure'
    if producer.get('agent') == 'm3_management_assessment': return 'management'
    if 'm4_debt' in aid: return 'debt'
    if producer.get('module') == 'FO': return 'financial'
    if info['artifact_type'] == 'agent_output': return 'specialist'
    if info['artifact_type'] in {'memo', 'handoff'} or 'governance' in aid: return 'final'
    return 'generic'


def humanize(key):
    return str(key).replace('_', ' ').replace('.', ' · ').strip().capitalize()


def presentation(info):
    payload = info.get('payload')
    doc = payload if isinstance(payload, dict) else {}
    component = doc.get('artifact')
    report_doc = component if isinstance(component, dict) else doc
    kind = family(info)
    # Existing memo presentation policy preserves reviewed management wording.
    if kind == 'management' and report_doc.get('schema_version') == 'm3-management-assessment-3.0':
        from app.services.bo.management_view import management_view
        view = management_view(report_doc)
        report_doc = {**report_doc, **{key: view[key] for key in
            ['overall_assessment', 'key_strengths', 'key_concerns', 'qualifications', 'executive_profiles']}}
    if kind == 'debt' and isinstance(doc.get('assessment'), dict):
        report_doc = {**doc, **doc['assessment']}
    sections, used = [], set()
    for key, title in SECTIONS.get(kind, []):
        if key in report_doc:
            sections.append(dict(key=key, title=title, value=report_doc[key])); used.add(key)
    rest = {k: v for k, v in report_doc.items() if k not in used}
    if not used and rest:
        kind = 'generic'
    if rest: sections.append(dict(key='recorded_details', title='Recorded details', value=rest))
    if not isinstance(payload, dict) and payload is not None:
        sections.append(dict(key='recorded_output', title='Recorded output', value=payload))
    evidence, signals, disclosures = [], [], []
    seen_evidence, seen_signals, seen_disclosures = set(), set(), set()
    signal_keys = {'validation', 'validator_report', 'validation_issues', 'validator_adjustments',
                   'unresolved_challenges', 'unresolved_contradictions', 'rejected_items',
                   'limitations', 'uncertainties', 'missing_information', 'escalations',
                   'gates', 'warnings', 'review', 'review_reason', 'reviewer', 'reviewed_at',
                   'human_review_status', 'fo_decisions', 'requires_human_review', 'challenge',
                   'review_outcome', 'review_status', 'unproven_mitigants'}
    def walk(value, path=''):
        if isinstance(value, dict):
            eid = value.get('evidence_id') or value.get('source_id') or value.get('citation_id')
            if eid and str(eid) not in seen_evidence:
                seen_evidence.add(str(eid))
                evidence.append(dict(id=str(eid), anchor=anchor('evidence', eid), record=value, records=[value],
                                     href=safe_url(value.get('source_url') or value.get('url'))))
            elif eid:
                item = next(e for e in evidence if e['id'] == str(eid))
                if value not in item['records']:
                    item['records'].append(value)
                item['href'] = item['href'] or safe_url(value.get('source_url') or value.get('url'))
            for key, item in value.items():
                location = path + '/' + str(key)
                if key in signal_keys and item not in (None, [], {}):
                    fingerprint = repr(item)
                    if fingerprint not in seen_signals:
                        seen_signals.add(fingerprint)
                        signals.append(dict(title=humanize(key), path=location, value=item))
                if key in {'data_status', 'simulation_notice', 'simulation_provenance', 'synthetic',
                           'simulated', 'is_synthetic', 'is_simulated', 'mode', 'model_invoked'}:
                    disclosure = f'{humanize(key)}: {item}'
                    if disclosure not in seen_disclosures:
                        disclosures.append(disclosure); seen_disclosures.add(disclosure)
                walk(item, location)
        elif isinstance(value, list):
            for index, item in enumerate(value): walk(item, path + '/' + str(index))
    walk(info.get('source_disclosures') or {})
    walk(payload)
    for eid in info.get('evidence_ids', []):
        if eid not in seen_evidence:
            evidence.append(dict(id=eid, anchor=anchor('evidence', eid), record=None, records=[], href=None))
    if not disclosures:
        disclosures.append('Data origin and simulation status are not recorded in this artifact; verification is not inferred.')
    schema = str(info.get('schema_name') or info.get('schema_version') or doc.get('schema_version') or '')
    return dict(contract_version=CONTRACT_VERSION, family=kind, sections=sections,
                evidence=evidence, signals=signals, disclosures=disclosures,
                schema=schema or 'Not recorded',
                rendering_note=('Generic presentation of an unknown or historical schema. All recorded fields remain available.'
                                if kind == 'generic' else 'Presentation of persisted fields; no analytical recalculation.'))
