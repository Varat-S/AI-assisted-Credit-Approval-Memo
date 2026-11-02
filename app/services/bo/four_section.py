"""Deterministic assembly from frozen exact-run sources, never from local files.

Root chain/identity failures raise ArtifactIntegrityError. Component failures
produce an unavailable block; other verified components remain usable. This
module never calls specialist validators, providers, acquisition or retrieval.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
import re

import jsonschema
from sqlalchemy import select

from app.core.hashing import canonical_json, content_hash
from app.models.orm import AcceptedBusinessOverviewRow, AgenticAnalysisRun, AgentRunRow, TopicConclusionRow, ModelRun
from app.prompts.competitive_positioning import OUTPUT_VERSION, POLICY_VERSION
from app.prompts import source_selection
from app.schemas.bo_four_section import (
    DOCUMENT, SCHEMA_VERSION, ASSEMBLER_VERSION, PROVENANCE_VERSION, FILENAME,
    SECTION_TITLES, FOUR_SECTION_SCHEMA,
)
from app.services.pipeline.artifacts import ArtifactIntegrityError, StageRecorder, verified_artifacts

CONTRACT_POLICIES = {OUTPUT_VERSION: POLICY_VERSION, 'bo-source-selection-output-1.0.0': 'bo-source-selection-1.0.0', source_selection.OUTPUT_VERSION: source_selection.POLICY_VERSION}

PATHS = {
    'structure': '/module_conclusions/M3/m3_rebuild/structure/artifact',
    'management': '/module_conclusions/M3/m3_rebuild/management/artifact',
    'debt': '/module_conclusions/M4/m4_analysis/deliverable_1',
    'industry': '/module_conclusions/M2/findings',
}


def stage_name(run_id):
    return 'bo_four_section_memo:' + run_id


def provenance_stage(run_id):
    return 'bo_assembly_provenance:' + run_id


def _require(condition, reason):
    if not condition:
        raise ArtifactIntegrityError(reason)


def _at(root, pointer):
    value = root
    for token in pointer.strip('/').split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _company(value):
    tokens = re.findall(r'[a-z0-9]+', (value or '').casefold())
    while tokens and tokens[-1] in {'inc', 'incorporated', 'corp', 'corporation', 'llc', 'ltd'}:
        tokens.pop()
    return tokens


def _same_time(left, right):
    if left is None or right is None:
        return left is right
    return datetime.fromisoformat(left.replace('Z', '+00:00')) == datetime.fromisoformat(right.replace('Z', '+00:00'))


def _root_identity(audit):
    case = audit['case']
    return {'case_id': case['case_id'], 'analysis_run_id': audit['run']['analysis_run_id'],
            'evidence_snapshot_version': case['evidence_snapshot_version'],
            'evidence_snapshot_hash': audit['evidence_snapshot']['content_hash'],
            'reporting_company': case.get('borrower'), 'as_of_date': case.get('as_of_date'),
            'evidence_cutoff_timestamp': case.get('evidence_cutoff')}


def capture_provenance(run, audit, audit_hash):
    """Reporting-time freeze of already-produced bindings, not a validator run."""
    root = _root_identity(audit)
    bindings = {}
    for key, path in PATHS.items():
        try:
            value = _at(audit, path)
        except (KeyError, IndexError, TypeError):
            continue
        bindings[key] = {'identity': deepcopy(root), 'source_path': path,
                         'content_hash': content_hash(value)}
    producers = []
    for row in run.session.scalars(select(AgentRunRow).where(
            AgentRunRow.analysis_run_id == run.analysis_run_id).order_by(AgentRunRow.created_at, AgentRunRow.run_id)).all():
        producers.append({'agent_id': row.agent_id, 'agent_run_id': row.run_id,
                          'analysis_run_id': row.analysis_run_id, 'case_id': row.case_id,
                          'snapshot_version': row.snapshot_version,
                          'validation_status': row.validation_status})
    packet = run.m3_packet.model_dump(mode='json') if run.m3_packet is not None else None
    debt_id = getattr(run.m4_debt_result, 'run_id', None)
    debt_run = run.session.get(ModelRun, debt_id) if debt_id else None
    return {'schema_version': PROVENANCE_VERSION, 'identity': root, 'audit_sha256': audit_hash,
            'component_bindings': bindings, 'm3_packet': packet, 'producer_records': producers,
            'm3_source_run_id': (audit.get('module_conclusions', {}).get('M3') or {}).get('source_run_id'),
            'm4_producer_run_id': getattr(run.m4_debt_result, 'run_id', None),
            'm4_producer_record': {'run_id': debt_run.run_id, 'case_id': debt_run.case_id,
                                   'snapshot_version': debt_run.case_version,
                                   'validation_status': debt_run.validation_outcome} if debt_run else None,
            'governance': {'conclusion_status': run.conclusion_status, 'validators_enforced': run.enforce_validators,
                           'execution_mode': audit['run']['execution_mode'], 'human_review_status': 'pending'}}


@dataclass(frozen=True)
class SavedInputs:
    audit: dict
    snapshot: dict
    provenance: dict
    handoff: dict
    audit_hash: str
    snapshot_hash: str
    provenance_hash: str
    current_conclusion: dict | None


def load_saved_inputs(session, analysis_run_id, *, handoff_payload=None):
    """Read only explicit stage/run IDs; no latest query or file fallback."""
    run = session.get(AgenticAnalysisRun, analysis_run_id)
    _require(run is not None, 'Selected BO run does not exist.')
    if handoff_payload is None:
        rows = list(session.scalars(select(AcceptedBusinessOverviewRow).where(
            AcceptedBusinessOverviewRow.analysis_run_id == analysis_run_id)))
        _require(len(rows) == 1, 'Selected BO handoff is missing or ambiguous.')
        row = rows[0]
        _require(row.case_id == run.case_id and row.snapshot_version == run.evidence_snapshot_version,
                 'Selected handoff root differs from the BO run.')
        _require(type(row.payload.get('evidence_snapshot_version')) is int,
                 'Selected handoff snapshot version has an invalid type.')
        from app.services.bo.handoff import read_handoff
        handoff_payload = read_handoff(session, row.handoff_id).model_dump(mode='json')
    from app.services.bo.reporting import handoff_content_hash
    _require(handoff_payload.get('content_hash') == handoff_content_hash(handoff_payload),
             'Selected handoff content hash is invalid.')
    _require(handoff_payload.get('analysis_run_id') == analysis_run_id
             and handoff_payload.get('case_id') == run.case_id
             and handoff_payload.get('evidence_snapshot_version') == run.evidence_snapshot_version,
             'Selected handoff has an invalid root identity.')
    stages = {r.name: r for r in verified_artifacts(session, run.case_id, run.evidence_snapshot_version)}
    required = ['bo_audit:' + analysis_run_id, 'canonical_evidence', provenance_stage(analysis_run_id)]
    _require(all(name in stages for name in required), 'Frozen exact-run assembly sources are unavailable; no backfill is performed.')
    a, s, p = (stages[name] for name in required)
    audit, snapshot, provenance = (json.loads(r.payload_json) for r in (a, s, p))
    _require(audit.get('document') == 'business_overview_audit_report' and audit.get('version') == 'bo-audit-1.0',
             'Frozen audit root document is invalid.')
    try:
        identity = _root_identity(audit)
        borrower = next((e for e in snapshot.get('entities', []) if e.get('borrower_flag')), {})
        _require(identity['analysis_run_id'] == analysis_run_id and identity['case_id'] == run.case_id
                 and type(identity['evidence_snapshot_version']) is int
                 and identity['evidence_snapshot_version'] == run.evidence_snapshot_version,
                 'Frozen audit root belongs to a different case/run/snapshot.')
        _require(type(snapshot['snapshot_version']) is int
                 and snapshot['case_id'] == run.case_id and snapshot['snapshot_version'] == run.evidence_snapshot_version
                 and audit['evidence_snapshot']['case_id'] == run.case_id
                 and audit['evidence_snapshot']['snapshot_version'] == run.evidence_snapshot_version
                 and identity['evidence_snapshot_hash'] == s.sha256,
                 'Frozen audit and canonical evidence snapshot differ.')
        _require(identity['as_of_date'] == snapshot.get('as_of_date') == handoff_payload.get('as_of_date')
                 and _same_time(identity['evidence_cutoff_timestamp'], snapshot.get('evidence_cutoff_timestamp'))
                 and _same_time(identity['evidence_cutoff_timestamp'], handoff_payload.get('evidence_cutoff_timestamp'))
                 and _company(identity['reporting_company']) == _company(borrower.get('legal_name'))
                 == _company(handoff_payload.get('borrower_name')),
                 'Frozen root company, filing period or cutoff differs.')
        _require(provenance['schema_version'] == PROVENANCE_VERSION and provenance['identity'] == identity
                 and provenance['audit_sha256'] == a.sha256,
                 'Frozen assembly provenance does not bind this audit root.')
        _require((run.model_configuration or {}).get('business_orchestrator_contract') in CONTRACT_POLICIES,
                 'This run did not opt into the Milestone 2 contract.')
        if (run.model_configuration or {}).get('business_orchestrator_contract') == source_selection.OUTPUT_VERSION:
            _require(run.model_configuration.get('independent_business_challenge_enabled') is False,
                     'Source selection run lacks its explicit disabled-challenge setting.')
    except (KeyError, TypeError, StopIteration, ValueError, AttributeError) as exc:
        raise ArtifactIntegrityError('Frozen root identity is malformed.') from exc
    cid = handoff_payload.get('business_topic_conclusion_id')
    row = session.get(TopicConclusionRow, cid) if cid else None
    conclusion = ({'conclusion_id': row.id, 'analysis_run_id': row.analysis_run_id, 'case_id': row.case_id,
                   'snapshot_version': row.snapshot_version, 'acceptance_state': row.acceptance_state,
                   'orchestrator_run_id': row.orchestrator_run_id, 'payload': deepcopy(row.payload)} if row else None)
    return SavedInputs(audit, snapshot, provenance, deepcopy(handoff_payload), a.sha256, s.sha256, p.sha256, conclusion)


class _Assembler:
    def __init__(self, saved):
        self.s = saved
        self.audit, self.prov = saved.audit, saved.provenance
        self.root = _root_identity(self.audit)
        self.modules = self.audit.get('module_conclusions') or {}
        self.sources = []
        self.admitted = {p.get('evidence_id') for p in saved.snapshot.get('narrative_evidence', [])}
        self.admitted.update(f.get('fact_id') or f.get('id') for f in saved.snapshot.get('facts', []))

    def check_binding(self, key):
        binding = self.prov['component_bindings'][key]
        _require(binding['identity'] == self.root and binding['source_path'] == PATHS[key],
                 f'{key}: component identity differs from the selected root.')
        value = _at(self.audit, binding['source_path'])
        _require(content_hash(value) == binding['content_hash'], f'{key}: component content hash mismatch.')
        return value

    def ref(self, key, path, value):
        self.sources.append({'artifact_id': key, 'stage_name': 'bo_audit:' + self.root['analysis_run_id'],
                             'source_path': path, 'sha256': self.s.audit_hash, 'content_hash': content_hash(value),
                             'hash_kind': 'canonical_stage', 'binding': 'same_run_verified'})
        return key

    def producer(self, agent, run_id=None):
        candidates = [p for p in self.prov['producer_records'] if p['agent_id'] == agent
                      and (run_id is None or p['agent_run_id'] == run_id)]
        _require(bool(candidates), f'{agent}: recorded producer is unavailable.')
        p = candidates[-1]
        _require(p['analysis_run_id'] == self.root['analysis_run_id'] and p['case_id'] == self.root['case_id']
                 and p['snapshot_version'] == self.root['evidence_snapshot_version']
                 and p['validation_status'] == 'valid', f'{agent}: producer identity/validation mismatch.')
        return p

    def block(self, key, fn):
        block = {'status': 'unavailable', 'recorded_status': None, 'validation_status': None,
                 'source_ref': None, 'content': None, 'visible_warnings': []}
        if key == 'competitive_positioning':
            block.update(editorial_selection=None, selection_source_ref=None, challenge_source_ref=None)
        start = len(self.sources)
        try:
            _require(self.prov['governance']['validators_enforced'] is True,
                     'Exploratory output is ungoverned; eligible source content is unavailable.')
            fn(block)
        except (ArtifactIntegrityError, KeyError, IndexError, TypeError, ValueError, AttributeError, StopIteration) as exc:
            del self.sources[start:]
            reason = f'Missing recorded source field {exc}; no fallback was used.' if isinstance(exc, KeyError) else str(exc)
            block.update(status='unavailable', source_ref=None, content=None,
                         visible_warnings=[f'{key}: {reason}'])
            if key == 'competitive_positioning':
                block.update(editorial_selection=None, selection_source_ref=None, challenge_source_ref=None)
        return block

    def module_context(self, module):
        for field, expected in self.root.items():
            if field in module:
                _require(module[field] == expected, f'Module {field} does not match the selected root.')
        if 'filing_period' in module:
            _require(module['filing_period'] == self.root['as_of_date'], 'Module filing period differs.')

    def m3(self, key, block):
        module = self.modules['M3']
        self.module_context(module)
        _require(module.get('workflow') == 'm3-rebuild' and module.get('schema_version') == 'm3-rebuild-handoff-1.0',
                 'Unsupported M3 source contract.')
        component = module['m3_rebuild'][key]
        block.update(recorded_status=component.get('status'), validation_status=component.get('validation_status'))
        _require(component.get('status') in {'complete', 'partial'}
                 and component.get('validation_status') in {'passed', 'partial'},
                 component.get('error') or 'M3 component is missing or not validated.')
        value = self.check_binding(key)
        _require(isinstance(value, dict) and value.get('completion_status') == component['status'],
                 'M3 artifact and recorded component status differ.')
        packet = self.prov['m3_packet']
        _require(isinstance(packet, dict), 'The exact-run M3 source packet was not recorded.')
        body = {k: v for k, v in packet.items() if k != 'packet_hash'}
        _require(content_hash(body) == packet.get('packet_hash')
                 and packet['analysis_run_id'] == self.root['analysis_run_id']
                 and packet['case_id'] == self.root['case_id']
                 and packet['snapshot_version'] == self.root['evidence_snapshot_version'],
                 'M3 packet hash/case/run/snapshot mismatch.')
        context = packet['context']
        _require(_company(context['company']) == _company(self.root['reporting_company'])
                 and context['filing_period'] == self.root['as_of_date']
                 and _same_time(context['evidence_cutoff_timestamp'], self.root['evidence_cutoff_timestamp'])
                 and module['source_run_id'] == self.prov['m3_source_run_id'], 'M3 source context/run mismatch.')
        docs = {d['document_id']: d for d in self.s.snapshot.get('documents', [])}
        warnings = list(module.get('missing_information') or [])
        if key == 'structure':
            _require(value.get('schema_version') == '2.0', 'Unsupported M3 structure artifact.')
            company = next(iter(value['companies'].values()))
            _require(_company(company['company_display_name']) == _company(self.root['reporting_company']),
                     'Corporate structure belongs to another company.')
            prov = value['provenance']
            doc = docs[context['corporate_document_id']]
            _require(prov['input_document_id'] == doc['document_id'] and prov['source_sha256'] == doc['sha256']
                     and prov['canonical_snapshot_version'] == self.root['evidence_snapshot_version']
                     and prov['evidence_packet_hash'] == packet['packet_hash'], 'Structure source document/packet mismatch.')
            warnings.append(value['simulation_disclaimer'])
        else:
            _require(value.get('schema_version') == 'm3-management-assessment-3.0',
                     'A reviewed M3 management 3.0 artifact is not recorded.')
            self.producer('m3_management_assessment')
            self.producer('m3_validator_7')
            doc = docs[context['management_document_id']]
            _require(_company(value['company']) == _company(self.root['reporting_company'])
                     and value['filing_period'] == self.root['as_of_date']
                     and value['source']['sha256'] == doc['sha256']
                     and value['source']['path'].split(':', 1)[-1] == doc['document_id'],
                     'Management company/period/source document mismatch.')
            _require(not value.get('roster_date') or not self.root['evidence_cutoff_timestamp']
                     or value['roster_date'] <= self.root['evidence_cutoff_timestamp'][:10],
                     'Management roster is later than the evidence cutoff.')
            _require((component['status'] == 'partial' or value['validation']['overall_references_valid'] is True)
                     and all(o.get('review_outcome') in {'accepted', 'qualified'} for o in value['observations']),
                     'Management reviewed judgments are not eligible.')
            _require(set(value['source']['section_ids']) <= set(packet['evidence_ids']),
                     'Management source passages are outside its selected packet.')
            warnings.extend(value.get('limitations') or [])
        block.update(status='complete' if component['status'] == 'complete' else 'partial',
                     source_ref=self.ref(key, PATHS[key], value), content=deepcopy(value), visible_warnings=warnings)

    def industry(self, block):
        module = self.modules['M2']
        self.module_context(module)
        block.update(recorded_status=module.get('status'), validation_status='recorded')
        findings = self.check_binding('industry')
        _require(module.get('module') == 'M2' and isinstance(findings, list) and findings,
                 'No governed M2 industry findings are available.')
        records = [h for h in self.audit['hypotheses']['records'] if h.get('acceptance_state') == 'accepted']
        for f in findings:
            matches = [h for h in records if h['hypothesis_id'] == f['hypothesis_id'] and h['agent_id'] == 'm2_industry']
            _require(len(matches) == 1, 'M2 finding lacks an unambiguous canonical source record.')
            h = matches[0]
            _require(h['analysis_run_id'] == self.root['analysis_run_id'] and h['disposition'] in {'supported', 'qualified'}
                     and h['admissibility'] != 'audit_only' and h.get('validator_id') == 'validator_6'
                     and all(k in h and h[k] == v for k, v in f.items()), 'M2 finding identity/content/validation mismatch.')
            self.producer('m2_industry', h['agent_run_id'])
            _require(set(f['supporting_evidence_ids'] + f['contradicting_evidence_ids']) <= self.admitted,
                     'M2 evidence references are outside the selected snapshot.')
        block.update(status='complete' if module['status'] == 'complete' else 'partial',
                     source_ref=self.ref('industry', PATHS['industry'], findings),
                     content={'findings': deepcopy(findings)},
                     visible_warnings=list(module.get('missing_information') or []))
        if module['status'] != 'complete':
            block['visible_warnings'].append('M2 source coverage is incomplete; this is not a complete industry assessment.')
        for f in findings:
            block['visible_warnings'].extend(f.get('missing_information') or [])
            if f['admissibility'] in {'qualified_narrative', 'attributed'}:
                block['visible_warnings'].append(f"{f['hypothesis_id']}: preserve {f['admissibility']} qualification/attribution.")

    def debt(self, block):
        module = self.modules['M4']
        self.module_context(module)
        debt = module['m4_debt_assessment']
        block.update(recorded_status=debt.get('status'), validation_status='passed' if debt.get('validated') else 'failed')
        _require(module.get('m4_debt_status') == 'validated' and debt.get('status') == 'validated'
                 and debt.get('validated') is True and debt.get('validator_id') == 'validator_8_debt_structure',
                 debt.get('reason') or 'M4 debt output did not validate.')
        report = debt['validator_report']
        expected_checks = {'V8-01-RECONCILIATION', 'V8-02-SUBORDINATION-RATIO', 'V8-03-MATURITY-ORDER',
                           'V8-04-LEGAL-ENTITY', 'V8-05-DOUBLE-COUNTING', 'V8-06-RECONCILING-ITEMS'}
        _require(report.get('passed') is True and len(report.get('checks', [])) >= 6
                 and expected_checks <= {c.get('check_id') for c in report['checks']}
                 and all(c.get('passed') is True for c in report['checks']), 'M4 recorded Validator 8 checks did not pass.')
        _require(self.prov.get('m4_producer_run_id'), 'M4 debt producer identity was not recorded.')
        producer = self.prov['m4_producer_record']
        _require(producer and producer['run_id'] == self.prov['m4_producer_run_id']
                 and producer['case_id'] == self.root['case_id']
                 and producer['snapshot_version'] == self.root['evidence_snapshot_version']
                 and producer['validation_status'] == 'valid', 'M4 producer source case/snapshot/validation differs.')
        _require(set(debt['evidence_ids']) <= self.admitted and debt['evidence_ids'],
                 'M4 evidence references are outside the selected snapshot.')
        value = self.check_binding('debt')
        _require(canonical_json(value) == canonical_json(debt['assessment']['deliverable_1']),
                 'M4 assembled D1 differs from the validated debt assessment.')
        target = debt['assessment']['deliverable_4']['executive_credit_summary_box']['target_entity_and_period']
        _require(set(_company(self.root['reporting_company'])) <= set(_company(target))
                 and self.root['as_of_date'][:4] in target, 'M4 reporting company/period does not match the selected run.')
        block.update(status='complete', source_ref=self.ref('debt', PATHS['debt'], value), content=deepcopy(value),
                     visible_warnings=list(module.get('missing_information') or []) +
                     ['Debt population is preserved as supplied; recorded validation does not establish completeness beyond source scope.'])
        if not value['senior_notes_schedule'] and not value['non_note_obligations_schedule']:
            block['status'] = 'partial'
            block['visible_warnings'].append('No obligation rows were supplied; this is not evidence of zero debt.')

    def competitive(self, block):
        block.update(editorial_selection=None, selection_source_ref=None, challenge_source_ref=None)
        cid = self.s.handoff.get('business_topic_conclusion_id')
        current = self.s.current_conclusion
        _require(cid and current, 'No selected current Competitive Positioning conclusion is recorded.')
        _require(current['analysis_run_id'] == self.root['analysis_run_id'] and current['case_id'] == self.root['case_id']
                 and current['snapshot_version'] == self.root['evidence_snapshot_version']
                 and current['acceptance_state'] == 'accepted', 'Current conclusion belongs to another run or is not accepted.')
        candidates = [(i, c) for i, c in enumerate(self.audit['conclusions']) if c['conclusion_id'] == cid]
        _require(len(candidates) == 1, 'The exact conclusion is absent or ambiguous in the frozen audit.')
        index, item = candidates[0]
        _require(item['acceptance_state'] == 'accepted' and item['orchestrator_run_id'] == current['orchestrator_run_id']
                 and canonical_json(item['payload']) == canonical_json(current['payload']),
                 'Current conclusion differs from the frozen accepted conclusion.')
        selection = self.audit['orchestrator']['editorial_selection']
        _require(self.s.handoff['canonical_references'].get('business_orchestrator_contract') in CONTRACT_POLICIES
                 and selection['schema_version'] == self.s.handoff['canonical_references']['business_orchestrator_contract']
                 and selection['policy_version'] == CONTRACT_POLICIES[selection['schema_version']]
                 and selection['conclusion_id'] == cid and selection['orchestrator_run_id'] == current['orchestrator_run_id']
                 and content_hash(selection) == self.s.handoff['canonical_references'].get('editorial_selection_hash'),
                 'Milestone 2 selection-ledger identity/hash mismatch.')
        self.producer('business_orchestrator', current['orchestrator_run_id'])
        challenge = self.audit['challenger']
        rounds = challenge['rounds']
        no_challenge = selection['schema_version'] == source_selection.OUTPUT_VERSION
        if no_challenge:
            _require(self.s.handoff['canonical_references'].get('independent_business_challenge_enabled') is False
                     and challenge.get('status') == 'disabled_by_workflow'
                     and challenge.get('policy_version') == source_selection.POLICY_VERSION
                     and challenge.get('conclusion_id') == cid
                     and challenge.get('editorial_selection_hash') == content_hash(selection)
                     and rounds == 'not_executed'
                     and current['payload']['challenge_status'] == 'not_performed',
                     'Disabled challenge policy is not bound to this exact conclusion/ledger.')
            round_ = {'outcome': 'not_performed', 'findings': []}
        else:
            _require(isinstance(rounds, list) and rounds, 'No independent challenge is recorded.')
            round_ = rounds[-1]
            _require(round_['conclusion_id'] == cid and round_['status'] == 'validated'
                     and round_['editorial_selection'] == selection, 'Independent challenge is not bound to this exact conclusion/ledger.')
            self.producer('business_challenge', round_['agent_run_id'])
            _require(round_['editorial_review']['economic_support_reviewed'] is True
                     and round_['editorial_review']['material_omissions_reviewed'] is True,
                     'Independent editorial review is not recorded.')
        value = item['payload']
        _require(value['analysis_run_id'] == self.root['analysis_run_id'], 'Conclusion payload has a foreign run identity.')
        m1 = self.modules.get('M1') or {}
        self.module_context(m1)
        block.update(status='complete' if (self.modules.get('M1') or {}).get('status') == 'complete'
                     and round_['outcome'] in {'accepted', 'accepted_with_qualification', 'not_performed'} else 'partial',
                     recorded_status=self.prov['governance']['conclusion_status'], validation_status=round_['outcome'],
                     source_ref=self.ref('competitive_positioning', f'/conclusions/{index}/payload', value),
                     content=deepcopy(value), editorial_selection=deepcopy(selection),
                     selection_source_ref=self.ref('editorial_selection', '/orchestrator/editorial_selection', selection),
                     challenge_source_ref=(self.ref('challenge_policy', '/challenger', challenge) if no_challenge else
                                           self.ref('independent_challenge', f'/challenger/rounds/{len(rounds)-1}', round_)),
                     visible_warnings=[*(['Independent challenge was not performed under this workflow. Human review remains required.'] if no_challenge else []),
                                       *value.get('open_questions', []), *value.get('unresolved_contradictions', []),
                                       *((self.modules.get('M1') or {}).get('missing_information') or []),
                                       *(f['reason'] for f in round_['findings'] if f['severity'] in {'medium', 'high', 'material'})])
        if block['status'] == 'partial':
            block['visible_warnings'].append('Module 1 coverage remains incomplete.' if no_challenge else
                                            'Module 1 coverage or independent challenge remains incomplete or unresolved.')
        for h in self.audit['hypotheses']['records']:
            if h.get('section', '').startswith('M1') and (h.get('presentation_basis') or {}).get('open_question'):
                block['visible_warnings'].append('Unverified material information gap: ' + h['claim'])


def assemble(saved):
    """Pure transformation of detached verified saved inputs. No clocks or I/O."""
    _require(content_hash(saved.audit) == saved.audit_hash and content_hash(saved.snapshot) == saved.snapshot_hash
             and content_hash(saved.provenance) == saved.provenance_hash,
             'Saved assembly input hashes do not verify.')
    # Keep the pure transformation safe even when detached inputs have been
    # copied/edited after loading. Component-level metadata is checked below.
    try:
        root = _root_identity(saved.audit)
        borrower = next((e for e in saved.snapshot.get('entities', []) if e.get('borrower_flag')), {})
        _require(saved.audit.get('document') == 'business_overview_audit_report'
                 and saved.audit.get('version') == 'bo-audit-1.0'
                 and saved.provenance.get('schema_version') == PROVENANCE_VERSION
                 and saved.provenance['identity'] == root
                 and saved.provenance['audit_sha256'] == saved.audit_hash
                 and root['evidence_snapshot_hash'] == saved.snapshot_hash
                 and root['case_id'] == saved.snapshot['case_id'] == saved.handoff['case_id']
                 and root['analysis_run_id'] == saved.handoff['analysis_run_id']
                 and type(saved.snapshot['snapshot_version']) is int and type(saved.handoff['evidence_snapshot_version']) is int
                 and root['evidence_snapshot_version'] == saved.snapshot['snapshot_version'] == saved.handoff['evidence_snapshot_version']
                 and saved.audit['evidence_snapshot']['case_id'] == root['case_id']
                 and saved.audit['evidence_snapshot']['snapshot_version'] == root['evidence_snapshot_version']
                 and root['as_of_date'] == saved.snapshot.get('as_of_date') == saved.handoff.get('as_of_date')
                 and _company(root['reporting_company']) == _company(borrower.get('legal_name')) == _company(saved.handoff.get('borrower_name'))
                 and _same_time(root['evidence_cutoff_timestamp'], saved.snapshot.get('evidence_cutoff_timestamp'))
                 and _same_time(root['evidence_cutoff_timestamp'], saved.handoff.get('evidence_cutoff_timestamp')),
                 'Saved root identity/company/period/cutoff/provenance is inconsistent.')
        _require(saved.provenance['governance']['validators_enforced'] == saved.audit['run']['validators_enforced']
                 == saved.handoff['validators_enforced']
                 and saved.provenance['governance']['execution_mode'] == saved.audit['run']['execution_mode'],
                 'Saved root governance is inconsistent.')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ArtifactIntegrityError('Saved root identity is malformed.') from exc
    a = _Assembler(saved)
    structure = a.block('structure', lambda b: a.m3('structure', b))
    debt = a.block('debt', a.debt)
    management = a.block('management', lambda b: a.m3('management', b))
    cp = a.block('competitive_positioning', a.competitive)
    industry = a.block('industry', a.industry)
    sections = []
    for sid, title in SECTION_TITLES:
        sections.append({'id': sid, 'title': title})
    states = [structure['status'], debt['status']]
    sections[0].update(status='complete' if states == ['complete', 'complete'] else
                       'unavailable' if states == ['unavailable', 'unavailable'] else 'partial',
                       layout='structure_left_debt_right', structure=structure, debt_obligations=debt,
                       visible_warnings=structure['visible_warnings'] + debt['visible_warnings'])
    for section, block in zip(sections[1:], (management, cp, industry)):
        section.update(block)
    warnings = [w for s in sections for w in s['visible_warnings']]
    governance = a.prov['governance']
    if governance['execution_mode'] == 'offline_simulation':
        warnings.insert(0, 'Offline/scripted execution; this is not evidence of live model analytical quality.')
    memo = {
        'document': DOCUMENT, 'schema_version': SCHEMA_VERSION,
        'design_basis': {'assembler_version': ASSEMBLER_VERSION, 'selection_policy_version': CONTRACT_POLICIES[saved.handoff['canonical_references']['business_orchestrator_contract']]},
        'example_only': governance['execution_mode'] == 'offline_simulation',
        'identity': {**a.root, 'conclusion_id': saved.handoff.get('business_topic_conclusion_id'),
                     'orchestrator_run_id': (saved.current_conclusion or {}).get('orchestrator_run_id')},
        'governance': {**deepcopy(governance),
                       'memo_completeness': 'complete' if all(s['status'] == 'complete' for s in sections) else 'incomplete',
                       'independent_challenge_status': ('not_performed' if saved.handoff['canonical_references'].get('business_orchestrator_contract') == source_selection.OUTPUT_VERSION
                                                        else cp['validation_status'] or 'unavailable'), 'visible_warnings': warnings},
        'sources': a.sources, 'sections': sections,
        'evidence_ui': {'pattern': 'native_details', 'initially_expanded': False, 'hide_inline_source_citations': True,
                        'detail_fields': ['source_citations', 'evidence_quotes', 'calculation_traces', 'validation_records'],
                        'always_visible': ['material_qualifications', 'simulation_or_unverified_structure_notice',
                                           'completeness_warnings', 'unresolved_material_challenges', 'all_obligation_rows_and_business_columns'],
                        'static_pdf_evidence': 'appendix'},
    }
    memo['content_hash'] = content_hash(memo)
    verify_memo(memo)
    return memo


def verify_memo(memo):
    try:
        jsonschema.Draft202012Validator(FOUR_SECTION_SCHEMA).validate(memo)
    except jsonschema.ValidationError as exc:
        raise ArtifactIntegrityError('Four-section memo schema is invalid: ' + exc.message) from exc
    _require(memo['content_hash'] == content_hash({k: v for k, v in memo.items() if k != 'content_hash'}),
             'Four-section memo canonical content hash is invalid.')


def persist(session, saved, memo, *, path=None):
    """Idempotent freeze, with no overwrite of conflicting stage or file data."""
    verify_memo(memo)
    run_id = saved.handoff['analysis_run_id']
    existing_handoffs = list(session.scalars(select(AcceptedBusinessOverviewRow).where(
        AcceptedBusinessOverviewRow.analysis_run_id == run_id)))
    # Detached/sample inputs can be replayed by the pure function, but can
    # never authorize a persisted production artifact. Recheck authoritative
    # DB stages here; only initial reporting has no handoff row yet.
    authoritative = load_saved_inputs(session, run_id,
        handoff_payload=None if existing_handoffs else saved.handoff)
    _require((saved.audit_hash, saved.snapshot_hash, saved.provenance_hash) ==
             (authoritative.audit_hash, authoritative.snapshot_hash, authoritative.provenance_hash),
             'Provided assembly inputs differ from the authoritative frozen stages.')
    _require(canonical_json(memo) == canonical_json(assemble(authoritative)), 'Memo differs from its exact frozen sources.')
    if path is not None and path.exists():
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
            verify_memo(previous)
            _require(canonical_json(previous) == canonical_json(memo), 'Existing four-section file differs; refusing to overwrite.')
        except (OSError, ValueError) as exc:
            raise ArtifactIntegrityError('Existing four-section file is not verifiable; refusing to overwrite.') from exc
    recorder = StageRecorder(session, memo['identity']['case_id'], memo['identity']['evidence_snapshot_version'])
    row = recorder.record(stage_name(memo['identity']['analysis_run_id']), memo)
    if path is not None and not path.exists():
        with path.open('x', encoding='utf-8') as stream:
            stream.write(canonical_json(memo) + '\n')
    return row


def read_four_section(session, analysis_run_id):
    """Read an existing artifact only. Legacy absence is never auto-backfilled."""
    saved = load_saved_inputs(session, analysis_run_id)
    binding = saved.handoff['canonical_references'].get('four_section_memo')
    _require(isinstance(binding, dict), 'This legacy run has no four-section memo binding; no backfill is performed.')
    rows = verified_artifacts(session, saved.handoff['case_id'], saved.handoff['evidence_snapshot_version'])
    found = [r for r in rows if r.name == stage_name(analysis_run_id)]
    _require(len(found) == 1, 'Bound four-section memo stage is missing or ambiguous.')
    memo = json.loads(found[0].payload_json)
    verify_memo(memo)
    _require(binding == {'stage': found[0].name, 'schema_version': SCHEMA_VERSION,
                         'sha256': found[0].sha256, 'content_hash': memo['content_hash']},
             'Four-section memo differs from its exact-run handoff binding.')
    _require(canonical_json(memo) == canonical_json(assemble(saved)), 'Four-section memo differs from its frozen sources.')
    return memo
