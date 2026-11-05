"""Read exact workflow/run bindings without opening a writable application session.

The durable job record is the authority for joining BO and FO. A common case
name, directory order or latest output never establishes a workflow binding.
"""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3

from app.services.analysis_workspace import run_references, WorkspaceRecordError


class WorkflowScopeError(ValueError):
    pass


def recorded_workflows(database_url: str, case_id: str) -> list[dict]:
    prefix = 'sqlite:///'
    if not database_url.startswith(prefix):
        return []
    database = database_url[len(prefix):]
    if database == ':memory:' or '?' in database:
        return []
    path = Path(database).resolve()
    path = path.with_name(path.name + '.jobs.sqlite')
    if not path.is_file():
        return []
    try:
        # No schema initialization, migration, recovery or writes on a viewer GET.
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
            rows = connection.execute('SELECT job_id, payload FROM analysis_jobs').fetchall()
    except sqlite3.Error as exc:
        raise WorkflowScopeError('Recorded workflow references could not be read.') from exc
    workflows = []
    for ident, encoded in rows:
        try:
            job = json.loads(encoded)
        except (ValueError, TypeError) as exc:
            raise WorkflowScopeError('Recorded workflow references contain unreadable JSON.') from exc
        if not isinstance(job, dict) or job.get('case_id') != case_id:
            continue
        workflow = dict(workflow_id=ident, case_id=case_id, run_ids={}, available=True,
                        execution_status=job.get('execution_status'), error=None)
        try:
            if job.get('job_id') != ident:
                raise WorkspaceRecordError('Workflow identity differs from its stored job identity.')
            refs = run_references(job)
            rms = ((job.get('result') or {}).get('rms') or {}).get('summary') or {}
            stored = (job.get('run_ids') or {}).get('rms')
            if stored and rms.get('run_id') and stored != rms['run_id']:
                raise WorkspaceRecordError('The selected job has conflicting RMS references.')
            refs['rms'] = stored or rms.get('run_id')
            workflow['run_ids'] = {key: value for key, value in refs.items() if value}
            if not all(isinstance(v, str) for v in workflow['run_ids'].values()):
                raise WorkspaceRecordError('The selected job has invalid run references.')
            if not workflow['run_ids']:
                workflow.update(available=False, error='No stage outputs have been recorded for this workflow.')
        except (WorkspaceRecordError, TypeError, AttributeError) as exc:
            workflow.update(available=False, error=str(exc))
        workflows.append(workflow)
    return sorted(workflows, key=lambda item: item['workflow_id'])
