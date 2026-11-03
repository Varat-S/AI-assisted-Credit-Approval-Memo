"""Deterministic, read-only projection of the reviewed M3 artifact."""

from copy import deepcopy


CATEGORIES = (
    ('financial_stewardship', 'Financial Stewardship', 'Critical'),
    ('operational_execution', 'Operational Execution Capability', 'High'),
    ('governance_integrity', 'Governance and Integrity', 'High'),
    ('leadership_stability', 'Leadership Stability and Succession', 'Medium'),
    ('relevant_expertise', 'Relevant Expertise', 'Supporting'),
)


def management_view(artifact):
    """Project only surviving reviewed claims; never infer performance from a biography."""
    if not artifact:
        return None
    citations = {c['citation_id']: c for c in artifact.get('citations', [])}
    categories = [{'id': key, 'title': title, 'priority': priority,
                   'status': 'insufficient_evidence', 'findings': []}
                  for key, title, priority in CATEGORIES]
    by_id = {category['id']: category for category in categories}
    gaps = []
    uncategorized = []
    seen = {}
    for observation in artifact.get('observations', []):
        if observation.get('review_outcome') not in ('accepted', 'qualified'):
            continue
        ids = observation.get('citation_ids', [])
        if not ids or any(cid not in citations for cid in ids):
            continue
        category = observation.get('category')
        finding = {'text': observation.get('text', ''),
                   'direction': observation.get('direction'),
                   'review_status': observation['review_outcome'],
                   'limitations': list(dict.fromkeys(
                       ([observation.get('review_reason')] if observation['review_outcome'] == 'qualified' else [])
                       + observation.get('uncertainties', []))),
                   'observation_ids': [observation.get('observation_id')],
                   'citation_ids': list(ids)}
        finding['limitations'] = [x for x in finding['limitations'] if x]
        if category == 'information_gap':
            gaps.append(finding)
            continue
        target = by_id['leadership_stability'] if category in ('transition', 'integration', 'continuity') else None
        if target is None:
            uncategorized.append(finding)
            continue
        # Exact wording and direction can be merged without rewriting a claim.
        key = (finding['text'], finding['direction'], finding['review_status'], tuple(finding['limitations']))
        if key in seen:
            existing = seen[key]
            existing['observation_ids'].extend(finding['observation_ids'])
            existing['citation_ids'] = list(dict.fromkeys(existing['citation_ids'] + ids))
        else:
            target['findings'].append(finding)
            seen[key] = finding
    for category in categories:
        findings = category['findings']
        if findings:
            category['status'] = ('credit_concern' if any(f['direction'] == 'negative' for f in findings)
                                  else 'qualified' if any(f['review_status'] == 'qualified' for f in findings)
                                  else 'supporting_factor' if any(f['direction'] == 'positive' for f in findings)
                                  else 'insufficient_evidence')
    all_findings = [f for category in categories for f in category['findings']]
    strengths = [f for f in all_findings if f['direction'] == 'positive' and f['review_status'] == 'accepted'][:3]
    concerns = [f for f in all_findings if f['direction'] == 'negative'][:3]
    if len(concerns) < 3:
        concerns += [f for f in all_findings if f['review_status'] == 'qualified' and f not in concerns][:3-len(concerns)]
    if len(concerns) < 3:
        concerns += gaps[:3-len(concerns)]
    overall = artifact.get('overall_assessment') or {}
    return {'overall_assessment': {'text': overall.get('policy') or 'Management assessment unavailable.',
                                   'outcome': overall.get('outcome', 'unavailable'),
                                   'status': 'qualified' if overall.get('information_gaps') or artifact.get('completion_status') == 'partial' else 'accepted'},
            'categories': categories, 'key_strengths': strengths, 'key_concerns': concerns,
            'monitoring_priorities': [], 'information_gaps': gaps,
            'coverage_missing': list(artifact.get('coverage', {}).get('missing', [])),
            'uncategorized': uncategorized,
            'executive_profiles': deepcopy(artifact.get('profiles', [])),
            'reviewed_observations': deepcopy([o for o in artifact.get('observations', [])
                                                if o.get('review_outcome') in ('accepted', 'qualified')]),
            'citations': deepcopy(citations)}
