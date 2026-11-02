"""Read-only, exact-run presentation for history, memo review and audit.

Never chooses a latest company report. No worker, calculations or approval writes.
"""
from urllib.parse import quote
from sqlalchemy import select
from app.models.orm import AcceptedBusinessOverviewRow, FinancialOverviewRunRow, Snapshot

EXECUTION_STATES = ('pending', 'running', 'completed', 'failed', 'stopped', 'interrupted')


class WorkspaceRecordError(ValueError):
    pass


def run_references(job):
    result = job.get('result') or {}
    ids = {}
    for section, field in [('bo', 'analysis_run_id'), ('fo', 'run_id')]:
        if section == 'fo' and job.get('bo_only'):
            ids[section] = None
            continue
        summary = (result.get(section) or {}).get('summary') or {}
        stored, returned = (job.get('run_ids') or {}).get(section), summary.get(field)
        if stored and returned and stored != returned:
            raise WorkspaceRecordError('The selected job has conflicting report references.')
        ids[section] = stored or returned
    return ids


def selected_rows(session, job):
    ids = run_references(job)
    bo = session.scalar(select(AcceptedBusinessOverviewRow).where(
        AcceptedBusinessOverviewRow.analysis_run_id == ids['bo'])) if ids['bo'] else None
    fo = session.get(FinancialOverviewRunRow, ids['fo']) if ids['fo'] else None
    for row in (bo, fo):
        if row is not None and row.case_id != job.get('case_id'):
            raise WorkspaceRecordError('A report reference does not belong to the selected case.')
    return bo, fo


ANALYSIS_TABS = (('memo', 'Memo'), ('bo', 'Business Overview'), ('fo', 'Financial Overview'),
                 ('rms', 'Risk Mitigation & Structuring'), ('audit', 'Audit & Review'), ('execution', 'Execution'))


def analysis_tabs(job, current):
    """Header tabs shared by every page of one analysis. A tab whose report is not recorded yet has no href;
    a module outside the analysis scope has no tab, nor RMS, which needs both."""
    try:
        ids = run_references(job)
    except WorkspaceRecordError:
        ids = {'bo': None, 'fo': None}
    job_id, case = quote(job['job_id'], safe=''), quote(job.get('case_id') or '', safe='')
    reviewable = job.get('execution_status') in EXECUTION_STATES[2:] and any(ids.values())
    hrefs = {
        'memo': f'/analysis/{job_id}/review' if reviewable else None,
        'bo': f'/cases/{case}/bo.html?analysis_run_id={quote(ids["bo"], safe="")}&job={job_id}' if ids['bo'] else None,
        'fo': f'/cases/{case}/fo.html?run_id={quote(ids["fo"], safe="")}&job={job_id}' if ids['fo'] else None,
        'rms': f'/analysis/{job_id}/rms' if reviewable and ids['bo'] and ids['fo'] else None,
        'audit': f'/analysis/{job_id}/audit' if reviewable else None,
        'execution': f'/analysis/{job_id}/execution',
    }
    skipped = {'fo', 'rms'} if job.get('bo_only') else {'bo', 'rms'} if job.get('fo_only') else set()
    return {'job': job, 'current': current, 'tabs': [
        {'key': key, 'label': label, 'href': hrefs[key]} for key, label in ANALYSIS_TABS if key not in skipped]}


def analysis_for(job_id, case_id, run_id, current):
    """The analysis a workbench was opened from (``?job=``), or None when it does not own that run."""
    from app.services import bo_fo
    job = bo_fo.jobs.get(job_id) if job_id else None
    if job is None or job.get('case_id') != case_id:
        return None
    try:
        ids = run_references(job)
    except WorkspaceRecordError:
        return None
    return analysis_tabs(job, current) if ids.get(current) == run_id else None


def report_available(session, bo, fo):
    from app.services.bo.workbench import bo_artifact, BoRunNotFoundError
    memo = None
    if bo:
        for kind in ('memo', 'audit'):
            try:
                report = bo_artifact(session, bo.analysis_run_id, kind)
            except BoRunNotFoundError:
                continue  # Absence is safe; identity/integrity errors must propagate.
            if kind == 'memo':
                memo = report
    return bool(memo or fo)


def governance(session, job, bo, fo, available):
    status = job.get('execution_status', 'completed' if job.get('status') == 'finished' else job.get('status'))
    if status in {'pending', 'running'}:
        return 'Draft'
    if status != 'completed' or not available:
        return 'Unavailable or incomplete'
    from app.core.hashing import content_hash
    from app.services.bo.reporting import handoff_content_hash
    if bo and handoff_content_hash(bo.payload) != bo.content_hash or fo and content_hash(fo.payload) != fo.content_hash:
        return 'Unavailable or incomplete'
    if not job.get('bo_validators', True) or bo and bo.payload.get('validators_enforced', True) is False:
        return 'Human review required · exploratory'
    if bo and bo.payload.get('business_topic_conclusion_id') is None:
        return 'Unavailable or incomplete'
    if bo and bo.human_review_status == 'rejected':
        return 'Rejected · Business Overview'
    if bo and bo.human_review_status == 'accepted' and job.get('bo_only'):
        return 'Approved · Business Overview'
    # Combined approval must be explicitly bound to BOTH selected runs, never just the case.
    if bo and fo:
        for snapshot in session.scalars(select(Snapshot).where(
                Snapshot.case_id == job.get('case_id'), Snapshot.snapshot_type == 'final_case',
                Snapshot.finalized.is_(True))):
            payload = snapshot.payload or {}
            if (snapshot.content_hash == content_hash(payload) and
                    payload.get('accepted_analysis_run_id') == bo.analysis_run_id and
                    (payload.get('financial_analysis') or {}).get('run_id') == fo.run_id):
                return 'Approved'
    if bo and bo.human_review_status == 'accepted':
        return 'Human review required · Business Overview accepted'
    return 'Human review required'


def history(session, jobs, *, search='', status='', mode=''):
    from app.services.pipeline.artifacts import ArtifactIntegrityError
    from app.services.bo.handoff import HandoffError
    from pydantic import ValidationError
    needle = search.strip().casefold()
    rows = []
    for job in sorted(jobs, key=lambda value: value.get('created_at') or value.get('started_at') or '', reverse=True):
        company = (job.get('metadata') or {}).get('company') or job.get('folder') or 'Company not recorded'
        execution = job.get('execution_status') or ('completed' if job.get('status') == 'finished' else job.get('status', 'pending'))
        validation = 'standard' if job.get('bo_validators', True) else 'exploratory'
        try:
            ids = run_references(job)
        except WorkspaceRecordError:
            ids = {}
        search_text = ' '.join([company, job['job_id'], *(value for value in ids.values() if value)])
        if needle and needle not in search_text.casefold():
            continue
        if status and execution != status or mode and validation != mode:
            continue
        available, bo, fo, issue = False, None, None, None
        # Active history never queries uncommitted analytical outputs.
        if execution not in {'pending', 'running'}:
            try:
                bo, fo = selected_rows(session, job)
                available = report_available(session, bo, fo)
            except (WorkspaceRecordError, ArtifactIntegrityError, HandoffError, ValidationError) as exc:
                issue = str(exc)
        path = 'review' if execution == 'completed' and available and not issue else 'execution'
        rows.append(dict(job=job, company=company, execution=execution, mode=validation,
                         date=(job.get('created_at') or job.get('started_at') or 'Not recorded'),
                         governance=governance(session, job, bo, fo, available) if not issue else 'Unavailable or incomplete',
                         href='/analysis/' + quote(job['job_id'], safe='') + '/' + path,
                         issue=issue))
    return rows


def anchor(kind, identifier):
    from hashlib import sha256
    return kind + '-' + sha256(str(identifier).encode()).hexdigest()[:20]


def safe_url(value):
    from urllib.parse import urlsplit
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    from urllib.parse import parse_qsl
    import re
    if any(key.lower() in {'key','auth','sig'} or re.search(r'api[_-]?key|secret|token|password|authorization|credential|signature',key,re.I) for key,_ in parse_qsl(parsed.query)):
        return None
    return value if parsed.scheme in {'http', 'https'} and parsed.netloc and not parsed.username and not parsed.password else None


def load_review(session, job):
    """Load verified frozen BO reports and the exact recorded FO payload; no latest fallback."""
    from app.core.hashing import content_hash
    from app.models.orm import TopicConclusionRow
    from app.services.bo.workbench import bo_artifact, BoRunNotFoundError
    from app.services.bo.handoff import read_handoff
    from app.services.fo.memo import build_memo
    from app.services.fo.review import run_header, review_for, review_view, overrides_for
    bo, fo = selected_rows(session, job)
    out = dict(job=job, bo=bo, fo=fo, memo=None, audit=None, synthesis=None, financial=None,
               consolidated=None, sources=[], recorded_sources=[], reason=None, errors=[], excluded_claim_ids=[],
               governance=governance(session, job, bo, fo, report_available(session, bo, fo)))
    if bo:
        from app.services.bo.consolidated import load
        out['consolidated'] = load(session, bo.case_id, bo.analysis_run_id, bo.snapshot_version)
        if out['consolidated']:
            from app.services.bo.workbench import reviewed_memo
            out['consolidated'] = {**out['consolidated'], 'governance': reviewed_memo(session, bo.analysis_run_id)['status']}
        handoff = read_handoff(session, bo.handoff_id)  # existing typed content-hash integrity guard
        if handoff.analysis_run_id != bo.analysis_run_id or handoff.case_id != bo.case_id or handoff.evidence_snapshot_version != bo.snapshot_version:
            raise WorkspaceRecordError('Handoff identity differs from this selected run.')
        reports = {}
        for kind in ('memo','audit'):
            try:
                reports[kind] = bo_artifact(session, bo.analysis_run_id, kind)
            except BoRunNotFoundError:
                reports[kind] = None
        memo, audit = reports['memo'], reports['audit']
        out.update(memo=memo, audit=audit)
        if not memo or not audit:
            out['reason'] = 'The selected run has no complete recorded memo and audit package.'
            out['governance'] = 'Unavailable or incomplete'
        else:
            # Each available archive was independently checked by bo_artifact,
            # even when the companion is absent. Both are needed for synthesis.
            out.update(memo=memo, audit=audit)
            out['sources'] = [{**source, 'anchor':anchor('source', source.get('evidence_id') or source.get('n')),
                               'href':safe_url(source.get('source_url'))} for source in memo.get('sources') or []]
            out['recorded_sources'] = list(out['sources'])
            cid = bo.payload.get('business_topic_conclusion_id')
            conclusion = session.get(TopicConclusionRow, cid) if cid else None
            frozen = next((c for c in audit.get('conclusions', []) if c.get('conclusion_id') == cid), None)
            rounds = (audit.get('challenger') or {}).get('rounds')
            challenged = next((r for r in reversed(rounds if isinstance(rounds, list) else [])
                               if r.get('conclusion_id') == cid), None)
            enforced = job.get('bo_validators', True) and bo.payload.get('validators_enforced', True)
            if not enforced:
                out['reason'] = 'Exploratory output is ungoverned. Inspect its advisory synthesis in Audit & Review.'
            elif not conclusion or not frozen:
                out['reason'] = 'An accepted synthesis was not recorded.'
            elif (conclusion.analysis_run_id != bo.analysis_run_id or conclusion.case_id != job.get('case_id') or
                  conclusion.snapshot_version != bo.snapshot_version or
                  conclusion.acceptance_state != 'accepted' or frozen.get('acceptance_state') != 'accepted'):
                out['reason'] = 'The recorded conclusion is not an accepted conclusion for this run.'
            elif content_hash(conclusion.payload) != content_hash(frozen.get('payload')):
                raise WorkspaceRecordError('The recorded conclusion differs from its frozen audit artefact.')
            elif not challenged or challenged.get('status') != 'validated':
                out['reason'] = 'A successful independent challenge of this conclusion is not recorded.'
            else:
                payload = frozen['payload']
                if payload.get('analysis_run_id') != bo.analysis_run_id:
                    raise WorkspaceRecordError('The synthesized conclusion belongs to another run.')
                from app.services.analysis_claims import automatic_coverage_ids, ORIGIN_NOTICE
                additions = automatic_coverage_ids(audit, frozen)
                def project(claim):
                    if not isinstance(claim, dict) or not isinstance(claim.get('text'), str) or not claim['text'].strip():
                        return None
                    if claim.get('claim_id') in additions:
                        out['excluded_claim_ids'].append(claim.get('claim_id'))
                        return None
                    evidence_ids = claim.get('evidence_ids') or []
                    return {**claim, 'anchor':anchor('claim',claim.get('claim_id')),
                            'sources':[s for s in out['sources'] if s.get('evidence_id') in evidence_ids],
                            'missing_citations':[eid for eid in evidence_ids if not any(s.get('evidence_id') == eid for s in out['sources'])]}
                synthesis = dict(assessment=project(payload.get('overall_assessment')), strengths=[], weaknesses=[],
                                 integrated=[], origin_notice=ORIGIN_NOTICE)
                for key in ('strengths', 'weaknesses'):
                    synthesis[key] = [view for claim in payload.get(key) or [] if (view := project(claim))]
                for key in ('key_drivers', 'material_risks'):
                    synthesis['integrated'].extend(view for claim in payload.get(key) or [] if (view := project(claim)))
                synthesis['uncertainties'] = list(dict.fromkeys([*(payload.get('open_questions') or []),
                                                                *(payload.get('unresolved_contradictions') or [])]))
                out['synthesis'] = synthesis if synthesis['assessment'] else None
                if out['synthesis'] is None:
                    out['reason'] = ('The recorded overall assessment is an automatic specialist coverage copy.'
                                     if (payload.get('overall_assessment') or {}).get('claim_id') in additions
                                     else 'A usable overall assessment is not recorded in the validated conclusion.')
            selected_claims = ([out['synthesis']['assessment'], *out['synthesis']['strengths'], *out['synthesis']['weaknesses'], *out['synthesis']['integrated']] if out['synthesis'] else [])
            cited_ids = {source.get('evidence_id') for claim in selected_claims for source in claim.get('sources', [])}
            out['sources'] = [source for source in out['sources'] if source.get('evidence_id') in cited_ids]
            if out['synthesis'] is None:
                out['governance'] = 'Unavailable or incomplete' if enforced else 'Human review required · exploratory'
    else:
        out['reason'] = 'No Business Overview report is recorded for this selected job.'
    if fo and not job.get('bo_only'):
        if content_hash(fo.payload) != fo.content_hash:
            raise WorkspaceRecordError('Financial Overview payload failed its recorded integrity check.')
        out['financial'] = build_memo(dict(fo.payload), run=run_header(fo),
                                      review=review_view(review_for(session, fo.run_id)),
                                      overrides=overrides_for(session, fo.run_id), source=None)
    return out
