"""M4A-01: frozen hashes and selected-run identity are independent safeguards.

All mutations occur before freezing synthetic records (or explicitly corrupt an
isolated chain). Never repairs history, invokes a worker, or contacts a provider.
"""
import copy
import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from lxml import html
from sqlalchemy import select, update

from app.api.deps import get_session
from app.main import create_app
from app.models.base import Base
from app.models.orm import AcceptedBusinessOverviewRow, StageArtifact, AgenticAnalysisRun
from app.services import bo_fo
from app.services.bo.reporting import handoff_content_hash
from app.services.bo.workbench import bo_artifact
from app.services.pipeline.artifacts import ArtifactIntegrityError, StageRecorder, verified_artifacts
from tests.integration.test_analysis_review_workspace import seed_run

SECRET = 'CONFIDENTIAL FOREIGN ARCHIVE CONTENT'


def stored_records(session):
    """Include all tables, not only the artefact we are deliberately rejecting."""
    session.flush()
    return {table.name: sorted(json.dumps(dict(row), default=str, sort_keys=True)
                              for row in session.execute(select(table)).mappings())
            for table in Base.metadata.sorted_tables}


@pytest.fixture
def archive_workspace(db_session, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Read-time identity tests must not run workers or providers')
    from app.services.llm.providers_vertex import VertexProviderBackend
    from app.services.llm.providers import RealProviderBackend
    monkeypatch.setattr(VertexProviderBackend, 'generate', forbidden)
    monkeypatch.setattr(VertexProviderBackend, '_client', forbidden)
    monkeypatch.setattr(RealProviderBackend, 'generate', forbidden)
    jobs = []
    original = StageRecorder.record

    @contextmanager
    def factory(*, absent=(), change=None):
        def record(self, name, payload):
            kind = name.split(':')[0].removeprefix('bo_')
            if name.endswith(':bo-selected'):
                if kind in absent:
                    return None
                payload = copy.deepcopy(payload)
                if change:
                    change(kind, payload)
            return original(self, name, payload)
        with monkeypatch.context() as patch:
            patch.setattr(StageRecorder, 'record', record)
            jobs.extend([seed_run(db_session, 'other', 2), seed_run(db_session, 'selected', 1)])
        class Records:
            start = forbidden
            def get(self, ident):
                return copy.deepcopy(next((j for j in jobs if j['job_id'] == ident), None))
            def recent(self):
                return copy.deepcopy(jobs)
        monkeypatch.setattr(bo_fo, 'jobs', Records())
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        with TestClient(app) as client:
            yield client, jobs, db_session
    return factory


def poison(kind, payload):
    if kind == 'audit':
        payload['hypotheses']['records'][0]['claim'] = SECRET
    else:
        payload['executive']['provisional_view']['text'] = SECRET


def reject_every_path(client, session):
    before = stored_records(session)
    for path in [
        '/analysis/selected/review', '/analysis/selected/audit',
        '/analysis/selected/audit#specialists', '/analysis/selected/audit#evidence',
        '/cases/HCA_2024/bo/runs/bo-selected',
        '/cases/HCA_2024/bo.html?analysis_run_id=bo-selected',
        '/cases/HCA_2024/bo/runs/bo-selected/memo.json',
        '/cases/HCA_2024/bo/runs/bo-selected/audit.json',
        '/cases/HCA_2024/bo/runs/bo-selected/memo.html',
        '/cases/HCA_2024/bo/runs/bo-selected/audit.html',
        '/cases/HCA_2024/bo/runs/bo-selected/memo.pdf',
        '/cases/HCA_2024/bo/runs/bo-selected/audit.pdf',
    ]:
        response = client.get(path)
        assert response.status_code in {404, 409}, (path, response.status_code, response.text)
        assert SECRET not in response.text
        assert 'Synthesized assessment other' not in response.text
    response = client.get('/credit-memos?search=selected')
    assert response.status_code == 200
    assert SECRET not in response.text
    row = html.fromstring(response.text).xpath('//article[@data-job-id="selected"]')[0]
    assert 'Unavailable or incomplete' in row.text_content()
    assert not row.xpath('.//a[contains(@href,"/review")]')
    # Other HCA run still resolves its own frozen output, never the rejected one.
    other = client.get('/analysis/other/audit')
    assert other.status_code == 200 and 'Original specialist wording other' in other.text
    assert SECRET not in other.text
    assert stored_records(session) == before


def test_valid_selected_run_and_second_hca_remain_separate(archive_workspace):
    with archive_workspace() as (client, _, session):
        before = stored_records(session)
        for name in ('selected', 'other'):
            review = client.get(f'/analysis/{name}/review')
            audit = client.get(f'/analysis/{name}/audit')
            assert review.status_code == audit.status_code == 200
            assert 'Synthesized assessment ' + name in review.text
            assert 'Original specialist wording ' + name in audit.text
            assert 'Original specialist wording ' + ('other' if name == 'selected' else 'selected') not in audit.text
            payload = client.get(f'/cases/HCA_2024/bo/runs/bo-{name}/audit.json')
            assert payload.status_code == 200 and payload.json()['run']['analysis_run_id'] == 'bo-' + name
        assert stored_records(session) == before


@pytest.mark.parametrize('absent', [('memo',), ('audit',), ('memo', 'audit')])
def test_honest_partial_package_without_fabrication(archive_workspace, absent):
    with archive_workspace(absent=absent) as (client, jobs, session):
        jobs[-1].update(execution_status='interrupted', status='interrupted')
        before = stored_records(session)
        review = client.get('/analysis/selected/review')
        audit = client.get('/analysis/selected/audit')
        assert review.status_code == audit.status_code == 200
        assert 'No validated Business Credit Assessment is available for this run.' in review.text
        assert 'Synthesized assessment other' not in review.text + audit.text
        assert ('AUDIT ONLY SPECIALIST selected' in audit.text) == ('audit' not in absent)
        assert 'Original specialist wording other' not in audit.text
        if 'audit' not in absent:
            document = html.fromstring(audit.text)
            for href in document.xpath('//a[starts-with(@href,"#")]/@href'):
                assert document.xpath('//*[@id="' + href[1:] + '"]')
        assert stored_records(session) == before


@pytest.mark.parametrize('kind,absent', [
    ('audit', ('memo',)), ('audit', ()), ('memo', ()), ('memo', ('audit',)),
])
@pytest.mark.parametrize('field', ['case', 'run', 'document', 'schema', 'frozen_version'])
def test_correctly_hashed_foreign_or_wrong_type_archive_rejected(archive_workspace, kind, absent, field):
    def change(current, payload):
        if current != kind:
            return
        poison(current, payload)
        if field == 'case':
            payload['case']['case_id'] = 'FOREIGN_CASE'
        elif field == 'run':
            payload['run']['analysis_run_id'] = 'bo-other'  # same borrower, different run
        elif field == 'document':
            payload['document'] = 'business_overview_memo' if kind == 'audit' else 'business_overview_audit_report'
        elif field == 'schema':
            payload['version'] = 'unknown-report-schema'
        else:
            payload['case']['evidence_snapshot_version'] = 2
    with archive_workspace(absent=absent, change=change) as (client, _, session):
        # Valid hashes never stand in for identity verification.
        assert verified_artifacts(session, 'HCA_2024', 1)
        with pytest.raises(ArtifactIntegrityError):
            bo_artifact(session, 'bo-selected', kind)
        reject_every_path(client, session)


@pytest.mark.parametrize('kind', ['memo', 'audit'])
@pytest.mark.parametrize('field', ['case', 'run', 'document', 'version', 'case_version', 'null_run', 'empty_payload'])
def test_unverifiable_historical_identity_is_not_treated_as_absence(archive_workspace, kind, field):
    def change(current, payload):
        if current != kind:
            return
        poison(current, payload)
        if field == 'case_version':
            del payload['case']['evidence_snapshot_version']
        elif field == 'null_run':
            payload['run'] = None
        elif field == 'empty_payload':
            payload.clear()
        else:
            del payload[field]
    with archive_workspace(change=change) as (client, _, session):
        reject_every_path(client, session)


@pytest.mark.parametrize('field,value', [('case_id', 'FOREIGN_CASE'), ('snapshot_version', 2),
                                        ('snapshot_version', True), ('snapshot_version', None)])
def test_audit_snapshot_identity_is_independent_of_outer_headers(archive_workspace, field, value):
    def change(kind, payload):
        if kind == 'audit':
            poison(kind, payload)
            payload['evidence_snapshot'][field] = value
    with archive_workspace(absent=('memo',), change=change) as (client, _, session):
        reject_every_path(client, session)


def test_corrupted_chain_fails_closed_without_changes(archive_workspace):
    with archive_workspace() as (client, _, session):
        session.execute(update(StageArtifact).where(StageArtifact.name == 'bo_audit:bo-selected')
                        .values(payload_json='{"confidential":"' + SECRET + '"}'))
        session.expire_all()
        reject_every_path(client, session)


@pytest.mark.parametrize('field,value', [('case_id', 'FOREIGN_CASE'), ('evidence_snapshot_version', 2)])
def test_authoritative_analysis_run_must_agree_with_handoff(archive_workspace, field, value):
    with archive_workspace() as (client, _, session):
        setattr(session.get(AgenticAnalysisRun, 'bo-selected'), field, value)
        session.flush()
        reject_every_path(client, session)


@pytest.mark.parametrize('field,value', [('handoff_id', 'foreign-handoff'),
                                        ('analysis_run_id', 'bo-other'), ('case_id', 'FOREIGN_CASE'),
                                        ('evidence_snapshot_version', 2)])
def test_correctly_hashed_handoff_identity_must_agree_with_row(archive_workspace, field, value):
    with archive_workspace() as (client, _, session):
        row = session.get(AcceptedBusinessOverviewRow, 'handoff-selected')
        row.payload = {**row.payload, field: value}
        row.content_hash = handoff_content_hash(row.payload)
        session.flush()
        reject_every_path(client, session)


@pytest.mark.parametrize('key,value', [('analysis_run_id', 'bo-other'),
                                    ('evidence_snapshot_version', 2), ('audit_stage', 'bo_audit:bo-other')])
def test_recorded_canonical_reference_cannot_redirect_archive(archive_workspace, key, value):
    with archive_workspace() as (client, _, session):
        row = session.get(AcceptedBusinessOverviewRow, 'handoff-selected')
        row.payload = {**row.payload, 'canonical_references': {key: value}}
        row.content_hash = handoff_content_hash(row.payload)
        session.flush()
        reject_every_path(client, session)


@pytest.mark.parametrize('record_type', ['finding', 'conclusion'])
@pytest.mark.parametrize('key,value', [('analysis_run_id', 'bo-other'), ('case_id', 'FOREIGN_CASE'),
                                    ('snapshot_version', 2)])
def test_embedded_declared_identity_must_agree_with_archive(archive_workspace, record_type, key, value):
    def change(kind, payload):
        if kind != 'audit':
            return
        poison(kind, payload)
        record = (payload['hypotheses']['records'][0] if record_type == 'finding'
                  else payload['conclusions'][0]['payload'])
        record[key] = value
    with archive_workspace(absent=('memo',), change=change) as (client, _, session):
        reject_every_path(client, session)
