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
from app.services.bo.hypotheses import quote_in_passage
from app.services.llm.client import LLMClient
from app.services.pipeline.artifacts import ArtifactIntegrityError, StageRecorder, verified_artifacts

VERSION = 'informational-business-model-1.0'
VALIDATOR_VERSION = 'business-model-evidence-1.1'


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
        selected.append({k: p.get(k) for k in ('evidence_id', 'document_id', 'section', 'location', 'text')})
        size += amount
    return selected, omitted


def resolve_citation(citation, passages):
    """Split a verbatim cross-chunk quote into its real, adjacent source IDs."""
    source = next((p for p in passages if p['evidence_id'] == citation['evidence_id']), None)
    if source is None:
        raise ValueError('Unknown selected-10-K evidence ID.')
    if quote_in_passage(citation['quote'], source['text']):
        return [deepcopy(citation)]
    if source.get('location') is None:
        raise ValueError('Quotation is not present in its declared passage.')
    ordered = sorted([p for p in passages if p['document_id'] == source['document_id']
                      and p['section'] == source['section'] and p.get('location') is not None],
                     key=lambda p: p['location'])
    anchor = next(i for i, p in enumerate(ordered) if p['evidence_id'] == source['evidence_id'])
    lo = hi = anchor
    while lo > max(0, anchor - 2) and ordered[lo-1]['location'] + len(ordered[lo-1]['text']) == ordered[lo]['location']:
        lo -= 1
    while hi < min(len(ordered)-1, anchor + 2) and ordered[hi]['location'] + len(ordered[hi]['text']) == ordered[hi+1]['location']:
        hi += 1
    context = ordered[lo:hi+1]
    joined = ''.join(p['text'] for p in context)
    if not quote_in_passage(citation['quote'], joined):
        raise ValueError('Quotation is not exact adjacent selected-10-K evidence.')
    from app.services.bo.m3_rebuild.matching import locate
    match = locate(joined, citation['quote'])
    if not match:
        raise ValueError('Quotation offsets could not be established.')
    result, offset = [], 0
    for passage in context:
        start, end = max(match['span_start'] - offset, 0), min(match['span_end'] - offset, len(passage['text']))
        if end > start:
            # Very short boundary fragments need a little exact source context
            # to satisfy the citation schema's existing minimum quote length.
            if end - start < 12:
                start = max(0, start - 12)
                end = min(len(passage['text']), max(end, start + 12))
            result.append({'evidence_id': passage['evidence_id'], 'quote': passage['text'][start:end]})
        offset += len(passage['text'])
    if source['evidence_id'] not in {c['evidence_id'] for c in result} or len(result) < 2:
        raise ValueError('Recovered quote does not span its declared source boundary.')
    return result


def validate_description(answer, passages, *, retain_supported=False):
    """Validate references/quote occurrence (whitespace-normalised), not semantic entailment or neutrality."""
    value = Description.model_validate(answer).model_dump()
    if value['status'] == 'insufficient_evidence':
        if value['paragraphs'] or not (value['unavailable_reason'] or '').strip():
            raise ValueError('Insufficient evidence must have a reason and no description.')
        return value
    if not value['paragraphs'] or value['unavailable_reason'] is not None:
        raise ValueError('Complete description must have paragraphs and no unavailable reason.')
    retained = []
    words = 0
    for paragraph in value['paragraphs']:
        sentences = []
        for sentence in paragraph['sentences']:
            try:
                citations = [resolved for citation in sentence['evidence']
                             for resolved in resolve_citation(citation, passages)]
            except ValueError:
                if retain_supported:
                    continue  # Withhold the whole sentence, not a required supporting citation.
                raise
            sentences.append({**sentence, 'evidence': citations})
            words += len(re.findall(r'\S+', sentence['text']))
        if sentences:
            retained.append({'sentences': sentences})
    value['paragraphs'] = retained
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
    recovered = next((r for r in rows if r.name == 'informational_business_model_recovery:' + run_id), None)
    if recovered is not None:
        correction = json.loads(recovered.payload_json)
        if result.get('status') != 'rejected' or correction.get('recovery', {}).get('original_sha256') != row.sha256:
            raise ArtifactIntegrityError('Business Model recovery does not bind to the original rejected artifact.')
        result = correction
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


def recover_description(session, run_id):
    """Explicit append-only replay of a rejected saved response; no model calls."""
    from app.models.orm import ModelRun
    from app.services.bo.four_section import load_saved_inputs
    saved = load_saved_inputs(session, run_id)
    original = load_description(session, run_id, saved)
    if not original or original['status'] != 'rejected':
        return original
    model = session.get(ModelRun, original.get('model_run_id'))
    if (not model or model.case_id != saved.snapshot['case_id']
            or model.case_version != saved.snapshot['snapshot_version'] or model.prompt_name != NAME
            or not model.parsed_response):
        raise ArtifactIntegrityError('Saved Business Model response identity does not match the selected run.')
    passages, _ = select_passages(saved.snapshot)
    value = validate_description(model.parsed_response, passages, retain_supported=True)
    base = next(r for r in verified_artifacts(session, saved.snapshot['case_id'], saved.snapshot['snapshot_version'])
                if r.name == stage_name(run_id))
    result = {**original, **value, 'validator_version': VALIDATOR_VERSION,
              'recovery': {'original_sha256': base.sha256, 'model_run_id': model.run_id,
                           'reason': 'Revalidated saved response with adjacent-chunk citation recovery.'}}
    StageRecorder(session, saved.snapshot['case_id'], saved.snapshot['snapshot_version']).record(
        'informational_business_model_recovery:' + run_id, result)
    return result


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
            result.update(validate_description(response.parsed, passages, retain_supported=True))
            result['validator_version'] = VALIDATOR_VERSION
        except ValueError:
            result.update(status='rejected', paragraphs=[],
                          unavailable_reason='The Business Model description did not pass evidence or format checks.')
    StageRecorder(session, snapshot['case_id'], snapshot['snapshot_version']).record(stage_name(run_id), result)
    return result
