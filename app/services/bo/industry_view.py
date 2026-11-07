"""Read-only grouping of the selected run's governed industry findings."""
GROUPS = [('tailwind', 'Tailwinds'), ('headwind', 'Headwinds'),
          ('mixed', 'Mixed Factors'), ('uncertain', 'Uncertain Factors')]
DIRECTIONS = {'positive': 'tailwind', 'negative': 'headwind', 'mixed': 'mixed', 'neutral': 'uncertain'}


def group_findings(findings):
    groups = [{'id': ident, 'title': title, 'findings': []} for ident, title in GROUPS]
    buckets = {g['id']: g['findings'] for g in groups}
    exposures = []
    for finding in findings:
        metadata = finding.get('industry') or {}
        category = metadata.get('category') or DIRECTIONS.get(finding.get('direction'), 'uncertain')
        entry = {'finding': finding, 'title': metadata.get('title') or 'Industry finding',
                 'direction_label': {'positive': 'Positive', 'negative': 'Negative', 'neutral': 'Neutral', 'mixed': 'Mixed'}.get(finding.get('direction'), 'Unassessed'),
                 'state': metadata.get('state'), 'linked_development_ids': metadata.get('linked_development_ids', [])}
        if category == 'company_exposure' and metadata.get('kind') == 'exposure':
            exposures.append(entry)
        else:
            buckets.get(category, buckets['uncertain']).append(entry)
    # Never link to findings the selected run withheld or classified as exposures.
    titles = {entry['finding']['hypothesis_id']: entry['title'] for group in groups for entry in group['findings']}
    for entry in exposures:
        entry['links'] = [{'id': ident, 'title': titles[ident]} for ident in entry['linked_development_ids'] if ident in titles]
    return {'groups': groups, 'exposures': exposures}
