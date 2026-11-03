"""Read-only management presentation; never rewrites an analytical judgment."""
from copy import deepcopy
import re


CATEGORIES = (
    ('financial_stewardship', 'Financial Stewardship', 'Critical'),
    ('operational_execution', 'Operational Execution Capability', 'High'),
    ('governance_integrity', 'Governance and Integrity', 'High'),
    ('leadership_stability', 'Leadership Stability and Succession', 'Medium'),
    ('relevant_expertise', 'Relevant Expertise', 'Supporting'),
)
DIRECTION_LABELS = {'positive': 'Supporting Factor', 'negative': 'Credit Concern',
                    'mixed': 'Mixed Finding', 'neutral': 'Context', 'unavailable': 'Unassessed'}


def _key(text):
    return ' '.join(text.split())


def _unique(texts):
    result = {}
    for text in texts:
        if text and text.strip():
            result.setdefault(_key(text), text)
    return list(result.values())


def _processing_note(text):
    """Narrow display rules for recorded processing notices, not credit inference.

    Unknown limitations remain visible. These phrases describe provenance or
    citation processing; all originals remain in supporting records.
    """
    return (bool(re.fullmatch(r'Company and fiscal period were confirmed from the admitted SEC filing metadata '
                             r'\(form [\w-]+, CIK \d+\), not from cover-page text\. '
                             r'HTML passages have no pages; citations give page 1 and the passage offset\.', text))
            or text == 'Qualified or withheld judgments are identified individually in the review record.'
            or text == ('Educational structure is not a verified legal/obligor assessment. '
                        'Management observations are bounded continuity rules, not competence/governance ratings.')
            or bool(re.fullmatch(r'\d+ individual evidence claims are unsupported; other supported claims remain usable\.', text))
            or bool(re.fullmatch(r'Fact-level assessments of .+ were rejected due to citation failure or ambiguity\.', text))
            or bool(re.fullmatch(r'Supporting fact statements \([^)]+\) were rejected for paraphrasing canonical content\.', text)))


def _source_references(artifact, citations, documents, passages):
    """Use only matching same-run document metadata; hashes remain internal."""
    locations, by_citation = {}, {}
    for cid, citation in citations.items():
        document = documents.get(citation.get('document_id'), {})
        if document.get('sha256') != citation.get('source_sha256'):
            document = {}
        passage = passages.get(citation.get('source_id'), {})
        if not document or passage.get('document_id') != document.get('document_id'):
            passage = {}
        filename = document.get('filename', '')
        html = (document.get('parser') in ('inline_xbrl', 'sec_companion')
                or filename.lower().endswith(('.html', '.htm'))
                or artifact.get('source', {}).get('path', '').startswith(('sec-inline-xbrl:', 'sec-proxy:')))
        pdf = not html and (document.get('parser') in ('pdf_text', 'pdf_table')
                            or filename.lower().endswith('.pdf')
                            or citation.get('source_id', '').startswith('pdf:p'))
        label = 'Recorded management source'
        if document:
            label = artifact.get('company') or filename or label
            if document.get('form'):
                label += ' · Form ' + document['form']
            if document.get('report_date'):
                label += ' · ' + str(document['report_date'])
            if not document.get('form') and filename:
                label = filename
        offset = citation.get('passage_offset', passage.get('location'))
        page = citation.get('physical_page') if pdf else None
        locator = (f'Passage offset {offset}' if html and offset is not None
                   else f'Page {page}' if page is not None else 'Recorded passage')
        # Different quotes on one canonical passage remain separately recorded,
        # but the primary citation identifies that location only once.
        identity = (citation.get('source_sha256'), citation.get('document_id'),
                    citation.get('source_id'), offset if html else page)
        if identity not in locations:
            locations[identity] = {'number': len(locations) + 1, 'label': label, 'locator': locator,
                                   'citation_ids': [], 'anchor': 'bo-management-citation-' + cid.replace(':', '-'),
                                   'source_id': citation.get('source_id'), 'source_sha256': citation.get('source_sha256')}
        reference = locations[identity]
        reference['citation_ids'].append(cid)
        by_citation[cid] = reference
    return by_citation


def management_view(artifact, *, documents=None, passages=None, warnings=()):
    if not artifact:
        return None
    citations = {c['citation_id']: c for c in artifact.get('citations', [])}
    citation_views = _source_references(artifact, citations, documents or {}, passages or {})

    def references(ids):
        selected = {}
        for cid in ids:
            if cid not in citation_views:
                continue
            reference = citation_views[cid]
            if reference['number'] not in selected:
                selected[reference['number']] = {**reference, 'citation_ids': [],
                    'anchor': 'bo-management-citation-' + cid.replace(':', '-')}
            target = selected[reference['number']]
            if cid not in target['citation_ids']:
                target['citation_ids'].append(cid)
        return list(selected.values())

    validation = artifact.get('validation', {})
    review = validation.get('validator_7', {})
    corrections = validation.get('explicit_review_corrections') or {}
    effective_overall = corrections.get('corrected_overall') or review.get('overall', {})
    judgments = {j['judgment_id']: j for j in validation.get('judgment_results', [])}
    categories = [{'id': key, 'title': title, 'priority': priority,
                   'status': 'insufficient_evidence', 'review_status': None, 'findings': []}
                  for key, title, priority in CATEGORIES]
    gaps, uncategorized, findings, seen = [], [], [], {}
    qualifications = {}
    technical_notes, methodology = [], []

    def qualify(text, origin, observation_ids=()):
        if not text or not text.strip():
            return
        entry = qualifications.setdefault(_key(text), {'text': text, 'origins': [], 'observation_ids': []})
        entry['origins'] = list(dict.fromkeys(entry['origins'] + [origin]))
        entry['observation_ids'] = list(dict.fromkeys(entry['observation_ids'] + list(observation_ids)))

    model = artifact.get('model_assessment', {})
    overall_limits = _unique(effective_overall.get('limitations', []) + model.get('uncertainties', [])
                             + model.get('missing_information', []))
    for text in overall_limits:
        qualify(text, 'overall')
    for observation in artifact.get('observations', []):
        if observation.get('review_outcome') not in ('accepted', 'qualified'):
            continue
        ids = observation.get('citation_ids', [])
        if not ids or any(cid not in citations for cid in ids):
            continue
        oid = observation.get('observation_id')
        reason = observation.get('review_reason')
        limits = _unique(([reason] if observation['review_outcome'] == 'qualified' else [])
                         + observation.get('uncertainties', []))
        finding = {'text': observation.get('text', ''), 'direction': observation.get('direction'),
                   'direction_label': DIRECTION_LABELS.get(observation.get('direction'), 'Unassessed'),
                   'review_status': observation['review_outcome'], 'limitations': limits,
                   'observation_ids': [oid], 'citation_ids': list(ids), 'references': references(ids)}
        # Evidence-basis restrictions are shown explicitly but the internal fact
        # IDs and detailed rejection rationale stay in the supporting record.
        result = judgments.get(oid, {})
        if reason and observation['review_outcome'] == 'qualified':
            if (result.get('removed_fact_ids') and any(fid in reason for fid in result['removed_fact_ids'])
                    and re.fullmatch(r'The supporting facts [\w ,]+ were rejected for paraphrasing; '
                                     r'[\w ]+ is instead supported by appointment and role claim IDs\.', reason)):
                qualify('Some submitted supporting evidence was rejected; this finding uses the surviving reviewed evidence.',
                        'review_basis', [oid])
                technical_notes.append(reason)
            else:
                qualify(reason, 'review_reason', [oid])
        for text in observation.get('uncertainties', []):
            qualify(text, 'observation_uncertainty', [oid])
        key = (finding['text'], finding['direction'], finding['review_status'], tuple(_key(t) for t in limits), observation.get('category'))
        if key in seen:
            existing = seen[key]
            existing['observation_ids'].append(oid)
            existing['citation_ids'] = list(dict.fromkeys(existing['citation_ids'] + ids))
            existing['references'] = references(existing['citation_ids'])
            continue
        seen[key] = finding
        findings.append(finding)
        if observation.get('category') == 'information_gap':
            gaps.append(finding)
        elif observation.get('category') in ('transition', 'integration', 'continuity') and finding['direction'] in DIRECTION_LABELS:
            categories[3]['findings'].append(finding)
        else:
            uncategorized.append(finding)

    for category in categories:
        directions = {f['direction'] for f in category['findings']}
        if directions:
            category['status'] = ('supporting_factor' if directions == {'positive'} else 'credit_concern' if directions == {'negative'}
                                  else 'context' if directions == {'neutral'} else 'mixed_or_uncertain')
            category['review_status'] = ('qualified' if any(f['review_status'] == 'qualified' for f in category['findings']) else 'accepted')

    for text in _unique(artifact.get('limitations', []) + list(warnings) + review.get('scope_limitations', [])):
        if text.startswith(('Validator 7 used a saved/offline reviewer response;', 'Offline fixture;')):
            methodology.append(text)
        elif _processing_note(text):
            technical_notes.append(text)
        else:
            qualify(text, 'recorded_limitation')
    withheld_claims = sum(c.get('outcome') == 'unsupported' for c in validation.get('claim_results', []))
    withheld_judgments = sum(j.get('outcome') == 'unsupported' for j in judgments.values())
    if withheld_claims or withheld_judgments:
        counts = ([f"{withheld_claims} evidence claim{'s' if withheld_claims != 1 else ''}"] if withheld_claims else [])
        counts += ([f"{withheld_judgments} judgment{'s' if withheld_judgments != 1 else ''}"] if withheld_judgments else [])
        qualify('Validation withheld ' + ' and '.join(counts) + '; only surviving reviewed findings are presented.',
                'validation_outcomes')

    groups = []
    for key, title in [('supporting_factors', 'Supporting Factors'), ('credit_concerns', 'Credit Concerns'),
                        ('mixed_uncertain', 'Mixed or Uncertain Findings'), ('information_gaps', 'Information Gaps')]:
        selected = [f for f in findings if (
            'supporting_factors' if f['direction'] == 'positive' else 'credit_concerns' if f['direction'] == 'negative'
            else 'information_gaps' if f in gaps else 'mixed_uncertain') == key]
        for finding in selected:
            finding['group_id'] = key
        groups.append({'id': key, 'title': title, 'findings': selected, 'print_findings': selected[:3],
                       'omitted_count': max(0, len(selected) - 3)})

    overall = artifact.get('overall_assessment') or {}
    eligible_ids = {oid for f in findings for oid in f['observation_ids']}
    refs_valid = validation.get('overall_references_valid', True) and set(effective_overall.get('judgment_ids', [])) <= eligible_ids
    reviewed_text = effective_overall.get('text') if refs_valid else None
    status = ('unavailable' if overall.get('outcome', 'unavailable') == 'unavailable' else 'qualified'
              if qualifications or overall.get('information_gaps') or artifact.get('completion_status') == 'partial'
              or any(f['review_status'] == 'qualified' for f in findings) else 'accepted')
    source_ids = [cid for g in groups for f in g['print_findings'] for cid in f['citation_ids']]
    source_ids += [cid for f in findings if set(f['observation_ids']) & set(effective_overall.get('judgment_ids', [])) for cid in f['citation_ids']]

    profiles = deepcopy(artifact.get('profiles', []))
    observations = deepcopy([o for o in artifact.get('observations', []) if o.get('review_outcome') in ('accepted', 'qualified')])
    for item in profiles + observations:
        item['references'] = references(item.get('citation_ids', []))
    return {'overall_assessment': {'text': reviewed_text or overall.get('policy') or 'Management assessment unavailable.',
                'wording_label': 'Reviewed assessment' if reviewed_text else 'Recorded assessment',
                'original_text': model.get('explanation') or overall.get('policy'), 'recorded_text': overall.get('policy'),
                'outcome': overall.get('outcome', 'unavailable'), 'status': status, 'limitations': overall_limits},
            'categories': categories, 'finding_groups': groups,
            'key_strengths': groups[0]['print_findings'], 'key_concerns': groups[1]['print_findings'],
            'additional_concerns': groups[1]['omitted_count'],
            'qualifications': list(qualifications.values()), 'methodology_notices': _unique(methodology),
            'technical_notes': _unique(technical_notes), 'handled_warnings': list(warnings),
            'assessment_gaps': [c for c in categories if not c['findings']], 'monitoring_priorities': [],
            'information_gaps': gaps, 'coverage_missing': list(artifact.get('coverage', {}).get('missing', [])),
            'uncategorized': uncategorized, 'uncategorized_concerns': [f for f in uncategorized if f['direction'] == 'negative'],
            'recorded_limitations': deepcopy(artifact.get('limitations', [])),
            'executive_profiles': profiles, 'reviewed_observations': observations,
            'citations': deepcopy(citations), 'citation_references': citation_views, 'sources': references(source_ids)}
