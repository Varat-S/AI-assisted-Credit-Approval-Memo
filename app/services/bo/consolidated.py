"""Exact-run deterministic copying/assembly; no providers or inference here."""
import json
from app.core.hashing import content_hash
from app.schemas.bo_consolidated import (ConsolidatedBO, CompetitiveSynthesis, CopyItem, Section, Source, TITLES)
from app.services.pipeline.artifacts import verified_artifacts, ArtifactIntegrityError
from app.services.bo.reconcile import similarity

# No standalone industry report exists in this roster. Its designated report is
# the complete ordered governed findings, including interpretation/quotes.
MAPPINGS = (
    (0, ('module_conclusions','M3','m3_rebuild','structure','artifact')),
    (0, ('module_conclusions','M4','m4_analysis','deliverable_1')),
    (1, ('module_conclusions','M3','m3_rebuild','management','artifact')),
    (3, ('module_conclusions','M4','m4_analysis','deliverable_2')),
    (3, ('module_conclusions','M4','m4_analysis','deliverable_4')),
    (4, ('module_conclusions','M2','findings')),
)

def at(payload, path):
    for key in path:
        if not isinstance(payload, dict) or key not in payload:
            return None
        payload = payload[key]
    return payload


def selection_issues(parsed, hypotheses, reconciliation):
    """Deterministic gates supplement (never replace) independent challenge."""
    s = CompetitiveSynthesis.model_validate(parsed)
    points = s.key_drivers
    ids = [p.claim_id for p in points]
    issues = []
    if len(set([s.overall_assessment.claim_id, *ids])) != len(ids) + 1:
        issues.append('duplicate point ID')
    decisions = [d.hypothesis_id for d in s.selections]
    if len(set(decisions)) != len(decisions) or set(decisions) != set(hypotheses):
        issues.append('Every candidate requires exactly one selection decision')
    for p in [s.overall_assessment, *points]:
        if any(h not in hypotheses or not hypotheses[h].usable for h in p.hypothesis_ids):
            issues.append('Inadmissible or non-Module-1 basis: ' + p.claim_id)
        governed_quotes = [q for hid in p.hypothesis_ids if hid in hypotheses
                           for q in hypotheses[hid].quoted_values]
        if any(not any(all(source.get(k) == v for k,v in q.model_dump(exclude_none=True).items())
                           for source in governed_quotes) for q in p.quoted_values):
            issues.append('Unbound quoted value: ' + p.claim_id)
        if not p.text.strip() or not p.claim_id.strip():
            issues.append('Empty analytical point')
        for other in points:
            if p is other or p.claim_id == s.overall_assessment.claim_id:
                continue
            a, b = set(p.hypothesis_ids), set(other.hypothesis_ids)
            groups = lambda refs: {reconciliation.group_of(h) for h in refs} - {None}
            if a == b or groups(a) & groups(b) or similarity(p.text, other.text) >= .8:
                issues.append('Duplicate/artificially split economic insight: ' + p.claim_id)
    point_map = {p.claim_id: p for p in points}
    for d in s.selections:
        used = [p.claim_id for p in points if d.hypothesis_id in p.hypothesis_ids]
        if d.disposition == 'audit_only':
            if used or d.hypothesis_id in s.overall_assessment.hypothesis_ids or d.point_id is not None:
                issues.append('Audit-only candidate presented: ' + d.hypothesis_id)
        elif d.point_id not in point_map or d.hypothesis_id not in point_map[d.point_id].hypothesis_ids:
            issues.append('Selection target does not incorporate candidate: ' + d.hypothesis_id)
    dimensions = {p.dimension for p in points}
    if not {'revenue', 'cost'} <= dimensions and not s.coverage_gaps:
        issues.append('Missing revenue/cost coverage requires explicit gaps')
    if len(points) < 5 and (s.completeness != 'incomplete' or not s.human_review_required or not s.coverage_gaps):
        issues.append('Five-point shortfall must be incomplete with gaps and human review')
    if not s.human_review_required:
        issues.append('Human review is required for all draft outputs')
    return sorted(set(issues))


def legacy_claims(parsed):
    """Lossless internal adapter for existing conclusion/challenge validators."""
    def clean(p):
        result = {k:v for k,v in p.items() if k not in ('dimension','counterevidence','analysis')}
        if p.get('analysis'):
            result['text'] = '\n\n'.join([p['text'], *p['analysis'].values()])
        return result
    return {'overall_assessment': clean(parsed['overall_assessment']),
            'key_drivers': [clean(p) for p in parsed['key_drivers']],
            'open_questions': [*parsed['coverage_gaps'], *parsed['residual_uncertainty']]}


def assemble(session, *, case_id, run_id, version):
    rows = {r.name:r for r in verified_artifacts(session, case_id, version)}
    memo_stage, audit_stage = 'bo_memo:' + run_id, 'bo_audit:' + run_id
    if memo_stage not in rows or audit_stage not in rows:
        raise ArtifactIntegrityError('Consolidated source archives missing')
    memo, audit = [json.loads(rows[n].payload_json) for n in (memo_stage, audit_stage)]
    from app.models.orm import AcceptedBusinessOverviewRow
    from app.services.bo.workbench import verify_report_identity
    from sqlalchemy import select
    handoff = session.scalar(select(AcceptedBusinessOverviewRow).where(
        AcceptedBusinessOverviewRow.analysis_run_id == run_id))
    if handoff is None or handoff.case_id != case_id or handoff.snapshot_version != version:
        raise ArtifactIntegrityError('Exact run handoff missing')
    for kind, payload in [('memo',memo), ('audit',audit)]:
        verify_report_identity(session, handoff, kind, payload)
    sources = [Source(stage=n, sha256=rows[n].sha256, case_id=case_id,
                     analysis_run_id=run_id, evidence_snapshot_version=version) for n in (memo_stage,audit_stage)]
    sections = [Section(title=t, status='complete') for t in TITLES]
    for index, path in MAPPINGS:
        value = at(memo, path)
        section = sections[index]
        if value is None or value == [] or value == {}:
            section.status = 'missing' if not section.items else 'incomplete'
            section.limitations.append('Missing designated content: ' + '.'.join(path))
        else:
            if section.status == 'missing':
                section.status = 'incomplete'
            section.items.append(CopyItem(source_stage=memo_stage, field_path=list(path),
                                          content_hash=content_hash(value), content=value))
    if sections[4].items:
        sections[4].status = 'incomplete'
        sections[4].limitations.append('Missing standalone Industry report: this roster records governed industry findings only. All available findings are preserved below; no replacement report has been generated.')
    selected = audit.get('competitive_selection')
    rounds = (audit.get('challenger') or {}).get('rounds')
    final_id = handoff.payload.get('business_topic_conclusion_id')
    challenge = next((r for r in reversed(rounds if isinstance(rounds,list) else [])
                      if r.get('conclusion_id') == final_id), None)
    section = sections[2]
    if selected is None:
        section.status = 'missing'
        section.limitations.append('No consolidated competitive synthesis was validated.')
    else:
        frozen = next((c for c in audit.get('conclusions', []) if c.get('conclusion_id') == final_id), None)
        if (not frozen or audit.get('competitive_selection_conclusion_id') != final_id
                or audit.get('competitive_selection_orchestrator_run_id') != frozen.get('orchestrator_run_id')):
            raise ArtifactIntegrityError('Selection does not belong to final conclusion')
        projection = legacy_claims(selected)
        for key in ('overall_assessment', 'key_drivers'):
            projected = projection[key] if key == 'key_drivers' else [projection[key]]
            accepted = frozen['payload'][key] if key == 'key_drivers' else [frozen['payload'][key]]
            # quoted_values are validator input; the legacy conclusion does not serialize them.
            if len(projected) != len(accepted) or any(any(p.get(k) != a.get(k) for k in
                    ('claim_id','text','hypothesis_ids','evidence_ids','uncertainty')) for p,a in zip(projected,accepted)):
                raise ArtifactIntegrityError('Selection differs from challenged conclusion')
        section.synthesis = CompetitiveSynthesis.model_validate(selected)
        section.status = section.synthesis.completeness
        if (not challenge or challenge.get('status') != 'validated'
                or challenge.get('outcome') not in {'accepted', 'accepted_with_qualification'}
                or not memo['run'].get('validators_enforced', True)):
            section.status = 'incomplete'
            section.limitations.append('Independent enforced validation/challenge unavailable; advisory draft only.')
        section.limitations.extend(section.synthesis.coverage_gaps)
    # Module completeness/validation labels are preserved, never inferred from schema success.
    for index, module in [(0,'M3'),(0,'M4'),(1,'M3'),(2,'M1'),(3,'M4'),(4,'M2')]:
        block = (memo.get('module_conclusions') or {}).get(module) or {}
        if block.get('status') != 'complete':
            if sections[index].status == 'complete':
                sections[index].status = 'incomplete'
            sections[index].limitations.extend(block.get('missing_information') or [module + ' is incomplete.'])
    return ConsolidatedBO(schema_id='consolidated-business-overview', schema_version='1.0', case_id=case_id, analysis_run_id=run_id, evidence_snapshot_version=version,
                         sources=sources, evidence_sources=memo.get("sources") or [], sections=sections, audit_stage=audit_stage,
                         governance=dict(memo['status']), challenge=challenge,
                         execution_mode=memo['run']['execution_mode']).model_dump(mode='json')


def load(session, case_id, run_id, version):
    rows = {r.name:r for r in verified_artifacts(session, case_id, version)}
    name = 'bo_consolidated:' + run_id
    if name not in rows:
        return None  # historical reports stay historical; no synthetic migration
    result = ConsolidatedBO.model_validate_json(rows[name].payload_json).model_dump(mode='json')
    if (result['case_id'],result['analysis_run_id'],result['evidence_snapshot_version']) != (case_id,run_id,version):
        raise ArtifactIntegrityError('Consolidated identity mismatch')
    # Reassembly compares all copies, hashes, selection and governance with their frozen sources.
    if result != assemble(session, case_id=case_id,run_id=run_id,version=version):
        raise ArtifactIntegrityError('Consolidated sources or copy fidelity mismatch')
    return result
