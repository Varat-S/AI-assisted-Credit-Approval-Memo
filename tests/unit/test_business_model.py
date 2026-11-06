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
