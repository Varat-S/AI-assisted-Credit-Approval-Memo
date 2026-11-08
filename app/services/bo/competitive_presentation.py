"""Read-only grouping of selected findings and their frozen source explanations.

No retrieval, inference, rewriting, selection or persistence. Explanatory fields
are presentation copies of the same verified audit already used by evidence panels.
"""
from copy import deepcopy

from app.schemas.bo import HypothesisRecord
from app.services.bo.competitive_positioning import eligible, evidence_ids
from app.services.bo.roster_v3 import V3_AGENT_6_ID
from app.services.pipeline.artifacts import ArtifactIntegrityError
from app.services.bo.finding_assessment import assessment

REVENUE = 'Revenue Drivers'
COST = 'Cost Drivers'
INTERACTIONS = 'Revenue & Cost Interactions'
GROUPS = (REVENUE, COST, INTERACTIONS)
PRIMARY_GROUP = {'m1_revenue_quality': REVENUE, 'm1_customer_stickiness': REVENUE,
                 'm1_pricing_power': REVENUE, 'm1_operating_model': COST,
                 'm1_competitive_durability': REVENUE}
TOPICS = {'m1_revenue_quality': 'Pricing & reimbursement', 'm1_customer_stickiness': 'Demand & payer mix',
          'm1_pricing_power': 'Customer retention', 'm1_operating_model': 'Operating costs',
          'm1_competitive_durability': 'Competitive position & entry barriers',
          V3_AGENT_6_ID: 'Cross-dimensional insight'}
SOURCE_ORDER = {agent: rank for rank, agent in enumerate(TOPICS)}
TYPES = {'fact': 'Fact', 'calculated_fact': 'Calculated fact', 'management_claim': 'Management statement',
         'inference': 'Inference', 'assumption': 'Assumption'}


def selected_source(claim, audit, provenance):
    """Never borrow another producer, superseded source or component's prose."""
    hid = claim['hypothesis_ids'][0]
    if claim['claim_id'] != 'selected:' + hid:
        raise ArtifactIntegrityError('Selected finding claim ID does not match its source.')
    producers = {p['agent_id']: p['agent_run_id'] for p in provenance['producer_records']
                 if p['validation_status'] == 'valid'}
    matches = []
    for index, source in enumerate(audit['hypotheses']['records']):
        if source['hypothesis_id'] != hid or source['acceptance_state'] != 'accepted':
            continue
        record = HypothesisRecord.model_validate({k: v for k, v in source.items() if k in HypothesisRecord.model_fields})
        if (eligible(record) and record.analysis_run_id == audit['run']['analysis_run_id']
                and record.agent_run_id == producers.get(record.agent_id)):
            matches.append((index, source, record))
    if len(matches) != 1:
        raise ArtifactIntegrityError('Selected finding lacks one current validated source for presentation.')
    index, source, record = matches[0]
    if (claim['text'] != source['claim'] or claim['claim_type'] != source['claim_type']
            or claim['parameter_result_ids'] != source['parameter_result_ids']
            or set(claim['evidence_ids']) != evidence_ids(record)
            or claim['hypothesis_ids'] != [hid, *source['component_hypothesis_ids']]):
        raise ArtifactIntegrityError('Selected finding differs from its frozen source.')
    return index, source


def grouped_findings(entries, audit, provenance):
    groups = {name: [] for name in GROUPS}
    for entry in entries:
        claim = entry['claim']
        index, source = selected_source(claim, audit, provenance)
        if source['agent_id'] == V3_AGENT_6_ID:
            group = INTERACTIONS
        else:
            group = PRIMARY_GROUP[source['agent_id']]
        details = []
        seen = {source['claim']}
        def add(label, value, path):
            if isinstance(value, str) and value.strip() and (value not in seen or path == 'interpretation/watch_trigger'):
                details.append({'label': label, 'text': value,
                                'source_path': f'/hypotheses/records/{index}/' + path})
                seen.add(value)
        add('Credit explanation', source.get('credit_mechanism'), 'credit_mechanism')
        interpretation = source.get('interpretation') or {}
        for key, label in [('implication', 'Specialist interpretation'), ('magnitude', 'Magnitude'),
                           ('trend', 'Trend'), ('watch_trigger', 'Watch trigger')]:
            add(label, interpretation.get(key), 'interpretation/' + key)
        add('How the effect transmits', source.get('transmission_mechanism'), 'transmission_mechanism')
        pointers = [
            {'label': 'Finding', 'parts': [{'text': source['claim'],
                'source_path': f'/hypotheses/records/{index}/claim'},
                *[d for d in details if d['label'] in {'Magnitude', 'Trend'}]],
             'empty_text': ''},
            {'label': 'Credit Implication',
             'parts': [d for d in details if d['label'] in {'Credit explanation', 'Specialist interpretation', 'How the effect transmits'}],
             'empty_text': 'No separate credit implication was recorded.'},
            {'label': 'Watch Triggers', 'parts': [d for d in details if d['label'] == 'Watch trigger'],
             'empty_text': 'No specific watch trigger was recorded.'},
        ]
        entry = deepcopy(entry)
        review = assessment(source, pointers, claim.get('uncertainty'))
        pointers[0]['classification'] = review['finding']
        pointers[1]['classification'] = review['implication']
        entry['evidence']['title'] = TOPICS[source['agent_id']]
        groups[group].append({**entry, 'topic': TOPICS[source['agent_id']],
                              'claim_type_label': TYPES[source['claim_type']],
                              'direction_label': source['direction'].capitalize(),
                              'details': details, 'pointers': pointers, 'assessment': review,
                              'source_hypothesis_id': source['hypothesis_id'],
                              'source_agent_id': source['agent_id']})
    for entries in groups.values():
        entries.sort(key=lambda e: (SOURCE_ORDER[e['source_agent_id']], e['source_hypothesis_id']))
    return [{'title': name, 'entries': deepcopy(groups[name])} for name in GROUPS if groups[name] or name in (REVENUE, COST)]


def insight_formation(source, audit, provenance):
    """Exact current-run specialist lineage for Agent 6's recorded component IDs.

    Never infer contributors from matching wording or filing quotations. Invalid,
    withheld or superseded components are not replaced with another finding.
    """
    from app.services.bo.roster_v3 import V3_M1_PRIMARY_IDS, V3_SPEC_BY_AGENT
    if source.get('agent_id') != V3_AGENT_6_ID:
        return None
    producers = {p['agent_id']: p['agent_run_id'] for p in provenance['producer_records']
                 if p['validation_status'] == 'valid'}
    groups, unavailable = {}, 0
    for hid in dict.fromkeys(source.get('component_hypothesis_ids', [])):
        matches = [h for h in audit['hypotheses']['records'] if h['hypothesis_id'] == hid]
        if len(matches) != 1:
            unavailable += 1
            continue
        h = matches[0]
        record = HypothesisRecord.model_validate({k: v for k, v in h.items() if k in HypothesisRecord.model_fields})
        if not (record.agent_id in V3_M1_PRIMARY_IDS and eligible(record)
                and record.acceptance_state.value == 'accepted'
                and record.analysis_run_id == audit['run']['analysis_run_id']
                and record.agent_run_id == producers.get(record.agent_id)):
            unavailable += 1
            continue
        spec = V3_SPEC_BY_AGENT[record.agent_id]
        group = groups.setdefault(spec.code, {'agent_number': spec.code[-1], 'agent_name': spec.title, 'findings': []})
        group['findings'].append({'hypothesis_id': hid, 'text': h['claim']})
    return {'contributors': [groups[k] for k in sorted(groups)], 'unavailable_count': unavailable,
            'text': source['claim'], 'credit_implication': source.get('credit_mechanism'),
            'direction_label': {'positive': 'Positive', 'negative': 'Negative', 'neutral': 'Neutral',
                                'mixed': 'Mixed'}.get(source.get('direction'), 'Unassessed')}
