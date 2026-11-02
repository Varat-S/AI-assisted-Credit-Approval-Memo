"""Module 1 editorial boundary. No inference, retrieval, persistence or memo assembly.

Reference/selection/number gates are deterministic. Semantic faithfulness and
material omission review still belong to the existing independent challenger.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re

import jsonschema

from app.prompts.competitive_positioning import (
    INPUT_VERSION, OUTPUT_VERSION, POLICY_VERSION, WRITER_SCHEMA, CHALLENGER_SCHEMA,
)
from app.schemas.agentic import AcceptanceState
from app.schemas.bo import Admissibility, Disposition
from app.services.bo.hypotheses import unbound_numbers
from app.services.bo.indicators import IndicatorSet
from app.services.bo.reconcile import reconcile
from app.services.bo.roster_v3 import V3_M1_PRIMARY_IDS, V3_AGENT_6_ID, V3_SPEC_BY_AGENT
from app.services.bo.synthesis import iter_claims, validate_orchestrator_output

M1_IDS = frozenset((*V3_M1_PRIMARY_IDS, V3_AGENT_6_ID))
M1_PARAMETERS = frozenset(p for a in M1_IDS for p in V3_SPEC_BY_AGENT[a].owned_parameters)
_CAUSAL = re.compile(
    r"\b(?:compound\w*|amplif\w*|intensif\w*|reinforc\w*|exacerbat\w*|"
    r"caus\w*|driv(?:e|es|en|ing)|transmit\w*|interact\w*|"
    r"lead(?:s|ing)? to|result(?:s|ing)? in|therefore|thereby|because|"
    r"raise[sd]?|reduc\w*|weaken\w*|protect\w*|support\w*)\b", re.I)
_ATTRIBUTION = re.compile(r"\b(?:management|company (?:states|reports|believes|expects)|"
                          r"according to|reported by|management[- ]attributed)\b", re.I)


def evidence_ids(record):
    return {*record.evidence_ids(),
            *(q['evidence_id'] for q in record.evidence_quotes if q.get('evidence_id')),
            *(record.mitigant.outcome_evidence_ids if record.mitigant else [])}


def eligible(record):
    spec = V3_SPEC_BY_AGENT.get(record.agent_id)
    return (record.agent_id in M1_IDS and record.usable
            and record.disposition in (Disposition.SUPPORTED, Disposition.QUALIFIED)
            and record.section == spec.code
            and record.validator_id == spec.validator_id
            and bool(record.validator_version))


def scoped_indicators(records, indicators):
    records = list(records)
    refs = {pid for h in records for pid in h.parameter_result_ids}
    refs.update(q.get('parameter_result_id') for h in records for q in h.quoted_values)
    scoped = IndicatorSet(
        results=[r for r in indicators.results if r.parameter_result_id in refs
                 and r.acceptance_state is AcceptanceState.ACCEPTED
                 and r.analysis_run_id in {h.analysis_run_id for h in records}],
        traces=[t for t in indicators.traces if t.parameter_result_id in refs],
    )
    known = scoped.known_values()
    scoped.traces = [t for t in scoped.traces if t.parameter_result_id in known
                     and t.value == known[t.parameter_result_id]]
    return scoped


def build_input(*, identity, hypotheses, parameters, indicators, validated_runs,
                coverage, data_limitations=(), open_conflicts=(),
                challenge_feedback=(), validation_feedback=()):
    """Accept canonical records, pin producers, and expose only M1 evidence.

    An inconsistent M1 identity is an error, not an invitation to borrow another
    run's finding. Non-M1 records/parameters are simply outside this input.
    """
    expected_identity = {'case_id', 'analysis_run_id', 'evidence_snapshot_version',
                         'evidence_snapshot_hash', 'as_of_date', 'evidence_cutoff_timestamp'}
    if set(identity) != expected_identity:
        raise ValueError('Competitive Positioning identity requires exactly the versioned identity fields.')
    if (not isinstance(identity['case_id'], str) or not identity['case_id'].strip()
            or not isinstance(identity['analysis_run_id'], str) or not identity['analysis_run_id'].strip()
            or type(identity['evidence_snapshot_version']) is not int
            or identity['evidence_snapshot_version'] < 1
            or not isinstance(identity['evidence_snapshot_hash'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', identity['evidence_snapshot_hash'])
            or any(identity[k] is not None and not isinstance(identity[k], str)
                   for k in ('as_of_date', 'evidence_cutoff_timestamp'))):
        raise ValueError('Competitive Positioning identity is malformed or unbound.')
    run_id = identity['analysis_run_id']
    records, excluded = [], []
    for h in hypotheses:
        if h.agent_id not in M1_IDS:
            continue
        if h.analysis_run_id != run_id:
            raise ValueError('Competitive Positioning hypothesis belongs to another run.')
        if eligible(h) and validated_runs.get(h.agent_id) == h.agent_run_id:
            records.append(h)
        else:
            excluded.append(h)
    if len({h.hypothesis_id for h in records}) != len(records):
        raise ValueError('Duplicate canonical Competitive Positioning hypothesis ID.')
    current = {h.hypothesis_id: h for h in records}
    for h in records:
        if h.agent_id == V3_AGENT_6_ID and any(
                cid not in current or current[cid].agent_id not in V3_M1_PRIMARY_IDS
                for cid in h.component_hypothesis_ids):
            raise ValueError('Agent 6 components are not current validated M1 primaries.')
    accepted = []
    for p in parameters:
        if p.agent_id not in M1_IDS:
            continue
        if p.analysis_run_id != run_id:
            raise ValueError('Competitive Positioning parameter belongs to another run.')
        if (p.acceptance_state is AcceptanceState.ACCEPTED
                and p.parameter_id in V3_SPEC_BY_AGENT[p.agent_id].owned_parameters
                and validated_runs.get(p.agent_id) == p.agent_run_id):
            accepted.append(p.model_dump(mode='json'))
    bounded = scoped_indicators(records, indicators)
    related = reconcile(records, excluded)
    return {
        'schema_version': INPUT_VERSION, 'identity': deepcopy(identity),
        'policy_version': POLICY_VERSION,
        'hypotheses': [h.model_dump(mode='json') for h in records],
        'parameters': accepted,
        'indicators': [t.model_dump(mode='json') for t in bounded.traces
                       if t.parameter_result_id in bounded.known_values()],
        'duplicate_groups': related.duplicate_groups,
        'contradictions': related.contradictions,
        'coverage': {a: deepcopy(c) for a, c in coverage.items() if a in M1_IDS},
        'data_limitations': deepcopy(list(data_limitations)),
        'open_conflicts': deepcopy(list(open_conflicts)),
        'audit_only_hypotheses': [h.model_dump(mode='json') for h in excluded],
        'challenge_feedback': deepcopy(list(challenge_feedback)),
        'validation_feedback': deepcopy(list(validation_feedback)),
    }


def _schema_issues(parsed, schema):
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(parsed),
                    key=lambda e: str(list(e.path)))
    return [f'editorial_schema: {list(e.path)}: {e.message}' for e in errors]


def validate_output(parsed, *, hypotheses, indicators, parameters):
    """Stricter source-bound gates on top of existing synthesis validation.

    No rewrite/drop/coverage insertion is applied: the submitted editorial
    decisions either pass together or remain a rejected auditable attempt.
    """
    issues = _schema_issues(parsed, WRITER_SCHEMA)
    if issues:
        return issues
    records = {h.hypothesis_id: h for h in hypotheses if eligible(h)}
    bounded = scoped_indicators(records.values(), indicators)
    parameter_by_id = {p.parameter_result_id: p for p in parameters
                       if p.agent_id in M1_IDS
                       and p.parameter_id in V3_SPEC_BY_AGENT[p.agent_id].owned_parameters
                       and p.acceptance_state is AcceptanceState.ACCEPTED}
    accepted_ids = set(parameter_by_id) | set(bounded.known_values())
    issues += validate_orchestrator_output(
        parsed, hypotheses=records, reconciliation=reconcile(list(records.values())),
        indicators=bounded, accepted_parameter_ids=accepted_ids)
    claims = dict((c['claim_id'], c) for _, c in iter_claims(parsed))
    if parsed['overall_assessment']['section'] != 'executive':
        issues.append('editorial_section: the lead must use executive.')
    for name, c in iter_claims(parsed):
        cid = c['claim_id']
        if not cid.strip() or cid.startswith('source:') or not c['text'].strip():
            issues.append(f'editorial_claim: {cid!r} has blank text/ID or a reserved ID.')
        category = {'overall_assessment': 'assessment', 'key_drivers': 'driver',
                    'material_risks': 'risk'}[name]
        if c['category'] != category:
            issues.append(f'editorial_category: {cid} must be {category}.')
        used = [records[hid] for hid in c['hypothesis_ids'] if hid in records]
        if name != 'overall_assessment' and c['section'] not in {h.section for h in used}:
            issues.append(f'editorial_section: {cid} must retain a cited M1 section.')
        allowed = {e for h in used for e in evidence_ids(h)}
        if not c['evidence_ids'] or not set(c['evidence_ids']) <= allowed:
            issues.append(f'editorial_evidence: {cid} lacks source-bound evidence.')
        if any(h.admissibility is Admissibility.QUALIFIED_NARRATIVE
               or h.contradicting_evidence_ids for h in used) and not (c['uncertainty'] or '').strip():
            issues.append(f'editorial_qualification: {cid} must preserve qualification/counterevidence.')
        if any(h.admissibility is Admissibility.ATTRIBUTED for h in used) and not _ATTRIBUTION.search(c['text']):
            issues.append(f'editorial_attribution: {cid} must attribute management statements.')
        # Unlike the legacy gate, a claimed quoted_value cannot license itself.
        source_values = [q for h in used for q in h.quoted_values]
        source_refs = {pid for h in used for pid in h.parameter_result_ids}
        source_refs.update(q.get('parameter_result_id') for q in source_values)
        source_values += [dict(parameter_result_id=t.parameter_result_id, value=t.value,
                               unit=t.units, period=t.period,
                               denominator=(t.denominator or {}).get('name'))
                          for t in bounded.traces if t.parameter_result_id in source_refs]
        for q in c['quoted_values']:
            matches = [s for s in source_values
                       if s.get('parameter_result_id') == q['parameter_result_id']
                       and s.get('value') == q['value']]
            if not matches or not any(all(q.get(k) is None or q[k] == s.get(k)
                                          for k in ('unit', 'period', 'denominator')) for s in matches):
                issues.append(f'editorial_quoted_value: {cid} invents/misbinds {q!r}.')
        permitted_params = source_refs | {
            pid for pid, p in parameter_by_id.items()
            if any(h.agent_id == p.agent_id and h.parameter_id == p.parameter_id for h in used)}
        if not set(c['parameter_result_ids']) <= permitted_params:
            issues.append(f'editorial_parameter: {cid} uses unrelated parameter context.')
        values = [q['value'] for q in source_values if isinstance(q.get('value'), (int, float))]
        quotes = [q['quote'] for h in used for q in h.evidence_quotes if q.get('quote')]
        for token in sorted(set(unbound_numbers(c['text'], values, quotes))):
            issues.append(f'editorial_number: {cid} states unbound {token!r}.')

    decisions = parsed['selection_decisions']
    counts = Counter(d['hypothesis_id'] for d in decisions)
    if set(counts) != set(records) or any(n != 1 for n in counts.values()):
        issues.append('editorial_ledger: exactly one decision per eligible finding is required.')
    for d in decisions:
        hid, refs = d['hypothesis_id'], d['claim_ids']
        if not d['reason'].strip():
            issues.append(f'editorial_ledger: {hid} needs a specific reason.')
        if d['decision'] == 'omitted':
            if refs:
                issues.append(f'editorial_ledger: omitted {hid} cannot name presented claims.')
            # Primary component references may be lineage only. An omitted
            # finding must not otherwise appear in the narrative's support.
            for cid, c in claims.items():
                if hid in c['hypothesis_ids'] and not _component_only(hid, c, records):
                    issues.append(f'editorial_ledger: omitted {hid} is presented by {cid}.')
        else:
            actual = {cid for cid, c in claims.items() if hid in c['hypothesis_ids']}
            if not refs or set(refs) != actual:
                issues.append(f'editorial_ledger: {hid} must name all directly presenting claims.')
            if d['decision'] == 'merged' and any(
                    not (set(claims.get(cid, {}).get('hypothesis_ids', [])) - {hid}) for cid in refs):
                issues.append(f'editorial_ledger: merged {hid} needs another supporting finding.')
    for merge in parsed['merged_duplicates']:
        ids = [merge['kept_hypothesis_id'], *merge['merged_hypothesis_ids']]
        if len(set(ids)) != len(ids) or not set(ids) <= set(records):
            issues.append('editorial_duplicates: duplicate merge has unknown/repeated IDs.')
        ledger = {d['hypothesis_id']: d for d in decisions}
        kept = ledger.get(merge['kept_hypothesis_id'], {})
        if kept.get('decision') not in {'selected', 'merged'}:
            issues.append('editorial_duplicates: kept finding is not presented.')
        for hid in merge['merged_hypothesis_ids']:
            other = ledger.get(hid, {})
            if (other.get('decision') != 'merged'
                    or not set(other.get('claim_ids', [])) & set(kept.get('claim_ids', []))):
                issues.append(f'editorial_duplicates: {hid} is not merged with the kept finding.')
    interactions = parsed['interaction_basis']
    if len({b['claim_id'] for b in interactions}) != len(interactions):
        issues.append('editorial_interaction: duplicate interaction claim IDs.')
    basis = {b['claim_id']: b['agent6_hypothesis_ids'] for b in interactions}
    for cid in basis.keys() - claims.keys():
        issues.append(f'editorial_interaction: unknown claim {cid}.')
    for cid, c in claims.items():
        used = [records[h] for h in c['hypothesis_ids'] if h in records]
        a6 = {h.hypothesis_id for h in used if h.agent_id == V3_AGENT_6_ID}
        if set(basis.get(cid, [])) != a6:
            issues.append(f'editorial_interaction: {cid} must name exactly its cited Agent 6 findings.')
        for hid in a6:
            h = records[hid]
            if (not h.transmission_mechanism or not h.component_hypothesis_ids
                    or not set(h.component_hypothesis_ids) <= set(c['hypothesis_ids'])):
                issues.append(f'editorial_interaction: {cid} lacks validated mechanism/components.')
        # Conservative lexical precheck; it does NOT replace semantic challenge.
        primary_agents = {h.agent_id for h in used if h.agent_id in V3_M1_PRIMARY_IDS}
        if len(primary_agents) > 1 and _CAUSAL.search(c['text']) and not a6:
            issues.append(f'editorial_causal: {cid} combines dimensions causally without Agent 6.')
    return issues


def _component_only(hid, claim, records):
    """An Agent 6 claim may carry components solely to preserve source lineage.

    The writer explicitly declares any directly presented components in its
    ledger; omission is only permitted here for an Agent 6 component.
    """
    return any(h.agent_id == V3_AGENT_6_ID and hid in h.component_hypothesis_ids
               for rid in claim['hypothesis_ids'] if (h := records.get(rid)))


def validate_review(parsed, output, eligible_ids):
    from app.prompts import source_selection
    schema = (source_selection.CHALLENGER_SCHEMA if output.get('policy_version') == source_selection.POLICY_VERSION
              else CHALLENGER_SCHEMA)
    issues = _schema_issues(parsed, schema)
    if issues:
        return issues
    review = parsed['editorial_review']
    omitted = {d['hypothesis_id'] for d in output['selection_decisions'] if d['decision'] == 'omitted'}
    interactions = {b['claim_id'] for b in output['interaction_basis']}
    for key, expected in (
            ('reviewed_hypothesis_ids', set(eligible_ids)),
            ('reviewed_omitted_hypothesis_ids', omitted),
            ('reviewed_interaction_claim_ids', interactions)):
        if set(review[key]) != expected:
            issues.append(f'editorial_review: {key} does not cover exactly the current output.')
    return issues


def audit_selection(output, *, orchestrator_run_id, conclusion_id):
    return {
        'schema_version': OUTPUT_VERSION, 'policy_version': POLICY_VERSION,
        'orchestrator_run_id': orchestrator_run_id, 'conclusion_id': conclusion_id,
        **{key: deepcopy(output[key]) for key in (
            'selection_decisions', 'interaction_basis', 'merged_duplicates', 'follow_up')},
        'quoted_values': {c['claim_id']: deepcopy(c['quoted_values']) for _, c in iter_claims(output)},
    }
