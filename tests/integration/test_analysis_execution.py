"""M2 execution lifecycle. Synthetic filing + mocked worker, never paid providers."""
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from lxml import html
from app.api import analysis
from app.services import bo_fo
from app.services.analysis_jobs import JobStore, IdempotencyConflict
from tests.integration.test_analysis_workspace import evidence, workspace


def wait_for(jobs, ident, status):
    for _ in range(200):
        job = jobs.get(ident)
        if job['execution_status'] == status and (status in {'pending','running'} or job['finished_at']):
            return job
        time.sleep(.01)
    raise AssertionError(jobs.get(ident))


@pytest.fixture
def execution_env(workspace, monkeypatch, tmp_path):
    from app.models.base import create_engine_and_session, init_db
    from app.core.config import get_settings
    database = tmp_path / 'execution-main.sqlite'
    engine, _ = create_engine_and_session('sqlite:///' + str(database))
    init_db(engine)
    engine.dispose()
    monkeypatch.setattr(get_settings(), 'database_url', 'sqlite:///' + str(database))
    jobs = bo_fo.Jobs(tmp_path/'jobs.sqlite')
    monkeypatch.setattr(bo_fo, 'jobs', jobs)
    monkeypatch.setattr(bo_fo, 'plan', lambda folder, case_id, cutoff: {'case_id':case_id or 'HCA_2024','cutoff':cutoff})
    monkeypatch.setattr(analysis, 'execution_backends', lambda sections: (None,None,None))
    released = threading.Event()
    started = threading.Event()
    calls = []
    def worker(**kwargs):
        calls.append(kwargs)
        kwargs['on_stage']('bo','primary_specialists','running', {'agents':{'fixture':'running'}})
        kwargs['on_progress']('bo','specialist test checkpoint')
        started.set()
        assert released.wait(10)
        if kwargs['stop'].is_set():
            status='stopped'
        else:
            kwargs['on_stage']('bo','primary_specialists','completed')
            status='completed'
        return {'case_id':kwargs['case_id'], 'bo':{'status':status,'summary':{'analysis_run_id':'fixture-bo','conclusion_status':'human_review_required'}},
                'fo':{'status':'skipped' if kwargs['bo_only'] else 'completed'}, 'rms':{'status':'skipped','reason':'fixture'}}
    monkeypatch.setattr(bo_fo, 'run_bo_fo', worker)
    yield workspace,jobs,released,started,calls
    released.set()
    for job in jobs.recent():
        if job['execution_status'] in {'pending','running'}:
            for _ in range(200):
                if jobs.get(job['job_id'])['finished_at']:break
                time.sleep(.01)


def submit(client, **values):
    return client.post('/analysis/start', data={'submission_key':uuid.uuid4().hex, **values}, follow_redirects=False)


@pytest.mark.parametrize('sections', ['both','bo','fo'])
@pytest.mark.parametrize('mode', ['standard','exploratory'])
def test_submission_mappings_and_persistent_metadata(execution_env, sections, mode):
    client,jobs,release,started,calls=execution_env
    response=submit(client,sections=sections,validation_mode=mode)
    assert response.status_code==303, response.text
    ident=response.headers['location'].split('/')[2]
    assert started.wait(2)
    kwargs=calls[0]
    assert kwargs['bo_only'] == (sections=='bo')
    assert kwargs['fo_only'] == (sections=='fo')
    assert kwargs['bo_validators'] == (mode=='standard')
    assert kwargs['folder']=='HCA 10-K FY2024'
    assert kwargs['cutoff'].isoformat()=='2025-03-31T23:59:59+00:00'
    job=jobs.get(ident)
    assert job['metadata']['validation_mode']==mode
    assert job['metadata']['submitted_configuration']['sections']==sections
    assert job['stages']['bo:primary_specialists']['status']=='running'
    assert 'specialist test checkpoint' in job['sections']['bo']['steps']
    restored=bo_fo.Jobs(jobs._store_path)
    assert restored.get(ident)['created_at']==job['created_at']
    assert restored.get(ident)['execution_status']=='running' # live worker in same process
    release.set()
    job=wait_for(jobs,ident,'completed')
    assert job['memo_status']=='human_review_required'
    assert job['stages']['bo:primary_specialists']['status']=='completed'
    assert job['result']['bo']['summary']['analysis_run_id']=='fixture-bo'


def test_navigation_refresh_retry_and_intentional_new_run(execution_env):
    client,jobs,release,started,calls=execution_env
    token=uuid.uuid4().hex
    first=submit(client,submission_key=token)
    assert started.wait(2)
    duplicate=submit(client,submission_key=token)
    assert duplicate.headers['location']==first.headers['location']
    for url in ['/', '/credit-memos', first.headers['location'],first.headers['location']]:
        response=client.get(url)
        assert response.status_code==200
    ident=first.headers['location'].split('/')[2]
    page=client.get(first.headers['location']).text
    assert 'Execution Details' in page and 'fetch(' in page and 'primary_specialists' in page
    assert ident in client.get('/credit-memos').text
    assert jobs.get(ident)['stop_requested'] is False
    assert len(calls)==1
    conflict=submit(client,submission_key=token,validation_mode='exploratory')
    assert conflict.status_code==409 and len(calls)==1
    second=submit(client)
    assert second.headers['location']!=first.headers['location']
    assert len(jobs.recent())==2


@pytest.mark.parametrize('values',[{'sections':'specialists'},{'validation_mode':'skip'},{'company':'other'},{'case_id':'../bad'},{'submission_key':'bad'}])
def test_invalid_post_never_launches(execution_env, values):
    client,jobs,_,_,calls=execution_env
    assert submit(client,**values).status_code==400
    assert not calls and not jobs.recent()


def test_missing_evidence_and_provider_prevent_launch(execution_env,evidence,monkeypatch):
    client,jobs,_,_,calls=execution_env
    monkeypatch.setattr(analysis,'execution_backends',lambda sections: (_ for _ in ()).throw(ValueError('No ADC credentials')))
    assert submit(client).status_code==400
    (evidence/'hca-test.htm').unlink()
    assert submit(client).status_code==400
    assert not calls and not jobs.recent()


def test_explicit_stop_persists_and_is_not_instantaneous(execution_env):
    client,jobs,release,started,calls=execution_env
    response=submit(client,sections='bo')
    assert started.wait(2)
    ident=response.headers['location'].split('/')[2]
    assert client.post(f'/analysis/{ident}/stop',follow_redirects=False).status_code==303
    job=jobs.get(ident)
    assert job['stop_requested'] and job['execution_status']=='running'
    assert calls[0]['stop'].is_set()
    release.set()
    wait_for(jobs,ident,'stopped')
    assert ident in client.get('/credit-memos').text


def test_worker_failure_and_interruption_remain_in_history(execution_env,monkeypatch):
    client,jobs,release,started,calls=execution_env
    monkeypatch.setattr(bo_fo,'run_bo_fo',lambda **kwargs: (_ for _ in ()).throw(RuntimeError('synthetic failure')))
    response=submit(client)
    ident=response.headers['location'].split('/')[2]
    failed=wait_for(jobs,ident,'failed')
    assert 'synthetic failure' in failed['error']
    assert 'synthetic failure' in client.get(response.headers['location']).text
    store=jobs._store()
    orphan={**failed,'job_id':'orphan','status':'running','execution_status':'running','finished_at':None}
    store.claim(orphan)
    with store._connect() as con:
        con.execute("UPDATE analysis_jobs SET owner_pid=-1 WHERE job_id='orphan'")
    restarted=bo_fo.Jobs(jobs._store_path)
    assert restarted.get('orphan')['execution_status']=='interrupted'
    page=client.get('/credit-memos').text
    assert ident in page and 'orphan' in page and 'Interrupted' in page and 'Failed' in page
    assert client.get('/analysis/orphan/execution').status_code==200
    assert client.get('/analysis/missing/execution').status_code==404


def test_atomic_claim_prevents_concurrent_workers(tmp_path):
    store=JobStore(tmp_path/'jobs.db')
    def claim(index):
        return store.claim({'job_id':str(index)}, 'same-key','same-request')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(claim,range(16)))
    assert len({ident for ident,created in results})==1
    assert sum(created for ident,created in results)==1
    with pytest.raises(IdempotencyConflict):store.claim({'job_id':'other'},'same-key','different-request')


def test_cross_manager_stop_is_observed_without_browser(tmp_path):
    from app.services.analysis_jobs import StoredStop
    store=JobStore(tmp_path/'jobs.db')
    store.claim({'job_id':'one','execution_status':'running','stop_requested':False})
    stop=StoredStop(store,'one')
    assert JobStore(store.path).request_stop('one')
    assert stop.is_set()
    store.save({'job_id':'one','execution_status':'running','stop_requested':False})
    assert store.get('one')['stop_requested'] # progress cannot erase concurrent stop


def test_committed_partial_output_survives_interruption_and_legacy_view(execution_env, monkeypatch):
    client,jobs,release,started,calls=execution_env
    response=submit(client)
    assert started.wait(2)
    ident=response.headers['location'].split('/')[2]
    calls[0]['on_stage']('fo','recorded_output','completed',{'run_id':'partial-fo','outputs':['fixture-output']})
    assert client.get(f'/run?job={ident}').status_code==200
    job=jobs.get(ident)
    assert job['run_ids']['fo']=='partial-fo'
    assert job['artifacts']['fo']==['fixture-output']
    assert job['result']['fo']['summary']['run_id']=='partial-fo'
    # A simulated worker death retains the committed sibling result.
    with jobs._store()._connect() as con:
        con.execute('UPDATE analysis_jobs SET owner_pid=-1 WHERE job_id=?',(ident,))
    interrupted=jobs.get(ident)
    assert interrupted['execution_status']=='interrupted'
    assert interrupted['result']['fo']['summary']['run_id']=='partial-fo'
    release.set()
    wait_for(jobs,ident,'completed')


def test_worker_thread_termination_is_not_left_running(execution_env,monkeypatch):
    client,jobs,_,_,_=execution_env
    def terminated(**kwargs):
        raise SystemExit('simulated thread termination')
    monkeypatch.setattr(bo_fo,'run_bo_fo',terminated)
    response=submit(client)
    ident=response.headers['location'].split('/')[2]
    job=wait_for(jobs,ident,'interrupted')
    assert 'SystemExit' in job['error']
    assert ident in client.get('/credit-memos').text


def test_delete_finished_run_from_history(execution_env):
    client,jobs,release,started,calls=execution_env
    ident=submit(client).headers['location'].split('/')[2]
    assert started.wait(2)
    page=html.fromstring(client.get('/credit-memos').text)
    assert not page.xpath(f'//article[@data-job-id="{ident}"]//form')  # no delete while running
    assert not page.xpath(f'//article[@data-job-id="{ident}"]//input[@class="select-run"]')
    assert client.post(f'/analysis/{ident}/delete',follow_redirects=False).status_code==409
    release.set()
    wait_for(jobs,ident,'completed')
    page=html.fromstring(client.get('/credit-memos').text)
    assert page.xpath(f'//article[@data-job-id="{ident}"]//form/@action')==[f'/analysis/{ident}/delete']
    assert page.xpath(f'//article[@data-job-id="{ident}"]//input[@class="select-run"]')
    assert page.xpath('//div[@class="bulk-bar"]//button[contains(@class,"delete-selected")]')
    response=client.post(f'/analysis/{ident}/delete',follow_redirects=False)
    assert response.status_code==303 and response.headers['location']==f'/credit-memos?deleted={ident}'
    page=client.get(response.headers['location']).text
    assert f'Deleted run {ident}' in page and f'data-job-id="{ident}"' not in page
    assert jobs.get(ident) is None and bo_fo.Jobs(jobs._store_path).get(ident) is None
    assert client.post(f'/analysis/{ident}/delete',follow_redirects=False).status_code==404
