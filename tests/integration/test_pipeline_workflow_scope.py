"""Exact, read-only combined workflow navigation over persisted BO/FO outputs."""
import hashlib
import json
import shutil
import sqlite3

import pytest

from app.core.config import get_settings
from tests.integration.test_pipeline_viewer_v2 import recorded, CASE, url, digests


def seed_job(store, ident='workflow-one', *, case=CASE, bo='bo-recorded', fo='fo-recorded', conflict=False):
    job = dict(job_id=ident, case_id=case, execution_status='completed', bo_only=False,
               run_ids={'bo':bo, 'fo':fo}, result={
                   'bo':{'status':'completed','summary':{'analysis_run_id':'other-bo' if conflict else bo}},
                   'fo':{'status':'completed','summary':{'run_id':fo}},
                   'rms':{'status':'completed','summary':{'run_id':'rms-recorded'}}})
    with sqlite3.connect(store) as db:
        db.execute('CREATE TABLE IF NOT EXISTS analysis_jobs (job_id TEXT PRIMARY KEY, payload TEXT)')
        db.execute('INSERT INTO analysis_jobs VALUES (?,?)',(ident,json.dumps(job)))


@pytest.fixture()
def workflow(recorded, tmp_path, monkeypatch):
    root,client=recorded
    database=tmp_path/'analysis.db'
    store=database.with_name(database.name+'.jobs.sqlite')
    seed_job(store)
    monkeypatch.setattr(get_settings(),'database_url','sqlite:///'+database.as_posix())
    return root,client,store


def graph(client, **params):
    return client.get(f'/pipeline/{CASE}/graph.json',params=params)


def test_entire_workflow_binds_every_fo_stage_to_the_recorded_fo_run(workflow):
    root,client,_=workflow
    body=graph(client,workflow_id='workflow-one').json()
    assert body['scope']=='workflow' and body['workflow_id']=='workflow-one'
    assert body['bound_runs']=={'bo':'bo-recorded','fo':'fo-recorded','rms':'rms-recorded'}
    nodes={n['id']:n for n in body['nodes']}
    for node in ['fo.precheck','fo.measures','fo.triggers','fo.scoring','output.fo_overview']:
        assert not nodes[node]['illustration'],node
        assert nodes[node]['run_id']=='fo-recorded'
        detail=client.get(url(nodes[node]['artifact_id']))
        assert detail.status_code==200 and detail.json()['payload_available']
        report=client.get(url(nodes[node]['artifact_id'],'/report.html'))
        assert report.status_code==200 and 'Output unavailable' not in report.text
    assert nodes['agent.m1_revenue_quality']['run_id']=='bo-recorded'
    assert any(n.get('artifact_id')=='rms.assessment.rms-recorded' for n in body['nodes'])


def test_individual_run_remains_explicit_and_does_not_bind_another_run(workflow):
    _,client,_=workflow
    body=graph(client,run_id='bo-recorded').json()
    assert body['scope']=='run' and body['workflow_id'] is None
    fo=next(n for n in body['nodes'] if n['id']=='fo.measures')
    assert fo['illustration'] and fo['artifact_id'] is None
    assert body['workflows'][0]['run_ids']['fo']=='fo-recorded'
    assert graph(client,run_id='bo-recorded',workflow_id='workflow-one').status_code==400


def test_unrelated_fo_run_is_never_joined_by_case_or_directory_order(workflow):
    root,client,_=workflow
    folder=root/'fo'/CASE
    shutil.copytree(folder/'fo-recorded',folder/'zzz-unrelated')
    path=folder/'zzz-unrelated'/'financial_overview.json'
    doc=json.loads(path.read_text());doc['composite']['score']=9.9;path.write_text(json.dumps(doc))
    body=graph(client,workflow_id='workflow-one').json()
    assert all(n.get('run_id')!='zzz-unrelated' for n in body['nodes'])
    fo=next(n for n in body['nodes'] if n['id']=='output.fo_overview')
    assert client.get(url(fo['artifact_id'])).json()['payload']['composite']['score']==3.3


def test_missing_linked_fo_artifact_remains_absent_without_using_another_run(workflow):
    root,client,_=workflow
    folder=root/'fo'/CASE
    shutil.copytree(folder/'fo-recorded',folder/'other-run')
    shutil.rmtree(folder/'fo-recorded')
    body=graph(client,workflow_id='workflow-one').json()
    fo=next(n for n in body['nodes'] if n['id']=='fo.measures')
    assert fo['illustration'] and fo['artifact_id'] is None
    assert not any(n.get('run_id')=='other-run' for n in body['nodes'])


def test_conflicting_or_foreign_workflow_references_are_rejected(workflow):
    _,client,store=workflow
    seed_job(store,'conflicting',conflict=True)
    seed_job(store,'foreign',case='OTHER_CASE')
    assert graph(client,workflow_id='conflicting').status_code==409
    assert graph(client,workflow_id='foreign').status_code==404
    assert graph(client,workflow_id='missing').status_code==404


def test_multiple_recorded_workflows_are_offered_without_selecting_latest(workflow):
    _,client,store=workflow
    seed_job(store,'workflow-two')
    body=graph(client).json()
    assert {w['workflow_id'] for w in body['workflows']}=={'workflow-one','workflow-two'}
    assert body['selection_required'] and body['workflow_id'] is None
    assert not any(n.get('artifact_id') for n in body['nodes'])


def test_workflow_inspection_never_writes_jobs_or_artifacts_or_opens_an_orm_session(workflow,monkeypatch):
    root,client,store=workflow
    before=digests(root);job_hash=hashlib.sha256(store.read_bytes()).hexdigest()
    def forbidden(*args,**kwargs):raise AssertionError('Combined viewer must not initialize a database or run models.')
    monkeypatch.setattr('app.api.deps._session_factory',forbidden)
    monkeypatch.setattr('app.services.llm.providers.RealProviderBackend.generate',forbidden)
    for _ in range(2):assert graph(client,workflow_id='workflow-one').status_code==200
    assert digests(root)==before and hashlib.sha256(store.read_bytes()).hexdigest()==job_hash


def test_missing_job_history_does_not_create_a_database(recorded,tmp_path,monkeypatch):
    _,client=recorded
    database=tmp_path/'never-created.db'
    monkeypatch.setattr(get_settings(),'database_url','sqlite:///'+database.as_posix())
    body=graph(client,run_id='fo-recorded').json()
    assert body['workflows']==[]
    assert not database.exists() and not database.with_name(database.name+'.jobs.sqlite').exists()


def test_rms_sources_must_agree_with_the_workflow_fo_reference(workflow):
    root,client,_=workflow
    path=root/'rms'/CASE/'rms-recorded'/'rms.json'
    doc=json.loads(path.read_text());doc['sources']['fo_run_id']='unrelated-fo';path.write_text(json.dumps(doc))
    response=graph(client,workflow_id='workflow-one')
    assert response.status_code==409 and 'run bindings' in response.text
