"""Small SQLite sidecar for browser jobs; never stores provider objects or credentials.

The BO holds its analysis transaction across model calls. A sidecar keeps polling,
submission and cancellation independent of that lock. No automatic paid retries.
"""
import json
import copy
import logging
import os
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PROCESS_SESSION = uuid.uuid4().hex
ACTIVE = {'pending', 'running'}


def now():
    return datetime.now(timezone.utc).isoformat()


def store_path(database):
    database = Path(database).resolve()
    return database.with_name(database.name + '.jobs.sqlite')


def owner_alive(pid, session):
    if pid == os.getpid():
        return session == PROCESS_SESSION
    if pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) terminates the process on Windows; query it instead.
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            # Access denied means the process exists; anything else means it is gone.
            return ctypes.get_last_error() == 5 or kernel32.GetLastError() == 5
        try:
            code = ctypes.c_ulong()
            alive = kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        return bool(alive)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class IdempotencyConflict(ValueError):
    pass

# Process-local thread ownership. No expiry/heartbeat: a blocked provider call is
# still alive. Entries retain terminal snapshots until shutdown so failed writes
# can be reconciled by another Jobs instance without restarting paid execution.
_worker_lock = threading.RLock()
_workers = {}
TERMINAL = {'completed', 'failed', 'stopped', 'interrupted'}
log = logging.getLogger(__name__)


class JobStatusUnavailable(RuntimeError):
    """A recorded status cannot currently be verified; never a new job state."""


class JobStorageUnavailable(JobStatusUnavailable):
    pass


def storage_failure(exc):
    # Do not log the exception message/traceback: it can contain paths/secrets.
    log.warning('Analysis job storage unavailable; error_type=%s', type(exc).__name__)
    return JobStorageUnavailable('Analysis status cannot currently be verified because job storage is unavailable. No analysis has been restarted.')


def _worker_key(path, ident):
    return str(Path(path).resolve()), ident


def register_worker(path, ident, thread):
    with _worker_lock:
        _workers[_worker_key(path, ident)] = dict(thread=thread, terminal=None, launch_failed=False,
                                                 persistence_failed=False)


def forget_worker(path, ident):
    with _worker_lock:
        _workers.pop(_worker_key(path, ident), None)


def publish_terminal(path, job, *, launch_failed=False):
    with _worker_lock:
        entry = _workers.get(_worker_key(path, job['job_id']))
        if entry is not None:
            entry['terminal'] = copy.deepcopy(job)
            entry['launch_failed'] = launch_failed or entry['launch_failed']


def persistence_health(path, ident, *, failed):
    with _worker_lock:
        entry = _workers.get(_worker_key(path, ident))
        if entry is not None:
            entry['persistence_failed'] = failed


def worker_health(path, ident):
    with _worker_lock:
        entry = _workers.get(_worker_key(path, ident))
        if entry is None:
            return None
        thread = entry['thread']
        # Registration precedes the atomic claim; polling during Thread.start
        # must not declare an as-yet unstarted thread dead.
        alive = thread.is_alive() or (thread.ident is None and not entry['launch_failed'])
        return dict(alive=alive, terminal=copy.deepcopy(entry['terminal']),
                    persistence_failed=entry['persistence_failed'])


def finish_record(job):
    """Normalize observed termination, retaining completed sections/references."""
    execution = job['execution_status']
    job['finished_at'] = job.get('finished_at') or now()
    stages = job.get('stages') or {}
    sections = job.get('sections') or {}
    for section, state in sections.items():
        result = (job.get('result') or {}).get(section) or {}
        summary = result.get('summary') or {}
        if result.get('status') == 'completed' and (summary.get('analysis_run_id') or summary.get('run_id')):
            state['status'] = 'completed'
        elif state.get('status') in ACTIVE | {'waiting'} and execution != 'completed':
            state.update(status='failed' if execution == 'failed' else 'stopped',
                         step='Worker ended before this section completed')
    for key, state in stages.items():
        previous = state.get('status')
        if previous == 'running':
            state.update(status='stopped' if execution in {'stopped','interrupted'} else 'failed',
                         detail=job.get('error') or 'Execution ended before this stage completed',
                         finished_at=job['finished_at'])
        elif previous == 'pending':
            state.update(status='skipped', detail='Not reached during this execution')
        else:
            continue
        # Recovered termination must not leave a stale last-running UI event.
        section, _, stage = key.partition(':')
        job.setdefault('events', []).append(dict(section=section, stage=stage,
            status=state['status'], detail=state.get('detail'), at=job['finished_at']))
    return job


def merge_record(previous, incoming):
    """Never regress terminal work or lose a concurrently recorded stop/output."""
    if (previous.get('execution_status') == 'completed' or
            previous.get('execution_status') in TERMINAL and incoming.get('execution_status') in ACTIVE):
        return copy.deepcopy(previous)
    merged = {**previous, **copy.deepcopy(incoming)}
    for key in ('run_ids', 'artifacts'):
        if key in previous or key in incoming:
            merged[key] = {**(previous.get(key) or {}), **(incoming.get(key) or {})}
    if previous.get('result'):
        results = {**previous['result'], **(incoming.get('result') or {})}
        for section, recorded in previous['result'].items():
            summary = recorded.get('summary') or {} if isinstance(recorded, dict) else {}
            new_summary = (results.get(section) or {}).get('summary') or {}
            if ((summary.get('analysis_run_id') or summary.get('run_id'))
                    and not (new_summary.get('analysis_run_id') or new_summary.get('run_id'))):
                results[section] = recorded
        merged['result'] = results
    if previous.get('stop_requested'):
        merged.update(stop_requested=True, stop_requested_at=previous.get('stop_requested_at'))
    return merged


class JobStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _connect(self):
        con = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(self.path, timeout=15)
            con.execute('''CREATE TABLE IF NOT EXISTS analysis_jobs (
                job_id TEXT PRIMARY KEY, owner_pid INTEGER NOT NULL,
                owner_session TEXT NOT NULL, payload TEXT NOT NULL,
                request_key TEXT UNIQUE, request_hash TEXT)''')
            con.execute('PRAGMA user_version=1')
            con.execute('BEGIN IMMEDIATE')
            with con:
                yield con
        except (OSError, sqlite3.Error) as exc:
            raise storage_failure(exc) from exc
        finally:
            if con is not None:
                try:
                    con.close()
                except (OSError, sqlite3.Error) as exc:
                    raise storage_failure(exc) from exc

    def claim(self, job, key=None, fingerprint=None):
        with self._connect() as con:
            if key:
                previous = con.execute('SELECT job_id,request_hash FROM analysis_jobs WHERE request_key=?', (key,)).fetchone()
                if previous:
                    if previous[1] != fingerprint:
                        raise IdempotencyConflict('This submission key was already used with different settings. Open New Analysis for a separate run.')
                    return previous[0], False
            con.execute('INSERT INTO analysis_jobs VALUES (?,?,?,?,?,?)',
                        (job['job_id'], os.getpid(), PROCESS_SESSION, json.dumps(job), key, fingerprint))
        return job['job_id'], True

    def save(self, job):
        with self._connect() as con:
            previous = con.execute('SELECT payload FROM analysis_jobs WHERE job_id=?', (job['job_id'],)).fetchone()
            if previous is None:
                raise JobStorageUnavailable('Analysis status cannot currently be verified because its job record is unavailable. No analysis has been restarted.')
            if previous:
                merged = merge_record(json.loads(previous[0]), job)
                job.clear()
                job.update(merged)
            con.execute('UPDATE analysis_jobs SET payload=? WHERE job_id=?', (json.dumps(job), job['job_id']))

    def _read(self, job_id=None, recover=True):
        if not self.path.exists():
            return []
        reconciled = []
        with self._connect() as con:
            rows = con.execute('SELECT job_id,owner_pid,owner_session,payload FROM analysis_jobs'
                               + (' WHERE job_id=?' if job_id else ''), (job_id,) if job_id else ()).fetchall()
            jobs = []
            for ident, pid, session, payload in rows:
                job = json.loads(payload)
                if not isinstance(job, dict) or job.get('job_id', ident) != ident:
                    raise JobStatusUnavailable('The recorded analysis status could not be verified. No analysis has been restarted.')
                job.setdefault('job_id', ident)
                if not job.get('execution_status'):
                    legacy = 'completed' if job.get('status') == 'finished' else job.get('status')
                    if legacy in ACTIVE | TERMINAL:
                        job['execution_status'] = legacy
                    else:
                        job['worker_health'] = 'unverified'
                if recover and job.get('execution_status') in ACTIVE:
                    health = worker_health(self.path, ident) if pid == os.getpid() and session == PROCESS_SESSION else None
                    terminal = None
                    if not owner_alive(pid, session):
                        terminal = 'The worker process ended before completion. No automatic retry was started.'
                    elif health is not None and health['alive'] and health['persistence_failed']:
                        raise JobStorageUnavailable('Analysis status cannot currently be verified because worker status updates could not be persisted. No analysis has been restarted.')
                    elif health is not None and not health['alive']:
                        snapshot = health['terminal']
                        if snapshot and snapshot.get('execution_status') in TERMINAL:
                            job = merge_record(job, snapshot)
                        else:
                            terminal = 'The analysis worker ended without a terminal record. No automatic retry was started.'
                    elif health is None:
                        if pid == os.getpid() and session == PROCESS_SESSION and job.get('worker_tracking') == 'thread-v1':
                            terminal = 'No registered analysis worker remains for this job. No automatic retry was started.'
                        else:
                            # Legacy/live foreign-process records lack proof of a
                            # particular thread. Keep data; report uncertainty.
                            job['worker_health'] = 'unverified'
                    if terminal:
                        job.update(status='interrupted', execution_status='interrupted',
                                   error=terminal, memo_status='unavailable_or_incomplete')
                        finish_record(job)
                    if job.get('execution_status') in TERMINAL:
                        job.pop('worker_health', None)
                        job['status_recovered_at'] = now()
                        con.execute('UPDATE analysis_jobs SET payload=? WHERE job_id=?', (json.dumps(job), ident))
                        reconciled.append(ident)
                jobs.append(job)
        # Only acknowledge persistence after the transaction actually commits.
        for ident in reconciled:
            persistence_health(self.path, ident, failed=False)
        return jobs

    def get(self, job_id, recover=True):
        rows = self._read(job_id, recover)
        return rows[0] if rows else None

    def recent(self):
        return sorted(self._read(), key=lambda job: job.get('created_at') or '', reverse=True)

    def request_stop(self, job_id):
        if not self.path.exists():
            return False
        with self._connect() as con:
            row = con.execute('SELECT payload FROM analysis_jobs WHERE job_id=?', (job_id,)).fetchone()
            if not row:
                return False
            job = json.loads(row[0])
            if job['execution_status'] not in ACTIVE:
                return False
            job['stop_requested'] = True
            job['stop_requested_at'] = now()
            con.execute('UPDATE analysis_jobs SET payload=? WHERE job_id=?', (json.dumps(job), job_id))
            return True

    def delete(self, job_id):
        """Remove a finished analysis's record; None when unknown, False while it is still active."""
        if not self.path.exists():
            return None
        with self._connect() as con:
            row = con.execute('SELECT payload FROM analysis_jobs WHERE job_id=?', (job_id,)).fetchone()
            if not row:
                return None
            if json.loads(row[0]).get('execution_status') in ACTIVE:
                return False
            con.execute('DELETE FROM analysis_jobs WHERE job_id=?', (job_id,))
            return True


class StoredStop(threading.Event):
    def __init__(self, store, job_id):
        super().__init__()
        self.store, self.job_id = store, job_id

    def is_set(self):
        if not super().is_set():
            job = self.store.get(self.job_id, recover=False)
            if job is None:
                raise JobStorageUnavailable('Analysis status cannot currently be verified because its job record is unavailable. No analysis has been restarted.')
            if job and job.get('stop_requested'):
                self.set()
        return super().is_set()
