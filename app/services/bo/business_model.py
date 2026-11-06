"""Isolated informational agent over a selected run's frozen 10-K.

Runs AFTER credit analysis is complete. Its separate append-only artifact is
read only by the presentation layer: never included in handoffs, hypotheses,
credit scoring, or analytical prompts. Reading a memo never runs a model.
"""
from copy import deepcopy
import json
import re

from app.core.hashing import content_hash
from app.prompts.business_model import Description, NAME, PROMPT
from app.prompts.registry import PromptRegistry
from app.services.llm.client import LLMClient
from app.services.pipeline.artifacts import ArtifactIntegrityError, StageRecorder, verified_artifacts

VERSION = 'informational-business-model-1.0'


def stage_name(run_id):
    return 'informational_business_model:' + run_id


def select_passages(snapshot):
    """Only the selected period's primary 10-K; no exhibits, proxy or agent output.

    Use full admitted passages from Business, MD&A and financial statements.
    Explicit bounded selection retains whole passages and records omitted IDs.
    """
    docs = {d['document_id'] for d in snapshot.get('documents', [])
            if d.get('form') in {'10-K', '10-K/A'}
            and d.get('role') == 'primary_inline_xbrl'
            and d.get('report_date') == snapshot.get('as_of_date')}
    candidates = [p for p in snapshot.get('narrative_evidence', [])
                  if p.get('document_id') in docs and p.get('text', '').strip()
                  and p.get('section') in {'Item 1', 'Item 7', 'Item 8'}]
    candidates.sort(key=lambda p: ({'Item 1': 0, 'Item 7': 1, 'Item 8': 2}[p['section']],
                                   p.get('location') or 0, p['evidence_id']))
    selected, omitted, size = [], [], 0
    for p in candidates:
        amount = len(p['text'].encode('utf-8'))
        if size + amount > 650_000:
            omitted.append(p['evidence_id'])
            continue
        selected.append({k: p.get(k) for k in ('evidence_id', 'document_id', 'section', 'text')})
        size += amount
    return selected, omitted


def validate_description(answer, passages):
    """Validate references/quote occurrence, not semantic entailment or neutrality."""
    value = Description.model_validate(answer).model_dump()
    if value['status'] == 'insufficient_evidence':
        if value['paragraphs'] or not (value['unavailable_reason'] or '').strip():
            raise ValueError('Insufficient evidence must have a reason and no description.')
        return value
    if not value['paragraphs'] or value['unavailable_reason'] is not None:
        raise ValueError('Complete description must have paragraphs and no unavailable reason.')
    lookup = {p['evidence_id']: p for p in passages}
    words = 0
    for paragraph in value['paragraphs']:
        for sentence in paragraph['sentences']:
            words += len(re.findall(r'\S+', sentence['text']))
            for citation in sentence['evidence']:
                source = lookup.get(citation['evidence_id'])
                if source is None or citation['quote'] not in source['text']:
                    raise ValueError('A supporting quotation is not exact selected-10-K evidence.')
    # The approved word count is a target; allow modest variation, never a long report.
    if not 60 <= words <= 220:
        raise ValueError('Description is outside the brief presentation limit (60-220 words).')
    return value


def load_description(session, run_id, saved):
    name = stage_name(run_id)
    rows = verified_artifacts(session, saved.snapshot['case_id'], saved.snapshot['snapshot_version'])
    row = next((r for r in rows if r.name == name), None)
    if row is None:
        return None  # Legacy runs remain unchanged; never generate on a read.
    result = json.loads(row.payload_json)
    expected = {'analysis_run_id': run_id, 'case_id': saved.snapshot['case_id'],
                'snapshot_version': saved.snapshot['snapshot_version'], 'snapshot_hash': saved.snapshot_hash}
    if result.get('schema_version') != VERSION or result.get('identity') != expected:
        raise ArtifactIntegrityError('Business Model belongs to a different run or snapshot.')
    passages, _ = select_passages(saved.snapshot)
    if result.get('status') in {'complete', 'insufficient_evidence'}:
        try:
            validate_description({k: result[k] for k in ('status', 'paragraphs', 'unavailable_reason')}, passages)
        except (ValueError, KeyError) as exc:
            raise ArtifactIntegrityError('Business Model evidence validation failed.') from exc
    return deepcopy(result)


def run_description(session, run_id, backend):
    """One model call, idempotent per analysis run; failures cannot feed credit agents."""
    from app.services.bo.four_section import load_saved_inputs
    saved = load_saved_inputs(session, run_id)
    existing = load_description(session, run_id, saved)
    if existing is not None:
        return existing
    snapshot = saved.snapshot
    passages, omitted = select_passages(snapshot)
    identity = {'analysis_run_id': run_id, 'case_id': snapshot['case_id'],
                'snapshot_version': snapshot['snapshot_version'], 'snapshot_hash': saved.snapshot_hash}
    result = {'schema_version': VERSION, 'identity': identity, 'purpose': 'display_only',
              'status': 'insufficient_evidence', 'paragraphs': [],
              'unavailable_reason': 'No admitted business-description passages from the primary 10-K are available.',
              'model_run_id': None, 'selected_evidence_ids': [p['evidence_id'] for p in passages],
              'omitted_evidence_ids': omitted, 'input_hash': content_hash(passages)}
    if passages:
        registry = PromptRegistry(session)
        registry.register(NAME, template=PROMPT, response_schema=Description.model_json_schema(), role='informational')
        client = LLMClient(backend, prompts=registry, session=session)
        response = client.analyze({'company': saved.handoff['borrower_name'],
                                   'reporting_period': snapshot['as_of_date'], 'passages': passages,
                                   'source_selection': 'Business, MD&A and financial-statement passages from the primary 10-K',
                                   'omitted_passage_count': len(omitted)},
                                  evidence_ids=result['selected_evidence_ids'], case_id=snapshot['case_id'],
                                  case_version=snapshot['snapshot_version'], prompt_name=NAME,
                                  key=NAME, model_tier='narrow')
        result['model_run_id'] = response.run_id
        try:
            if not response.is_valid:
                raise ValueError('The provider response did not pass schema validation.')
            result.update(validate_description(response.parsed, passages))
        except ValueError:
            result.update(status='rejected', paragraphs=[],
                          unavailable_reason='The Business Model description did not pass evidence or format checks.')
    StageRecorder(session, snapshot['case_id'], snapshot['snapshot_version']).record(stage_name(run_id), result)
    return result
