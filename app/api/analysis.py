"""Setup, execution monitoring and durable run history over the existing BO/FO worker."""
from pathlib import Path
import hashlib
import json
import uuid
from urllib.parse import quote
from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_session
from app.services import analysis_workspace
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.config import get_settings
from app.services import bo_fo
from app.services.fo import precheck
from app.services.analysis_jobs import IdempotencyConflict, JobStatusUnavailable
from jinja2 import Environment, FileSystemLoader
from app.services.analysis_setup import company_registry, validate_setup, provider_configuration, SetupError

router = APIRouter(tags=["analysis workspace"])
_env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")), autoescape=True)


@router.get("/analysis/new", response_class=HTMLResponse)
def new_analysis(company: str = "hca", sections: str = "both", validation_mode: str = "standard",
                 cutoff: str = "", case_id: str = "", check: str = ""):
    values = dict(company=company, sections=sections, validation_mode=validation_mode,
                  cutoff=cutoff, case_id=case_id)
    companies, selection, errors = [], None, []
    try:
        companies = company_registry()
        selection = validate_setup(**values)
    except SetupError as exc:
        errors.append(str(exc))
    providers = provider_configuration(sections if sections in {"bo", "both"} else "both")
    if not providers["bo_configured"]:
        errors.append("Business Overview provider settings are unavailable. Configure the AI provider before starting an analysis.")
    if sections == "both" and not providers["fo_configured"]:
        errors.append("Financial Overview provider settings are unavailable. Configure them before starting a combined analysis.")
    invalid_choice = company not in {c["id"] for c in companies} or sections not in {"bo", "both"} or validation_mode not in {"standard", "exploratory"}
    return HTMLResponse(_env.get_template("analysis_setup.html.j2").render(
        values=values, companies=companies, selection=selection, errors=errors,
        providers=providers, checked=bool(check), execution_enabled=selection is not None and not errors,
        submission_key=uuid.uuid4().hex),
        status_code=400 if invalid_choice or (check and errors) else 200)


@router.get("/credit-memos", response_class=HTMLResponse)
def credit_memos(search: str = "", status: str = "", mode: str = "", session: Session = Depends(get_session)):
    if status and status not in analysis_workspace.EXECUTION_STATES or mode and mode not in {'standard','exploratory'}:
        raise HTTPException(400, 'Unknown history filter.')
    rows = analysis_workspace.history(session, bo_fo.jobs.recent(), search=search, status=status, mode=mode)
    return HTMLResponse(_env.get_template("credit_memos.html.j2").render(
        rows=rows, search=search, selected_status=status, selected_mode=mode,
        statuses=analysis_workspace.EXECUTION_STATES), headers={'Cache-Control':'no-store'})


def execution_backends(sections):
    """Local provider/SDK/credential discovery only. Never generates a response."""
    bo = bo_fo.bo_live_backend()
    m3 = bo_fo.m3_live_backend()
    fo = precheck.live_backend() if sections == 'both' else None
    # Vertex's SDK discovers ADC here; this does not issue a generation request.
    from app.services.llm.providers_vertex import VertexProviderBackend
    for backend in (bo, m3, fo):
        if isinstance(backend, VertexProviderBackend):
            client = backend._client()
            close = getattr(client, 'close', None)
            if close:
                close()
    return bo, m3, fo


@router.post('/analysis/start')
def start_analysis(company: str = Form('hca'), sections: str = Form('both'),
                   validation_mode: str = Form('standard'), cutoff: str = Form(''),
                   case_id: str = Form(''), submission_key: str = Form(...)):
    try:
        if len(submission_key) != 32 or uuid.UUID(submission_key).hex != submission_key:
            raise SetupError('Invalid submission key. Open New Analysis and submit again.')
        selection = validate_setup(company=company, sections=sections, validation_mode=validation_mode,
                                   cutoff=cutoff, case_id=case_id)
        parameters = selection.backend_parameters()
        settings = get_settings()
        database = bo_fo.sqlite_path(settings.database_url)
        settled = bo_fo.plan(parameters['folder'], parameters['case_id'] or None, selection.cutoff)
        bo_backend, m3_backend, fo_backend = execution_backends(sections)
        metadata = dict(company_id=selection.company['id'], company=selection.company['label'],
                        reporting_period=selection.evidence['report_date'].isoformat(),
                        evidence_package=selection.evidence['folder'], validation_mode=validation_mode,
                        scope=sections, submitted_configuration=parameters,
                        approval_policy=selection.approval_policy)
        fingerprint = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        job_id = bo_fo.jobs.start(
            database=database, folder=parameters['folder'], case_id=settled['case_id'],
            cutoff=selection.cutoff, bo_backend=bo_backend, m3_backend=m3_backend, fo_backend=fo_backend,
            fo_mode='live', output_root=settings.output_dir, data_root=settings.data_dir,
            bo_only=sections == 'bo', bo_validators=parameters['bo_validators'] == 'on',
            metadata=metadata, idempotency_key=submission_key, request_hash=fingerprint)
    except IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except JobStatusUnavailable:
        raise
    except Exception as exc:
        raise HTTPException(400, f'The analysis cannot start: {exc}') from exc
    return RedirectResponse(f'/analysis/{job_id}/execution', status_code=303)


@router.get('/analysis/{job_id}/execution', response_class=HTMLResponse)
def execution(job_id: str):
    job = bo_fo.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, 'Unknown analysis.')
    return HTMLResponse(_env.get_template('analysis_execution.html.j2').render(job=job),
                        headers={'Cache-Control':'no-store'})


@router.post('/analysis/{job_id}/stop')
def stop_analysis(job_id: str):
    if bo_fo.jobs.get(job_id) is None:
        raise HTTPException(404, 'Unknown analysis.')
    bo_fo.jobs.stop(job_id)
    return RedirectResponse(f'/analysis/{job_id}/execution', status_code=303)


def _selected_workspace(session, job_id):
    from app.services.pipeline.artifacts import ArtifactIntegrityError
    from app.services.bo.handoff import HandoffError
    from pydantic import ValidationError
    from app.services.bo.workbench import BoRunNotFoundError
    job = bo_fo.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, 'Unknown analysis.')
    try:
        return job, analysis_workspace.load_review(session, job)
    except (analysis_workspace.WorkspaceRecordError, ArtifactIntegrityError, HandoffError, ValidationError) as exc:
        raise HTTPException(409, 'The selected run could not be verified. Its records require attention.') from exc
    except BoRunNotFoundError as exc:
        raise HTTPException(404, 'A report for the selected run is unavailable.') from exc


@router.get('/analysis/{job_id}/review', response_class=HTMLResponse)
def review_analysis(job_id: str, session: Session = Depends(get_session)):
    job, view = _selected_workspace(session, job_id)
    if job.get('execution_status') in {'pending','running'}:
        return RedirectResponse(f'/analysis/{quote(job_id, safe="")}/execution', status_code=303)
    from app.services.analysis_audit import public_record
    display = {**view, **{key:public_record(view[key]) for key in ('memo','synthesis','financial','sources','reason')}}
    return HTMLResponse(_env.get_template('analysis_review.html.j2').render(job=job, view=display),
                        headers={'Cache-Control':'no-store'})


@router.get('/analysis/{job_id}/audit', response_class=HTMLResponse)
def audit_analysis(job_id: str, session: Session = Depends(get_session)):
    from app.services.analysis_audit import build_audit, public_record
    from app.services.pipeline.artifacts import ArtifactIntegrityError
    job, view = _selected_workspace(session, job_id)
    try:
        audit = build_audit(session, view)
    except (analysis_workspace.WorkspaceRecordError, ArtifactIntegrityError) as exc:
        raise HTTPException(409, 'The selected audit records could not be verified.') from exc
    # Display copies only. ORM references are used solely for exact existing review links.
    display = {**view, 'financial':public_record(view['financial']), 'reason':public_record(view['reason'])}
    return HTMLResponse(_env.get_template('analysis_audit.html.j2').render(
        job=job, view=display, audit=audit, anchor=analysis_workspace.anchor),
        headers={'Cache-Control':'no-store'})
