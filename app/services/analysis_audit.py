"""Exact-run, read-only audit projection over existing frozen artefacts and run logs."""
import copy
import json
import re
from collections import defaultdict
from sqlalchemy import select
from app.models.orm import AgentRunRow, HypothesisRecordRow
from app.services.analysis_workspace import anchor, safe_url, WorkspaceRecordError
from app.services.pipeline.artifacts import verified_artifacts
from app.core.hashing import content_hash

_SECRET_KEY = re.compile(r'(?:api[_-]?key|password|secret|authorization|credentials|access[_-]?token|refresh[_-]?token|private[_-]?key|client[_-]?secret)', re.I)


def public_record(value, _secrets=None):
    """Redact credentials from display copies; never mutate the canonical record."""
    if _secrets is None:
        from app.core.config import get_settings
        settings = get_settings()
        _secrets = tuple(credential.get_secret_value() for name in type(settings).model_fields
                         if _SECRET_KEY.search(name) and hasattr((credential := getattr(settings, name)), 'get_secret_value')
                         and len(credential.get_secret_value()) >= 6)
    if isinstance(value, dict):
        return {key: '[REDACTED]' if _SECRET_KEY.search(str(key)) or str(key).lower() == 'token' else public_record(item, _secrets)
                for key,item in value.items()}
    if isinstance(value, list):
        return [public_record(item, _secrets) for item in value]
    if isinstance(value, str):
        for secret in _secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[REDACTED PRIVATE KEY]', value, flags=re.S)
        value = re.sub(r'\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]', value, flags=re.I)
        value = re.sub(r'\b(?:AIza[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{16,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b', '[REDACTED]', value)
        value = re.sub(r'((?:[A-Za-z0-9_-]*(?:api[_-]?key|password|secret|authorization|credentials|access[_-]?token|refresh[_-]?token)|[?&]token)["\s]*[:=]["\s]*)([^\s,"&}]+)', r'\1[REDACTED]', value, flags=re.I)
        return value
    return value


def raw_output(value):
    if not value:
        return 'Not recorded'
    try:
        return json.dumps(public_record(json.loads(value)), ensure_ascii=False, indent=2)
    except (ValueError, TypeError):
        return public_record(value)


def build_audit(session, view):
    job, bo = view['job'], view['bo']
    if not bo or not view['audit']:
        return dict(hypotheses=[], agents=[], specialists=[], validators=[], synthesizers=[], challengers=[],
                    evidence=[], documents=[], conclusions=[], claims=[], modules={},
                    validator_records={}, challenge={}, remediation='Not recorded', record=None, rejected_sources=[], synthesis_history='Not recorded', management_claims=[], calculations=[], parameters=[])
    audit = view['audit']
    run_id = bo.analysis_run_id
    runs = list(session.scalars(select(AgentRunRow).where(
        AgentRunRow.analysis_run_id == run_id).order_by(AgentRunRow.created_at)))
    if any(row.case_id != job.get('case_id') or row.snapshot_version != bo.snapshot_version for row in runs):
        raise WorkspaceRecordError('Agent logs do not match the selected run and evidence version.')
    def family(agent):
        return 'synthesizer' if 'orchestrat' in agent else 'challenger' if 'challenge' in agent else 'validator' if 'validator' in agent else 'specialist'
    agents = []
    by_run = {}
    for row in runs:
        by_run[row.run_id] = row
        agents.append(public_record(dict(agent_id=row.agent_id, run_id=row.run_id, family=family(row.agent_id),
            status=row.validation_status, detail=row.validation_detail, error=row.error_state,
            rerun_reason=row.rerun_reason, raw=raw_output(row.raw_response), parsed=row.parsed_response,
            evidence_ids=row.input_evidence_ids, parent_run_ids=row.parent_run_ids,
            reused_from_cache=row.reused_from_cache, created_at=row.created_at.isoformat(), usage=row.usage)))
    records = {row.id:row for row in session.scalars(select(HypothesisRecordRow).where(
        HypothesisRecordRow.analysis_run_id == run_id))}
    findings = []
    for item in (audit.get('hypotheses') or {}).get('records') or []:
        item = copy.deepcopy(item)
        row = records.get(item.get('record_id'))
        original = None
        if row is not None:
            if row.case_id != job.get('case_id') or row.snapshot_version != bo.snapshot_version:
                raise WorkspaceRecordError('A specialist record belongs to another evidence version.')
            raw = by_run.get(row.agent_run_id)
            if raw and raw.raw_response:
                try:
                    original_response = json.loads(raw.raw_response)
                except (ValueError, TypeError):
                    original_response = {}
                if isinstance(original_response, dict):
                    original = next((h.get('claim') for h in original_response.get('hypotheses') or []
                                     if isinstance(h, dict) and h.get('hypothesis_id') == item.get('hypothesis_id')), None)
        item.update(anchor=anchor('finding', item.get('hypothesis_id')),
                    version_anchor=anchor('version',item.get('record_id') or len(findings)),
                    original_claim=original or (item.get('model_stated') or {}).get('claim') or 'Not recorded')
        findings.append(item)
    grouped = defaultdict(list)
    for item in findings:
        grouped[item.get('hypothesis_id') or 'Not recorded'].append(public_record(item))

    canonical = None
    for record in verified_artifacts(session, bo.case_id, bo.snapshot_version):
        if record.name == 'canonical_evidence':
            canonical = json.loads(record.payload_json)
            expected = (audit.get('evidence_snapshot') or {}).get('content_hash')
            if expected and content_hash(canonical) != expected:
                raise WorkspaceRecordError('The canonical evidence differs from this audit snapshot.')
    documents = {document.get('document_id'):document for document in (canonical or {}).get('documents') or []}
    for document in (audit.get('sources') or {}).get('documents') or []:
        documents.setdefault(document.get('document_id'),document)
    evidence = {}
    for passage in (canonical or {}).get('narrative_evidence') or []:
        eid = passage.get('evidence_id')
        document = documents.get(passage.get('document_id')) or {}
        evidence[eid] = {**document, **passage, 'existence':'Recorded in the selected evidence snapshot',
                         'excerpt':passage.get('text'), 'quotes':[]}
    for source in view.get('recorded_sources', view['sources']):
        eid = source.get('evidence_id')
        evidence.setdefault(eid, {**source, 'existence':'Citation recorded; full snapshot passage not recorded', 'quotes':[]})
    def reference(eid):
        if eid not in evidence:
            evidence[eid] = dict(evidence_id=eid, existence='Reference only; source passage not recorded', quotes=[])
        return evidence[eid]
    for finding in findings:
        for eid in [*(finding.get('supporting_evidence_ids') or []), *(finding.get('contradicting_evidence_ids') or [])]:
            reference(eid)
        for quote in finding.get('evidence_quotes') or []:
            reference(quote.get('evidence_id'))['quotes'].append(dict(
                quote=quote.get('quote'), hypothesis_id=finding.get('hypothesis_id'),
                verification=quote.get('verification_status') if quote.get('verification_status') is not None else 'Not recorded',
                entailment=quote.get('entailment_state') or finding.get('entailment_state') or 'Not recorded',
                finding_disposition=finding.get('disposition', 'Not recorded'),
                admissibility=finding.get('admissibility', 'Not recorded'),
                evidence_basis=finding.get('evidence_basis', 'Not recorded')))
    claims = []
    from app.services.bo.synthesis import iter_claims
    from app.services.analysis_claims import automatic_coverage_ids
    for conclusion in audit.get('conclusions') or []:
        additions = automatic_coverage_ids(audit, conclusion)
        for category, claim in iter_claims(conclusion.get('payload') or {}):
            item = {**claim, 'category':category, 'conclusion_id':conclusion.get('conclusion_id'),
                    'automatic_coverage':claim.get('claim_id') in additions,
                    'record_state':conclusion.get('acceptance_state'),
                    'anchor':anchor('claim', str(conclusion.get('conclusion_id'))+':'+str(claim.get('claim_id'))),
                    'hypotheses':[dict(hypothesis_id=hid, href='#'+anchor('finding',hid) if hid in grouped else None)
                                  for hid in claim.get('hypothesis_ids') or []]}
            for eid in claim.get('evidence_ids') or []:
                reference(eid)
            claims.append(public_record(item))
    for packet in audit.get('evidence_packets') or []:
        for item in packet.get('evidence') or []:
            source = reference(item.get('evidence_id'))
            for key in ('filename','section','location'):
                if not source.get(key):source[key] = item.get(key)
    calculations = [{**item, 'anchor':anchor('calculation', item.get('parameter_result_id'))} for item in audit.get('calculations') or []]
    sources = []
    for eid,source in evidence.items():
        sources.append(public_record({**source, 'evidence_id':eid, 'anchor':anchor('evidence',eid),
                                      'href':safe_url(source.get('source_url'))}))
    challenge = public_record(audit.get('challenger') or {})
    if isinstance(challenge.get('rounds'), list):
        for round in challenge['rounds']:
            for finding in round.get('findings') or []:
                target = next((claim for claim in claims if claim.get('claim_id') == finding.get('target')
                               and claim.get('conclusion_id') == round.get('conclusion_id')), None)
                finding['target_href'] = '#'+target['anchor'] if target else None
    return dict(hypotheses=[dict(hypothesis_id=hid,anchor=anchor('finding',hid),versions=versions)
                             for hid,versions in grouped.items()],
                agents=agents, specialists=[a for a in agents if a['family']=='specialist'],
                validators=[a for a in agents if a['family']=='validator'],
                synthesizers=[a for a in agents if a['family']=='synthesizer'],
                challengers=[a for a in agents if a['family']=='challenger'],
                evidence=sources, documents=public_record(list(documents.values())),
                conclusions=public_record(audit.get('conclusions') or []), claims=claims,
                modules=public_record(audit.get('module_conclusions') or {}),
                validator_records=public_record(dict(agents=audit.get('agents') or [],
                    reconciliation=audit.get('reconciliation') or {},
                    coverage=audit.get('module_conclusions') or {},
                    retrieval=audit.get('retrieval') or {},
                    execution=audit.get('execution') or {})),
                synthesis_history=public_record((audit.get('orchestrator') or {}).get('history') or 'Not recorded'),
                management_claims=public_record(audit.get('management_claims') or []),
                calculations=public_record(calculations), parameters=public_record(audit.get('parameters') or []),
                challenge=challenge,
                remediation=public_record(audit.get('rerun') or 'Not recorded'),
                rejected_sources=public_record((audit.get('sources') or {}).get('rejected_sources') or []),
                record=public_record(audit.get('final_conclusion')))
