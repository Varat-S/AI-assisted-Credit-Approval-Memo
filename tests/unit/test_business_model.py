"""Informational-agent isolation, evidence gating and idempotent persistence."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.orm import ModelRun
from app.prompts.business_model import NAME
from app.services.bo.business_model import load_description, run_description, select_passages, validate_description
from app.services.llm.client import FakeLLMBackend
from app.services.pipeline.artifacts import ArtifactIntegrityError, StageRecorder

TEXT = ('Northfield operates hospitals and outpatient clinics. Patients receive inpatient and outpatient services. '
        'Revenue comes from Medicare, Medicaid, commercial insurers and patient payments. '
        'Operating inputs include clinical employees, medical supplies, facilities and purchased physician services. '
        'Operating expenses include salaries and benefits, supplies and purchased services.')
SUMMARY = ('Northfield operates hospitals and outpatient clinics that provide inpatient and outpatient services to patients. '
           'It receives payments from Medicare, Medicaid, commercial insurers and patients for the services provided. '
           'The delivery of these services uses clinical employees, medical supplies, facilities and purchased physician services. '
           'Its operating expenses include salaries and benefits, supplies and purchased services used to deliver patient care across its hospitals and outpatient clinics.')


def snapshot():
    return {'case_id': 'CASE', 'snapshot_version': 1, 'as_of_date': '2025-12-31',
            'documents': [{'document_id': 'annual', 'role': 'primary_inline_xbrl', 'form': '10-K',
                           'report_date': '2025-12-31'}],
            'narrative_evidence': [{'evidence_id': 'E1', 'document_id': 'annual', 'section': 'Item 1',
                                    'location': 0, 'text': TEXT}]}


def answer():
    return {'status': 'complete', 'paragraphs': [{'sentences': [
        {'text': SUMMARY, 'evidence': [{'evidence_id': 'E1', 'quote': TEXT}]}]}], 'unavailable_reason': None}


def saved():
    return SimpleNamespace(snapshot=snapshot(), snapshot_hash='frozen-hash',
                           handoff={'borrower_name': 'Northfield', 'credit_view': 'unchanged'})


def test_selection_excludes_proxy_exhibits_other_period_and_other_agents():
    data = snapshot()
    for ident, changes in [('proxy', {'form': 'DEF 14A'}), ('exhibit', {'role': 'exhibit'}),
                           ('old', {'report_date': '2024-12-31'})]:
        data['documents'].append({**data['documents'][0], 'document_id': ident, **changes})
        data['narrative_evidence'].append({**data['narrative_evidence'][0], 'document_id': ident, 'evidence_id': ident})
    data['agent_output'] = 'DO NOT INCLUDE IN INPUT'
    selected, _ = select_passages(data)
    assert [p['evidence_id'] for p in selected] == ['E1']
    assert 'agent_output' not in str(selected)


@pytest.mark.parametrize('change', ['unknown_id', 'invented_quote', 'missing_citation', 'empty_complete', 'too_long'])
def test_unsupported_or_unbounded_descriptions_rejected(change):
    value = answer()
    sentence = value['paragraphs'][0]['sentences'][0]
    if change == 'unknown_id': sentence['evidence'][0]['evidence_id'] = 'proxy'
    if change == 'invented_quote': sentence['evidence'][0]['quote'] = 'The company sells software subscriptions.'
    if change == 'missing_citation': sentence['evidence'] = []
    if change == 'empty_complete': value['paragraphs'] = []
    if change == 'too_long': sentence['text'] = 'company ' * 221
    with pytest.raises(ValueError): validate_description(value, select_passages(snapshot())[0])


def test_quote_spanning_filing_line_breaks_is_accepted():
    # Filing text keeps line breaks (table cells, wrapped lines); the model quotes it with spaces.
    data = snapshot()
    data['narrative_evidence'][0]['text'] = TEXT.replace('outpatient clinics. Patients', 'outpatient clinics.\nPatients')
    value = answer()
    assert validate_description(value, select_passages(data)[0])['status'] == 'complete'
    value['paragraphs'][0]['sentences'][0]['evidence'][0]['quote'] = TEXT.replace('Medicare', 'Medicaree')
    with pytest.raises(ValueError):
        validate_description(value, select_passages(data)[0])


def test_insufficient_evidence_has_no_invented_description():
    assert validate_description({'status': 'insufficient_evidence', 'paragraphs': [],
                                 'unavailable_reason': 'Services are not described.'}, [])['paragraphs'] == []


def test_one_call_per_run_and_no_handoff_or_snapshot_mutation(db_session, monkeypatch):
    source = saved()
    original = deepcopy(source)
    monkeypatch.setattr('app.services.bo.four_section.load_saved_inputs', lambda *args: source)
    backend = FakeLLMBackend()
    backend.register('analyze', answer(), key=NAME)
    result = run_description(db_session, 'run-1', backend)
    assert result['status'] == 'complete' and result['purpose'] == 'display_only'
    assert source.snapshot == original.snapshot and source.handoff == original.handoff
    assert result['identity']['analysis_run_id'] == 'run-1'
    assert len(list(db_session.scalars(select(ModelRun)))) == 1
    monkeypatch.setattr(backend, 'generate', lambda *a: pytest.fail('No repeat model call allowed'))
    assert run_description(db_session, 'run-1', backend) == result
    assert load_description(db_session, 'run-2', source) is None
    assert load_description(db_session, 'run-1', source) == result
    assert len(list(db_session.scalars(select(ModelRun)))) == 1


def test_invalid_provider_output_saved_as_rejected_without_text(db_session, monkeypatch):
    monkeypatch.setattr('app.services.bo.four_section.load_saved_inputs', lambda *args: saved())
    backend = FakeLLMBackend()
    bad = answer();bad['paragraphs'][0]['sentences'][0]['evidence'][0]['quote'] = 'Not in the selected filing.'
    backend.register('analyze', bad, key=NAME)
    result = run_description(db_session, 'run-1', backend)
    assert result['status'] == 'rejected' and result['paragraphs'] == []


def test_wrong_snapshot_binding_is_rejected(db_session):
    source = saved()
    StageRecorder(db_session, 'CASE', 1).record('informational_business_model:run-1', {
        'schema_version': 'informational-business-model-1.0', 'identity': {'analysis_run_id': 'other'}})
    with pytest.raises(ArtifactIntegrityError): load_description(db_session, 'run-1', source)


def test_missing_10k_never_calls_model(db_session, monkeypatch):
    source = saved();source.snapshot['documents'] = []
    monkeypatch.setattr('app.services.bo.four_section.load_saved_inputs', lambda *args: source)
    result = run_description(db_session, 'run-1', None)
    assert result['status'] == 'insufficient_evidence' and result['model_run_id'] is None


def test_cross_chunk_quote_is_split_into_exact_original_source_ids():
    data = snapshot(); first = data['narrative_evidence'][0]; split = 95
    first['text'] = TEXT[:split]
    data['narrative_evidence'].append({**first, 'evidence_id': 'E2', 'location': split, 'text': TEXT[split:]})
    value = answer();value['paragraphs'][0]['sentences'][0]['evidence'][0]['evidence_id'] = 'E2'
    original = deepcopy(value)
    result = validate_description(value, select_passages(data)[0])
    citations = result['paragraphs'][0]['sentences'][0]['evidence']
    assert {c['evidence_id'] for c in citations} == {'E1', 'E2'}
    lookup = {p['evidence_id']: p['text'] for p in data['narrative_evidence']}
    assert all(c['quote'] in lookup[c['evidence_id']] for c in citations)
    assert value == original
    assert validate_description(result, select_passages(data)[0]) == result
    for mutation in ['gap', 'other_document', 'changed_number']:
        changed = deepcopy(data); trial = deepcopy(value)
        if mutation == 'gap': changed['narrative_evidence'][1]['location'] += 1
        if mutation == 'other_document': changed['narrative_evidence'][1]['document_id'] = 'other'
        if mutation == 'changed_number': trial['paragraphs'][0]['sentences'][0]['evidence'][0]['quote'] = TEXT.replace('Northfield', 'Northfield 2099')
        with pytest.raises(ValueError): validate_description(trial, changed['narrative_evidence'])


def test_one_bad_sentence_does_not_discard_other_supported_sentences():
    value = answer()
    value['paragraphs'][0]['sentences'].append({'text': 'Unsupported assertion.',
        'evidence': [{'evidence_id': 'E1', 'quote': 'Invented source quotation.'}]})
    result = validate_description(value, select_passages(snapshot())[0], retain_supported=True)
    assert result['paragraphs'] == answer()['paragraphs']
    assert len(value['paragraphs'][0]['sentences']) == 2


def test_saved_rejection_recovery_is_append_only_and_makes_no_model_call(db_session, monkeypatch):
    from app.services.bo import business_model as module
    from app.models.orm import StageArtifact
    source = saved()
    monkeypatch.setattr('app.services.bo.four_section.load_saved_inputs', lambda *args: source)
    backend = FakeLLMBackend();backend.register('analyze', answer(), key=NAME)
    validator = module.validate_description
    def old_rejection(*args, **kwargs): raise ValueError('Previous evidence validation failure')
    monkeypatch.setattr(module, 'validate_description', old_rejection)
    original = run_description(db_session, 'run-1', backend)
    assert original['status'] == 'rejected'
    row = db_session.query(StageArtifact).filter_by(name='informational_business_model:run-1').one()
    before_count = db_session.query(StageArtifact).count()
    frozen = (row.payload_json, row.sha256, row.chain_hash)
    monkeypatch.setattr(module, 'validate_description', validator)
    monkeypatch.setattr(backend, 'generate', lambda *a: pytest.fail('No model calls during recovery'))
    recovered = module.recover_description(db_session, 'run-1')
    assert recovered['status'] == 'complete'
    assert (row.payload_json, row.sha256, row.chain_hash) == frozen
    assert db_session.query(StageArtifact).count() == before_count + 1
    assert db_session.query(ModelRun).count() == 1
    assert load_description(db_session, 'run-1', source) == recovered
    assert module.recover_description(db_session, 'run-1') == recovered
    assert run_description(db_session, 'run-1', backend) == recovered
