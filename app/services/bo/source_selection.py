"""Pure selection validation and deterministic, verbatim source projection."""
from collections import Counter
from copy import deepcopy

from app.prompts import source_selection as contract
from app.services.bo.competitive_positioning import _schema_issues, evidence_ids, eligible
from app.services.bo.roster_v3 import V3_AGENT_6_ID
from app.schemas.bo import HypothesisRecord


def validate_plan(plan, source):
    issues = _schema_issues(plan, contract.WRITER_SCHEMA)
    if issues:
        return issues
    records = {h['hypothesis_id']: h for h in source['hypotheses']}
    entries = plan['selections'] + plan['omissions']
    counts = Counter(d['hypothesis_id'] for d in entries)
    if set(counts) != set(records) or any(n != 1 for n in counts.values()):
        issues.append('selection_coverage: every eligible finding must occur exactly once; unknown/duplicate IDs are forbidden.')
    if sum(d['placement'] == 'lead' for d in plan['selections']) != 1:
        issues.append('selection_lead: exactly one source finding must be the lead.')
    for d in entries:
        if not d['reason'].strip():
            issues.append('selection_reason: a substantive nonblank reason is required.')
    for d in plan['selections']:
        h = records.get(d['hypothesis_id'])
        if h is None:
            continue
        if (d['placement'], h['direction']) in {('driver', 'negative'), ('risk', 'positive')}:
            issues.append('selection_direction: placement contradicts the source direction: ' + d['hypothesis_id'])
        if h['agent_id'] == V3_AGENT_6_ID and (not h['transmission_mechanism'] or not h['component_hypothesis_ids']
                or not set(h['component_hypothesis_ids']) <= records.keys()):
            issues.append('selection_lineage: Agent 6 requires its current validated mechanism/components.')
    return issues


def project(plan, source):
    """Cannot receive model-authored prose: the wire schema contains only IDs/reasons."""
    issues = validate_plan(plan, source)
    if issues:
        raise ValueError('; '.join(issues))
    # Preserve the model's raw plan in the runner audit, but apply mandatory
    # primary cost coverage before copying claims. Interactions supplement these
    # findings; component lineage alone does not replace their visible analysis.
    plan = deepcopy(plan)
    records = {h['hypothesis_id']: h for h in source['hypotheses']}
    retained = []
    for omission in plan['omissions']:
        h = records[omission['hypothesis_id']]
        if (h['agent_id'] == 'm1_operating_model'
                and eligible(HypothesisRecord.model_validate(h))):
            retained.append(dict(
                hypothesis_id=h['hypothesis_id'],
                placement='risk' if h['direction'] == 'negative' else 'driver',
                reason='Mandatory primary cost coverage: Agent 6 interactions supplement '
                       'rather than replace this validated finding. Original selector omission: '
                       + omission['reason']))
    retained_ids = {d['hypothesis_id'] for d in retained}
    plan['omissions'] = [d for d in plan['omissions'] if d['hypothesis_id'] not in retained_ids]
    plan['selections'].extend(sorted(retained, key=lambda d: d['hypothesis_id']))
    issues = validate_plan(plan, source)
    if issues:
        raise ValueError('; '.join(issues))
    records = {h['hypothesis_id']: h for h in source['hypotheses']}
    claims = {}
    output = dict(schema_version=contract.PROJECTION_VERSION, policy_version=contract.POLICY_VERSION,
                  overall_assessment=None, strengths=[], weaknesses=[], key_drivers=[], material_risks=[],
                  selection_decisions=[], interaction_basis=[], merged_duplicates=[],
                  open_questions=[], unresolved_contradictions=deepcopy(source['open_conflicts']), follow_up=[])
    for choice in plan['selections']:
        h = records[choice['hypothesis_id']]
        refs = [h['hypothesis_id'], *h['component_hypothesis_ids']]
        related = [records[hid] for hid in refs]
        # All source fields remain in the audit; the UI keeps material limitations visible.
        qualifications = []
        for item in related:
            if item['admissibility'] == 'attributed':
                qualifications.append('Management-attributed source finding.')
            elif item['admissibility'] == 'qualified_narrative':
                qualifications.append('Qualified source finding.')
            qualifications.extend(item.get('missing_information', []))
            if item.get('contradicting_evidence_ids'):
                qualifications.append('Source finding has recorded counterevidence; see evidence panel.')
        cid = 'selected:' + h['hypothesis_id']
        category = {'lead': 'assessment', 'driver': 'driver', 'risk': 'risk'}[choice['placement']]
        claim = dict(claim_id=cid, category=category, text=h['claim'], title=None,
                     section='executive' if choice['placement'] == 'lead' else h['section'],
                     claim_type=h['claim_type'], hypothesis_ids=refs,
                     parameter_result_ids=deepcopy(h['parameter_result_ids']),
                     evidence_ids=sorted(evidence_ids(HypothesisRecord.model_validate(h))),
                     materiality=h['materiality'], uncertainty=' '.join(dict.fromkeys(qualifications)) or None,
                     quoted_values=deepcopy(h['quoted_values']))
        claims[cid] = claim
        if choice['placement'] == 'lead':
            output['overall_assessment'] = claim
        else:
            output['key_drivers' if choice['placement'] == 'driver' else 'material_risks'].append(claim)
        if h['agent_id'] == V3_AGENT_6_ID:
            output['interaction_basis'].append(dict(claim_id=cid, agent6_hypothesis_ids=[h['hypothesis_id']]))
    selected = {d['hypothesis_id']: d for d in plan['selections']}
    omitted = {d['hypothesis_id']: d for d in plan['omissions']}
    for hid in records:
        decision = selected.get(hid) or omitted[hid]
        output['selection_decisions'].append(dict(
            hypothesis_id=hid, decision='selected' if hid in selected else 'omitted',
            claim_ids=[cid for cid,c in claims.items() if hid in c['hypothesis_ids']] if hid in selected else [],
            reason=decision['reason']))
    return output
