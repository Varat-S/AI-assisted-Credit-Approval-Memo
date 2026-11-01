"""M4A-03: real thread liveness, SQLite faults, recovery without execution replay."""
import copy
import json
import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from lxml import html
from app.services import bo_fo
from app.services.analysis_jobs import (JobStore, JobStatusUnavailable, JobStorageUnavailable,
                                      PROCESS_SESSION, worker_health)
from tests.integration.test_analysis_execution import execution_env, evidence, workspace, submit
from tests.integration.test_execution_ui_refinement import presentation


@pytest.fixture
def health_env(execution_env, monkeypatch):
    client, jobs, _, _, _ = execution_env
    faults = {'updates':False, 'all':False}
    original = JobStore._connect
    @contextmanager
    def connection(self):
        with original(self) as con:
            if faults['all']:
                raise sqlite3.OperationalError('PRIVATE CREDENTIAL OR EVIDENCE MUST NOT LEAK')
            def authorize(action, table, *args):
                return (sqlite3.SQLITE_DENY if faults['updates'] and action == sqlite3.SQLITE_UPDATE
                        and table == 'analysis_jobs' else sqlite3.SQLITE_OK)
            con.set_authorizer(authorize)
            yield con
    monkeypatch.setattr(JobStore, '_connect', connection)
    releases = []
    created_threads = []
    calls = []
    def start(mode='failed', partial=False, key=None):
        release = threading.Event(); started = threading.Event()
        releases.append(release)
        def worker(**kw):
            calls.append(kw)
            kw['on_progress']('bo','Synthetic worker checkpoint')
            kw['on_stage']('bo','primary_specialists','running')
            kw['on_stage']('fo','workflow','running')
            if partial:
                kw['on_stage']('bo','recorded_output','completed',{'analysis_run_id':'partial-bo','outputs':['bo-output']})
                kw['on_stage']('fo','recorded_output','completed',{'run_id':'partial-fo','outputs':['fo-output']})
            if mode == 'completed':
                for stage in ('foundation','primary_specialists','reconciliation','orchestrator','challenger','memo_preparation'):
                    kw['on_stage']('bo',stage,'completed')
                for stage in ('workflow','reporting'):
                    kw['on_stage']('fo',stage,'completed')
            started.set()
            assert release.wait(10), 'test did not release its synthetic worker'
            if mode == 'progress_failure':
                kw['on_stage']('bo','primary_specialists','completed')
            if mode in {'failed','progress_failure'}:
                raise RuntimeError('Synthetic worker failed')
            if mode == 'interrupted':
                raise SystemExit('Synthetic thread interruption')
            if mode == 'stopped':
                assert kw['stop'].is_set()
            return dict(case_id=kw['case_id'],bo={'status':mode},fo={'status':mode},rms={'status':'skipped'})
        monkeypatch.setattr(bo_fo,'run_bo_fo',worker)
        response = submit(client, **({'submission_key':key} if key else {}))
        assert response.status_code == 303, response.text
        ident = response.headers['location'].split('/')[2]
        assert started.wait(3)
        thread = next(t for t in threading.enumerate() if t.name == 'bo-fo-'+ident)
        created_threads.append(thread)
        return ident, release, thread
    yield client, jobs, faults, start, calls
    faults.update(updates=False, all=False)
    for release in releases:release.set()
    for thread in created_threads:thread.join(3)


def finish(release, thread):
    release.set();thread.join(3)
    assert not thread.is_alive()


def test_write_failure_recovery_converges_across_history_polling_and_partial_links(health_env, tmp_path):
    client,jobs,faults,start,calls = health_env
    ident,release,thread = start(partial=True, key='1'*32)
    before = jobs.get(ident)
    jobs._store().claim({'job_id':'unrelated','execution_status':'completed','created_at':'old','run_ids':{'bo':'other'}})
    untouched = jobs._store().get('unrelated')
    faults['updates'] = True
    finish(release,thread)
    assert jobs._jobs[ident]['execution_status'] == 'failed'
    assert jobs._store().get(ident,recover=False)['execution_status'] == 'running'
    for path in [f'/run/jobs/{ident}', '/credit-memos', f'/analysis/{ident}/execution', f'/analysis/{ident}/review']:
        response = client.get(path)
        assert response.status_code == 503 and 'cannot currently be verified' in response.text
        assert 'PRIVATE CREDENTIAL' not in response.text
    faults['updates'] = False
    recovered = bo_fo.Jobs(jobs._store_path).get(ident) # shared process registry, fresh manager
    assert recovered['execution_status'] == 'failed' and recovered['finished_at']
    assert worker_health(jobs._store_path,ident)['persistence_failed'] is False
    assert recovered['created_at'] == before['created_at'] and recovered['started_at'] == before['started_at']
    assert recovered['run_ids'] == {'bo':'partial-bo','fo':'partial-fo'}
    assert recovered['artifacts'] == {'bo':['bo-output'],'fo':['fo-output']}
    assert recovered['result']['bo']['summary']['analysis_run_id'] == 'partial-bo'
    assert recovered['result']['fo']['summary']['run_id'] == 'partial-fo'
    assert recovered['finished_at'] == jobs._jobs[ident]['finished_at']
    assert client.get(f'/run/jobs/{ident}').json()['execution_status'] == 'failed'
    history = client.get('/credit-memos?search='+ident)
    assert history.status_code == 200 and 'Failed' in history.text and ident in history.text
    execution = client.get(f'/analysis/{ident}/execution')
    assert execution.status_code == 200 and 'Review recorded partial results' in execution.text
    assert "open.href='/analysis/'+encodeURIComponent(job.job_id)+'/review'" in execution.text
    view = presentation(tmp_path,recovered)
    assert view['findings'] != 'running' and view['status'] == 'failed'
    for _ in range(4):assert jobs.get(ident)['execution_status'] == 'failed'
    assert jobs._store().get('unrelated') == untouched
    assert len(calls) == 1
    same = submit(client, submission_key='1'*32)
    assert same.status_code == 303 and same.headers['location'] == f'/analysis/{ident}/execution'
    assert len(calls) == 1
    with jobs._store()._connect() as con:
        assert con.execute('SELECT request_key FROM analysis_jobs WHERE job_id=?',(ident,)).fetchone()[0] == '1'*32
        assert con.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0] == 2


@pytest.mark.parametrize('terminal', ['completed','stopped','interrupted','progress_failure'])
def test_terminal_semantics_survive_final_write_failure(health_env, terminal):
    client,jobs,faults,start,calls = health_env
    ident,release,thread = start(terminal)
    if terminal == 'stopped':assert jobs.stop(ident)
    faults['updates'] = True
    finish(release,thread)
    faults['updates'] = False
    recovered = jobs.get(ident)
    expected = 'failed' if terminal == 'progress_failure' else terminal
    assert recovered['execution_status'] == expected
    assert recovered['stop_requested'] == (terminal == 'stopped')
    assert client.get('/run/jobs/'+ident).json()['execution_status'] == expected
    assert len(calls) == 1


def test_blocked_worker_has_no_progress_timeout(health_env):
    client,jobs,_,start,calls = health_env
    ident,release,thread = start()
    with jobs._store()._connect() as con:
        job = json.loads(con.execute('SELECT payload FROM analysis_jobs WHERE job_id=?',(ident,)).fetchone()[0])
        job.update(created_at='1999-01-01T00:00:00Z',started_at='1999-01-01T00:00:00Z')
        con.execute('UPDATE analysis_jobs SET payload=? WHERE job_id=?',(json.dumps(job),ident))
    for _ in range(5):
        assert bo_fo.Jobs(jobs._store_path).get(ident)['execution_status'] == 'running'
        assert client.get('/run/jobs/'+ident).status_code == 200
    assert thread.is_alive() and len(calls) == 1
    finish(release,thread)


def test_read_outage_is_not_worker_death_and_errors_are_sanitized(health_env, caplog):
    client,jobs,faults,start,_ = health_env
    ident,release,thread = start()
    faults['all'] = True
    for path in ['/credit-memos',f'/run/jobs/{ident}',f'/analysis/{ident}/execution',f'/analysis/{ident}/stop']:
        response = client.post(path) if path.endswith('/stop') else client.get(path)
        assert response.status_code == 503
        assert response.headers['retry-after'] == '4'
        assert 'PRIVATE CREDENTIAL' not in response.text and 'Traceback' not in response.text
    assert thread.is_alive() and 'PRIVATE CREDENTIAL' not in caplog.text
    assert 'OperationalError' in caplog.text
    faults['all'] = False
    assert jobs.get(ident)['execution_status'] == 'running'
    finish(release,thread)


def test_repeated_storage_failure_has_bounded_attempts_and_no_unhandled_thread_error(health_env, monkeypatch):
    client,jobs,faults,start,calls = health_env
    errors=[];monkeypatch.setattr(threading,'excepthook',lambda args:errors.append(args.exc_value))
    ident,release,thread = start('progress_failure')
    faults['updates'] = True
    finish(release,thread)
    for _ in range(6):
        response=client.get('/run/jobs/'+ident)
        assert response.status_code == 503
    assert not errors and len(calls) == 1
    faults['updates'] = False
    assert jobs.get(ident)['execution_status'] == 'failed'


def test_concurrent_cleanup_polling_and_cancellation_never_restarts(health_env):
    client,jobs,faults,start,calls = health_env
    ident,release,thread = start(partial=True)
    faults['updates'] = True
    finish(release,thread)
    faults['updates'] = False
    def operation(index):
        if index%3 == 0:
            jobs.stop(ident)
        return jobs.get(ident)
    with ThreadPoolExecutor(max_workers=8) as pool:
        records=list(pool.map(operation,range(24)))
    assert {r['execution_status'] for r in records} == {'failed'}
    assert len({r['status_recovered_at'] for r in records}) == 1
    assert all(r['run_ids'] == {'bo':'partial-bo','fo':'partial-fo'} for r in records)
    assert len(calls) == 1


@pytest.mark.parametrize('terminal', ['completed','failed','stopped','interrupted'])
def test_stale_running_snapshot_cannot_downgrade_terminal_job(tmp_path, terminal):
    store=JobStore(tmp_path/'terminal.sqlite')
    original=dict(job_id='saved',status='finished' if terminal=='completed' else terminal,
                  execution_status=terminal,created_at='original',finished_at='original-finish',
                  run_ids={'bo':'preserved'},result={'bo':{'status':'completed','summary':{'analysis_run_id':'preserved'}}})
    store.claim(original)
    store.save({'job_id':'saved','execution_status':'running','result':None})
    assert store.get('saved') == original


@pytest.mark.parametrize('terminal', ['completed','failed','stopped','interrupted'])
def test_old_terminal_records_do_not_require_worker_metadata(tmp_path, terminal):
    store=JobStore(tmp_path/'legacy.sqlite')
    job=dict(job_id='historical',execution_status=terminal,status=terminal,created_at='old',
             finished_at='unchanged',run_ids={'fo':'recorded'},worker_health='unverified')
    store.claim(job)
    jobs=bo_fo.Jobs(store.path)
    assert jobs.get('historical') == job


def test_unknown_live_legacy_owner_is_explicitly_unverified(health_env):
    client,jobs,_,_,calls = health_env
    old=dict(job_id='legacy-live',execution_status='running',status='running',created_at='old',run_ids={'fo':'recorded'})
    jobs._store().claim(old)
    for path in ['/run/jobs/legacy-live','/credit-memos']:
        assert client.get(path).status_code == 503
    with jobs._store()._connect() as con:
        payload=json.loads(con.execute('SELECT payload FROM analysis_jobs WHERE job_id=?',('legacy-live',)).fetchone()[0])
    assert payload == old and not calls
    # Let the parent execution fixture clean up this deliberately unowned row.
    with jobs._store()._connect() as con:
        con.execute("UPDATE analysis_jobs SET owner_pid=-1 WHERE job_id='legacy-live'")


def test_managed_record_without_registered_worker_is_interrupted(tmp_path):
    store=JobStore(tmp_path/'missing-thread.sqlite')
    store.claim(dict(job_id='lost',execution_status='running',worker_tracking='thread-v1',created_at='old',run_ids={'bo':'partial'}))
    job=bo_fo.Jobs(store.path).get('lost')
    assert job['execution_status'] == 'interrupted' and job['run_ids']['bo']=='partial'


def test_real_process_exit_preserves_ids_and_idempotency_without_resumption(tmp_path, monkeypatch):
    path=tmp_path/'restart.sqlite'
    script="""from app.services.analysis_jobs import JobStore
import sys
JobStore(sys.argv[1]).claim(dict(job_id='exited',execution_status='running',created_at='old',worker_tracking='thread-v1',run_ids={'fo':'partial'}),'fixed-key','same-request')
"""
    subprocess.run([sys.executable,'-c',script,str(path)],check=True)
    jobs=bo_fo.Jobs(path)
    assert jobs.get('exited')['execution_status']=='interrupted'
    assert jobs.get('exited')['run_ids']['fo']=='partial'
    def forbidden(**kw):pytest.fail('Recovery must never execute the pipeline')
    monkeypatch.setattr(bo_fo,'run_bo_fo',forbidden)
    assert jobs.start(database=tmp_path/'unused.db',folder='offline',idempotency_key='fixed-key',request_hash='same-request')=='exited'
    assert len(jobs.recent()) == 1


def test_missing_record_is_not_silently_reported_as_success(health_env):
    client,jobs,_,start,_ = health_env
    ident,release,thread=start()
    with jobs._store()._connect() as con:con.execute('DELETE FROM analysis_jobs WHERE job_id=?',(ident,))
    finish(release,thread)
    assert client.get('/run/jobs/'+ident).status_code == 503
    assert client.get('/credit-memos').status_code == 503
    assert jobs._jobs[ident]['persistence_error']
    jobs._persistent.discard(ident)  # Disposable fixture teardown, not recovery.


def test_atomic_registration_precedes_visible_claim(health_env, monkeypatch):
    client,jobs,_,_,_ = health_env
    entered=threading.Event();allow=threading.Event();release=threading.Event()
    original=threading.Thread.start
    def delayed(self):
        if self.name.startswith('bo-fo-'):
            entered.set();assert allow.wait(5)
        return original(self)
    def worker(**kw):
        assert release.wait(5)
        return dict(case_id=kw['case_id'],bo={'status':'completed'},fo={'status':'completed'},rms={'status':'skipped'})
    monkeypatch.setattr(threading.Thread,'start',delayed)
    monkeypatch.setattr(bo_fo,'run_bo_fo',worker)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(submit,client)
        try:
            assert entered.wait(3)
            record=jobs.recent()[0]
            assert record['execution_status']=='pending'
            assert worker_health(jobs._store_path,record['job_id'])['alive']
        finally:
            allow.set();release.set()
        assert future.result().status_code == 303


def test_failed_thread_start_recovers_without_launch(health_env, monkeypatch):
    client,jobs,_,_,calls=health_env
    original=threading.Thread.start
    def fail(self):
        if self.name.startswith('bo-fo-'):raise RuntimeError('PRIVATE start error')
        return original(self)
    monkeypatch.setattr(threading.Thread,'start',fail)
    response=submit(client)
    ident=response.headers['location'].split('/')[2]
    job=jobs.get(ident)
    assert job['execution_status']=='failed' and not calls
    assert 'PRIVATE' not in client.get('/run/jobs/'+ident).text


def test_alive_worker_with_failed_status_writes_is_unverified_not_dead(health_env, monkeypatch):
    client,jobs,faults,_,_ = health_env
    started=threading.Event();attempt=threading.Event();blocked=threading.Event();release=threading.Event()
    def worker(**kw):
        kw['on_stage']('bo','primary_specialists','running');started.set()
        assert attempt.wait(5)
        try:kw['on_progress']('bo','write fails while sibling request is still blocked')
        except JobStorageUnavailable:pass  # Simulates waiting for a sibling request to finish.
        blocked.set();assert release.wait(5)
        raise RuntimeError('Synthetic worker termination')
    monkeypatch.setattr(bo_fo,'run_bo_fo',worker)
    response=submit(client);ident=response.headers['location'].split('/')[2]
    assert started.wait(3)
    thread=next(t for t in threading.enumerate() if t.name=='bo-fo-'+ident)
    try:
        faults['updates']=True;attempt.set();assert blocked.wait(3)
        assert thread.is_alive()
        assert client.get('/run/jobs/'+ident).status_code == 503
        assert jobs._store().get(ident,recover=False)['execution_status']=='running'
        faults['updates']=False
        assert client.get('/run/jobs/'+ident).status_code == 503 # Still unverified until an update succeeds.
    finally:
        release.set();thread.join(3)
    assert jobs.get(ident)['execution_status']=='failed'


def test_cleanup_and_cancellation_polling_race_preserves_the_same_job(health_env, monkeypatch):
    _,jobs,faults,start,calls=health_env
    entered=threading.Event();allow=threading.Event();original=JobStore.save
    def paused(self,job):
        if job.get('finished_at'):
            entered.set();assert allow.wait(5)
        return original(self,job)
    monkeypatch.setattr(JobStore,'save',paused)
    ident,release,thread=start(partial=True)
    release.set();assert entered.wait(3)
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            reads=list(pool.map(lambda _:jobs.get(ident),range(12)))
        assert all(r['execution_status']=='running' for r in reads) # Cleanup thread is still alive.
        assert thread.is_alive()
    finally:
        allow.set();thread.join(3)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _:jobs.stop(ident),range(8)))
    assert jobs.get(ident)['execution_status']=='failed'
    assert jobs.get(ident)['run_ids']=={'bo':'partial-bo','fo':'partial-fo'}
    assert len(calls)==1


def test_storage_unavailable_before_claim_cannot_launch_worker(health_env):
    client,jobs,faults,_,calls=health_env
    faults['all']=True
    response=submit(client)
    assert response.status_code==503 and not calls
    assert 'PRIVATE' not in response.text
    faults['all']=False
    assert jobs.recent()==[]


def test_intentional_new_submission_is_separate_from_recovery(health_env):
    _,jobs,faults,start,calls=health_env
    first,release,thread=start(key='3'*32)
    faults['updates']=True;finish(release,thread);faults['updates']=False
    assert jobs.get(first)['execution_status']=='failed' and len(calls)==1
    second,release,thread=start(key='4'*32)
    assert first!=second and len(calls)==2
    finish(release,thread)


def test_missing_record_guard_is_scoped_to_its_database(tmp_path, monkeypatch):
    from app.core.config import Settings
    import app.core.config as config
    active={'db':tmp_path/'first.db'}
    monkeypatch.setattr(config,'get_settings',lambda:Settings(_env_file=None,database_url='sqlite:///'+str(active['db'])))
    release=threading.Event();entered=threading.Event()
    def worker(**kw):
        entered.set();assert release.wait(5)
        return dict(case_id='CASE',bo={'status':'completed'},fo={'status':'skipped'},rms={'status':'skipped'})
    monkeypatch.setattr(bo_fo,'run_bo_fo',worker)
    jobs=bo_fo.Jobs()
    ident=jobs.start(database=active['db'],folder='offline')
    assert entered.wait(3)
    thread=next(t for t in threading.enumerate() if t.name=='bo-fo-'+ident)
    finish(release,thread)
    assert jobs.get(ident)['execution_status']=='completed'
    active['db']=tmp_path/'second.db'
    assert jobs.recent()==[] and jobs.get(ident) is None
    active['db']=tmp_path/'first.db'
    assert jobs.get(ident)['execution_status']=='completed'
