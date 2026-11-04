"""Setup, execution monitoring and durable run history over the existing BO/FO worker."""
from pathlib import Path
import hashlib
import json
import re
import uuid
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from sqlalchemy.orm import Session
from app.api.deps import get_session
from app.services import analysis_workspace
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from app.core.config import get_settings
from app.services import bo_fo
from app.services.acquisition import shared_filing
from app.services.acquisition.sec_edgar import EdgarError, SecEdgarClient
from app.services.audit.log import AuditLog
from app.services.extraction.sec.xml import MAX_FILE_BYTES
from app.services.fo import precheck
from app.services.analysis_jobs import IdempotencyConflict, JobStatusUnavailable
from jinja2 import Environment, FileSystemLoader
from app.services.analysis_setup import company_registry, validate_setup, provider_configuration, SetupError

router = APIRouter(tags=["analysis workspace"])
# The reporting templates hold the FO memo section, shared by the Memo tab and the standalone FO memo.
_env = Environment(loader=FileSystemLoader([str(Path(__file__).parent / "templates"),
                                            str(Path(__file__).parents[1] / "services" / "reporting" / "templates")]),
                   autoescape=True)


def _setup_page(*, values, check="", extra_errors=(), notice=None, reports=None, edgar=None, status_code=None):
    sections, validation_mode, company = values["sections"], values["validation_mode"], values["company"]
    companies, selection, errors = [], None, list(extra_errors)
    try:
        companies = company_registry()
        values["company"] = company = company or companies[0]["id"]
        selection = validate_setup(**values)
    except SetupError as exc:
        errors.append(str(exc))
    providers = provider_configuration(sections if sections in {"bo", "both", "fo"} else "both")
    if not providers["bo_configured"]:
        errors.append("Business Overview provider settings are unavailable. Configure the AI provider before starting an analysis.")
    if sections in {"both", "fo"} and not providers["fo_configured"]:
        errors.append("Financial Overview provider settings are unavailable. Configure them before starting a combined analysis.")
    invalid_choice = company not in {c["id"] for c in companies} or sections not in {"bo", "both", "fo"} or validation_mode not in {"standard", "exploratory"}
    if status_code is None:
        status_code = 400 if invalid_choice or (check and errors) else 200
    return HTMLResponse(_env.get_template("analysis_setup.html.j2").render(
        values=values, companies=companies, selection=selection, errors=errors,
        providers=providers, checked=bool(check), execution_enabled=selection is not None and not errors,
        submission_key=uuid.uuid4().hex, notice=notice, reports=reports, edgar=edgar or {},
        sec_env=bool(get_settings().sec_user_agent)), status_code=status_code)


@router.get("/analysis/new", response_class=HTMLResponse)
def new_analysis(company: str = "", sections: str = "both", validation_mode: str = "standard",
                 cutoff: str = "", case_id: str = "", check: str = "", added: str = ""):
    values = dict(company=company, sections=sections, validation_mode=validation_mode,
                  cutoff=cutoff, case_id=case_id)
    return _setup_page(values=values, check=check,
                       notice=f"Added {added} to edgar_filings/ with its bundle.json. It is selected below." if added else None)


def _added_company_id(folder_name):
    return re.sub(r"[^a-z0-9]+", "-", folder_name.lower()).strip("-")


def _file_request(request):
    if request.headers.get('X-Requested-With') != 'setup-files':
        raise HTTPException(403, 'Use the file controls on New Analysis.')


@router.post('/analysis/new/download-files')
def download_setup_files(request: Request, user_agent: str = Form(''), session: Session = Depends(get_session)):
    from app.services.setup_files import download_files, ContactRequired
    _file_request(request)
    def client():
        if not _contact(user_agent):
            raise ContactRequired('Enter a contact email to download from SEC EDGAR.')
        return _edgar_client(session, user_agent)
    try:
        return download_files(client)
    except ContactRequired as exc:
        return Response(json.dumps({'needs_contact': True, 'detail': str(exc)}),
                        status_code=422, media_type='application/json')
    except (SetupError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/analysis/new/corporate-structure')
async def upload_corporate_structure(request: Request, company: str = Form(...), file: UploadFile = File(...)):
    from app.services.setup_files import save_structure, MAX_STRUCTURE_BYTES
    _file_request(request)
    try:
        if not (file.filename or '').lower().endswith('.json'):
            raise ValueError('Choose a corporate structure .json file.')
        return save_structure(company, await file.read(MAX_STRUCTURE_BYTES + 1))
    except (ValueError, OSError, SetupError) as exc:
        raise HTTPException(400, str(exc)) from exc


def _contact(user_agent):
    """The SEC contact typed into the form, else SEC_USER_AGENT from .env."""
    return user_agent.strip() or get_settings().sec_user_agent or ""


def _edgar_client(session, user_agent):
    return SecEdgarClient(_contact(user_agent), audit=AuditLog(session))


_NO_SEC_CONTACT = "Enter your email (e.g. you@example.com) so SEC EDGAR can identify the request."


def _edgar_failure(message, edgar, status_code=400, reports=None):
    values = dict(company="", sections="both", validation_mode="standard", cutoff="", case_id="")
    return _setup_page(values=values, extra_errors=[message], edgar=edgar, status_code=status_code)


@router.get("/analysis/new/reports", response_class=HTMLResponse)
def list_edgar_reports(ticker: str = "", amendments: str = "", user_agent: str = "", session: Session = Depends(get_session)):
    """Step 1 of a download: the ticker's 10-Ks on SEC EDGAR, newest first."""
    edgar = {"ticker": ticker, "amendments": amendments, "user_agent": user_agent}
    if not _contact(user_agent):
        return _edgar_failure(_NO_SEC_CONTACT, edgar)
    try:
        company, reports = shared_filing.annual_reports(
            _edgar_client(session, user_agent), ticker.strip(), include_amendments=bool(amendments))
    except (EdgarError, ValueError) as exc:
        return _edgar_failure(f"Could not list {ticker.strip().upper()}'s 10-Ks: {exc}", edgar)
    if not reports:
        return _edgar_failure(f"SEC EDGAR lists no 10-K for {company['name']} ({company['ticker']}).", edgar, 404)
    values = dict(company="", sections="both", validation_mode="standard", cutoff="", case_id="")
    return _setup_page(values=values, reports=reports, edgar={**edgar, "company": company})


@router.post("/analysis/new/fetch")
def fetch_edgar_filing(ticker: str = Form(...), accession: str = Form(...), with_proxy: str = Form(""),
                       user_agent: str = Form(""), session: Session = Depends(get_session)):
    """Step 2: download the chosen 10-K into edgar_filings/ with its bundle.json and company.json."""
    if not _contact(user_agent):
        return _edgar_failure(_NO_SEC_CONTACT, {"ticker": ticker, "user_agent": user_agent})
    try:
        filing = shared_filing.fetch_filing(
            _edgar_client(session, user_agent), ticker.strip(), accession=accession.strip(), with_proxy=bool(with_proxy))
    except (shared_filing.SharedFilingError, EdgarError, ValueError) as exc:
        return _edgar_failure(f"Download failed: {exc}", {"ticker": ticker, "user_agent": user_agent})
    return RedirectResponse(f"/analysis/new?company={quote(_added_company_id(filing.name))}&added={quote(filing.name)}",
                            status_code=303)


@router.post("/analysis/new/import")
async def import_edgar_filing(files: list[UploadFile] = File(...), accession: str = Form(""),
                              filing_date: str = Form(""), ticker: str = Form(""), user_agent: str = Form(""),
                              session: Session = Depends(get_session)):
    """Upload a 10-K's files (or a .zip) into edgar_filings/."""
    edgar = {"accession": accession, "filing_date": filing_date, "import_ticker": ticker, "user_agent": user_agent}
    uploads: dict[str, bytes] = {}
    for upload in files:
        name = Path(upload.filename or "").name
        if not name:
            continue
        data = await upload.read(MAX_FILE_BYTES * 4 + 1)  # a .zip may hold several files
        if name in uploads:
            return _edgar_failure(f"{name!r} was selected twice.", edgar)
        uploads[name] = data
    try:
        parsed_date = date.fromisoformat(filing_date) if filing_date.strip() else None
        client = _edgar_client(session, user_agent) if _contact(user_agent) else None
        filing = shared_filing.import_filing(
            uploads, accession=accession.strip() or None, filing_date=parsed_date,
            ticker=ticker.strip() or None, client=client)
    except (shared_filing.SharedFilingError, EdgarError, ValueError) as exc:
        return _edgar_failure(f"Import failed: {exc}", edgar)
    return RedirectResponse(f"/analysis/new?company={quote(_added_company_id(filing.name))}&added={quote(filing.name)}",
                            status_code=303)


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
    bo = bo_fo.bo_live_backend() if sections != 'fo' else None
    m3 = bo_fo.m3_live_backend() if sections != 'fo' else None
    fo = precheck.live_backend() if sections in {'both', 'fo'} else None
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
def start_analysis(company: str = Form(''), sections: str = Form('both'),
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
        from app.services.analysis_preflight import check_database
        check_database(database)  # before provider setup or any generation
        bo_backend, m3_backend, fo_backend = execution_backends(sections)
        metadata = dict(company_id=selection.company['id'], company=selection.company['label'],
                        reporting_period=selection.evidence['report_date'].isoformat(),
                        evidence_package=selection.evidence['folder'], validation_mode=validation_mode,
                        scope=sections, submitted_configuration=parameters,
                        approval_policy=selection.approval_policy)
        if sections != 'fo':
            metadata['business_overview_workflow'] = {'bo_roster': bo_fo.BO_ROSTER,
                'business_orchestrator_contract': bo_fo.BROWSER_BO_CONTRACT,
                'editorial_selection_policy': bo_fo.BROWSER_SELECTION_POLICY}
        fingerprint = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        job_id = bo_fo.jobs.start(
            database=database, folder=parameters['folder'], case_id=settled['case_id'],
            cutoff=selection.cutoff, bo_backend=bo_backend, m3_backend=m3_backend, fo_backend=fo_backend,
            fo_mode='live', output_root=settings.output_dir, data_root=settings.data_dir,
            bo_only=sections == 'bo', fo_only=sections == 'fo', bo_validators=parameters['bo_validators'] == 'on',
            business_orchestrator_contract=bo_fo.BROWSER_BO_CONTRACT if sections != 'fo' else None,
            metadata=metadata, idempotency_key=submission_key, request_hash=fingerprint)
    except IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except JobStatusUnavailable:
        raise
    except Exception as exc:
        raise HTTPException(400, f'The analysis cannot start: {exc}') from exc
    return RedirectResponse(f'/analysis/{job_id}/execution', status_code=303)


@router.get('/analysis/{job_id}/execution', response_class=HTMLResponse)
def execution(job_id: str, session: Session = Depends(get_session)):
    job = bo_fo.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, 'Unknown analysis.')
    return HTMLResponse(_env.get_template('analysis_execution.html.j2').render(job=job, analysis=analysis_workspace.analysis_tabs(job, 'execution', session)),
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
    return HTMLResponse(_render_review(session, job, view), headers={'Cache-Control':'no-store'})


def _render_review(session, job, view, *, pdf=False):
    """The Memo tab's HTML; ``pdf`` drops the site navigation and adds page rules for printing."""
    from app.services.analysis_audit import public_record
    display = {**view, **{key:public_record(view[key]) for key in ('memo','synthesis','financial','sources','reason')}}
    credit = _credit_view(session, job)  # _selected_workspace has verified the run references
    return _env.get_template('analysis_review.html.j2').render(
        job=job, view=display, rms=credit['rms'] if credit else None, pdf=pdf,
        analysis=analysis_workspace.analysis_tabs(job, 'memo', session))


@router.get('/analysis/{job_id}/memo.pdf')
def review_pdf(job_id: str, session: Session = Depends(get_session)):
    """The completed memo as a downloadable PDF, rendered from the Memo tab's template."""
    from app.api.workbench import _with_pdf_font
    from app.services.reporting.memo import PdfBackendUnavailableError, _render_pdf_with, detect_pdf_backend
    job, view = _selected_workspace(session, job_id)
    if job.get('execution_status') != 'completed':
        raise HTTPException(409, 'The PDF is available once the analysis has completed.')
    backend = detect_pdf_backend()
    if backend is None:
        raise HTTPException(501, 'No PDF backend is installed; run `pip install xhtml2pdf` and restart.')
    html = _render_review(session, job, view, pdf=True)
    if backend == 'xhtml2pdf':  # the other backends resolve the page's own fonts
        html = _with_pdf_font(html)
    try:
        pdf = _render_pdf_with(backend, html)
    except PdfBackendUnavailableError as exc:
        raise HTTPException(501, str(exc)) from exc
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', f"{job.get('case_id') or 'analysis'}_{job_id}")
    return Response(content=pdf, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="{name}_credit_memo.pdf"', 'Cache-Control': 'no-store'})


@router.get('/analysis/{job_id}/rms', response_class=HTMLResponse)
def rms_analysis(job_id: str, notice: str | None = None, session: Session = Depends(get_session)):
    return rms_page(session, job_id, notice=notice)


def _credit_view(session, job):
    """The credit view (BO, FO and RMS) of exactly this analysis's two runs, never the case's latest of either;
    None when the analysis hasn't both."""
    from app.services.rms.case_view import credit_view
    ids = analysis_workspace.run_references(job)
    if job.get('bo_only') or job.get('fo_only') or not (ids['bo'] and ids['fo']):
        return None
    view = credit_view(session, job.get('case_id'), output_root=get_settings().output_dir,
                       fo_run_id=ids['fo'], bo_run_id=ids['bo'])
    return view if view['fo'] and view['bo'] else None


def rms_page(session, job_id, *, notice=None, error=None, status_code=200):
    job = bo_fo.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, 'Unknown analysis.')
    try:
        view = _credit_view(session, job)
    except analysis_workspace.WorkspaceRecordError as exc:
        raise HTTPException(409, 'The selected run could not be verified. Its records require attention.') from exc
    if view is None:
        raise HTTPException(404, "The credit view needs this analysis's Business and Financial Overview runs.")
    return HTMLResponse(_env.get_template('credit_case.html.j2').render(
        job=job, view=view, notice=notice, error=error, analysis=analysis_workspace.analysis_tabs(job, 'rms', session)),
        status_code=status_code, headers={'Cache-Control':'no-store'})


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
        job=job, view=display, audit=audit, anchor=analysis_workspace.anchor,
        analysis=analysis_workspace.analysis_tabs(job, 'audit', session)),
        headers={'Cache-Control':'no-store'})
