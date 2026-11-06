"""Run the Business Overview and the Financial Overview concurrently over one shared filing folder.

Both sections read the same folder in ``edgar_filings/`` (see
:mod:`app.services.acquisition.shared_filing`): the BO its ``bundle.json``, the FO its files. Each
runs in its own thread with its own database session and backend, under the same case id, so
one case shows both. A failure in one section is reported and never stops the other.

SQLite allows one writer at a time, and both sections keep a write transaction open for as long
as they run (the BO from its first stage, the FO from its first logged model call). So the
two never share a database while running:

* the BO writes to the main database, as ``run-bo-case`` does;
* the FO writes to its own staging database (seeded with the main database's prompt versions so
  its prompt registry behaves as it would there), and when it finishes its rows are copied into
  the main database in one transaction that waits for the BO's write lock.

If that copy cannot be made, the staging database is kept and its path reported; nothing is lost.

With ``bo_only`` the FO is not run at all (its entry is ``skipped``), so the BO can be run by itself.

A run can be stopped (``stop``, set from the browser by :meth:`Jobs.stop`): each section checks it before every
step and ends ``stopped``, recording nothing, and RMS is skipped. A model call already in flight can't be
interrupted, so the stop takes effect when it returns. A section that already finished keeps its result.

Risk Mitigation & Structuring (:mod:`app.services.rms`) runs once both threads have finished, and only when
both sections completed: it reads the BO's ``handoff.json`` and the FO's ``financial_overview.json`` and writes
``<output>/rms/<case>/<run>/rms.json``. With a loan request it gives a verdict; without one, a debt capacity
report. It is deterministic (no model) and writes nothing to the database.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from app.models.base import Base, create_engine_and_session, init_db
from app.prompts.source_selection import (
    OUTPUT_VERSION as BROWSER_BO_CONTRACT,
    POLICY_VERSION as BROWSER_SELECTION_POLICY,
)
from app.services import rms
from app.services.rms import runner as rms_runner
from app.services.acquisition import shared_filing
from app.services.fo import loader as fo_loader
from app.services.fo.runner import FinancialOverviewRunner, default_case_id, validate_case_id
from app.services.llm import usage
from app.services.pipeline.sec import sec_source_package

# How long a section waits for the other's write lock. The BO holds its lock for its whole run.
LOCK_WAIT_SECONDS = 3 * 60 * 60
# Reference rows the FO staging database starts with; only rows the FO run added are copied back.
SEEDED_TABLES = ("prompt_versions",)
# Every BO run uses the four-module v3 roster with the Module 4 debt specialist; there is no choice.
BO_ROSTER = "v3"


class BoFoError(ValueError):
    """The combined run cannot start (no shared folder, no backend, a bad case id)."""


def bo_live_backend(model: str | None = None):
    """The configured live provider for the BO (LLM_PROVIDER), as ``run-bo-case --live`` uses it. ``model``
    (Vertex only) runs every BO tier (narrow, orchestrator, challenge) on that model for this run, so a combined
    run uses the model picked for the FO's Pre-check Agent in both sections."""
    return _live_backend_for(_live_settings(model))


def m3_live_backend(model: str | None = None):
    """The live backend for Module 3's management specialist and its Validator 7 reviewer: the same provider and
    model as the BO, with the rebuild's response-schema adaptation on Vertex."""
    from app.services.bo.m3_rebuild.contracts import provider_schema

    return _live_backend_for(_live_settings(model), schema_transform=provider_schema)


def _live_settings(model: str | None):
    from app.core.config import get_settings

    settings = get_settings()
    if model:
        from app.services.fo.models import check_model

        model = check_model(model)
        if settings.llm_provider != "vertex":
            raise ValueError("A model can only be picked for the Vertex provider (LLM_PROVIDER=vertex).")
        settings = settings.model_copy(update={
            "vertex_model_narrow": model, "vertex_model_orchestrator": model, "vertex_model_challenge": model})
    return settings


def _live_backend_for(settings, *, schema_transform=None):
    if settings.llm_provider == "vertex":
        from app.services.llm.providers_vertex import VertexProviderBackend

        backend = VertexProviderBackend(settings, schema_transform=schema_transform)
    else:
        from app.services.llm.providers import RealProviderBackend

        backend = RealProviderBackend(settings)
    backend.check_configuration()
    return backend


def m3_package(package, folder: str, bundle):
    """The filing folder's inputs for Module 3: its 10-K (the bundle's primary Inline XBRL document) for the
    management assessment and, when present, its corporate-structure JSON (``shared_filing.m3_structure_path``).

    The JSON is dated to the filing's own availability, so the evidence cut-off admits both together."""
    from app.services.pipeline.package import Module3Input, SourceInput

    sources, corporate = list(package.sources), None
    path = shared_filing.m3_structure_path(folder)
    if path is not None:
        primary = next(f for f in bundle.files if f.filename == bundle.primary_document)
        sources.append(SourceInput(
            filename=path.name, path=str(path), parser="structured_json",
            tags=["m3", "corporate_structure"], available_at=primary.available_at,
            entity_id=package.borrower_entity_id, scope="consolidated", accounting_basis="not_applicable"))
        corporate = path.name
    fields = {name: getattr(package, name) for name in type(package).model_fields}
    return type(package)(**{**fields, "sources": sources, "module3": Module3Input(
        corporate_source=corporate, management_source=bundle.primary_document)})


def sqlite_path(database_url: str) -> Path:
    """The file behind a ``sqlite:///`` URL; a combined run needs a file both threads can open."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or ":memory:" in database_url or database_url == prefix:
        raise BoFoError("A combined BO + FO run needs a file-based SQLite database (DATABASE_URL=sqlite:///...).")
    return Path(database_url[len(prefix):]).resolve()


def plan(folder: str, case_id: str | None = None, cutoff: datetime | None = None) -> dict:
    """Check the folder can be read by both sections and settle the case id and evidence cut-off."""
    bundle = shared_filing.load_bundle(folder)
    if case_id:
        validate_case_id(case_id)
    else:
        case_id = default_case_id(fo_loader.load(folder)[0]["meta"], folder)
    if cutoff is not None and cutoff.tzinfo is None:
        raise BoFoError("The evidence cut-off needs a timezone, e.g. 2026-03-31T00:00:00Z.")
    # By default every file in the folder is admitted: the cut-off is the latest availability.
    cutoff = cutoff or max(f.available_at for f in bundle.files)
    return {"folder": folder, "case_id": case_id, "cutoff": cutoff, "bundle": bundle}


def run_bo_fo(*, database: Path, folder: str, bo_backend, fo_backend, fo_mode: str,
              output_root, data_root=None, case_id: str | None = None, cutoff: datetime | None = None,
              produce_pdf: bool = False, m3_backend=None,
              rms_request: rms.RmsRequest | None = None, on_progress=None, on_work=None,
              lock_wait: float = LOCK_WAIT_SECONDS, bo_only: bool = False, fo_only: bool = False,
              stop: threading.Event | None = None, bo_validators: bool = True, on_stage=None,
              business_orchestrator_contract: str | None = None) -> dict:
    """Run both sections at once; returns ``{"case_id", "folder", "cutoff", "bo": {...}, "fo": {...},
    "rms": {...}}``.

    Each section's entry has ``status`` ``completed`` or ``failed`` and either its ``summary`` or its
    ``error``. The BO's Module 3 management specialist and reviewer use ``m3_backend``. ``rms`` is ``completed`` (a verdict, or a debt capacity report without ``rms_request``), ``failed`` or ``skipped`` (a section didn't complete),
    with its ``summary``, ``error`` or ``reason``. ``on_progress(section, message)`` is called from the worker
    threads as they advance, and for ``rms`` once both have finished; ``on_work(section, done, total)`` with the
    units of work each section has done and plans (``total`` can grow while a section runs). ``bo_only`` runs the BO by itself: the FO
    (and so RMS) is ``skipped`` and ``fo_backend`` is not used. ``fo_only`` runs the FO by itself: the BO (and so RMS) is ``skipped`` and ``bo_backend`` is not used. Setting ``stop`` ends each unfinished section
    ``stopped`` at its next step. ``bo_validators=False`` runs the BO validators in advisory mode (an ungoverned
    draft, always left for human review; RMS notes it).
    """
    database = Path(database).resolve()
    data_root = Path(data_root) if data_root is not None else database.parent
    settled = plan(folder, case_id, cutoff)
    from app.services.analysis_preflight import check_database
    check_database(database)
    if business_orchestrator_contract not in {None, BROWSER_BO_CONTRACT, 'bo-competitive-positioning-output-1.0.0'}:
        raise BoFoError('Unsupported Business Overview orchestrator contract.')
    if not fo_only and not any(f.role == 'schema' for f in settled['bundle'].files):
        raise BoFoError('The selected Business Overview source bundle has no required schema file.')
    primary = next(f for f in settled['bundle'].files if f.filename == settled['bundle'].primary_document)
    if settled['cutoff'] < primary.available_at:
        raise BoFoError('The evidence cutoff excludes the selected annual report.')
    case_id = settled["case_id"]
    say = on_progress or (lambda section, message: None)
    tally = on_work or (lambda section, done, total: None)

    stage = on_stage or (lambda section, name, status, detail=None: None)

    def checker(section):
        def check(step):
            if stop is not None and stop.is_set():
                raise RunStopped(f"Stopped by the analyst before {step}; nothing was recorded.")
            say(section, step)
        return check

    def bo():
        from app.services.bo.runner import BusinessOverviewRunner

        identity = shared_filing.company_info(folder)
        package = sec_source_package(
            settled["bundle"], cutoff=settled["cutoff"],
            entity_id=identity.get("ticker") or None, legal_name=identity.get("name") or None)
        package = m3_package(package, folder, settled["bundle"])
        engine, factory = create_engine_and_session(
            f"sqlite:///{database.as_posix()}", sqlite_timeout=lock_wait)
        try:
            with factory() as session:
                result = BusinessOverviewRunner(
                    session, backend=bo_backend, data_root=data_root, output_root=output_root,
                    bo_roster=BO_ROSTER, enable_m4_debt_specialist=True,
                    business_orchestrator_contract=business_orchestrator_contract,
                    m3_backend=m3_backend, m3_reviewer_backend=m3_backend,
                    check_stop=checker("bo"), on_work=lambda d, t: tally("bo", d, t),
                    enforce_validators=bo_validators,
                    on_stage=lambda name, status, detail=None: stage("bo", name, status, detail),
                ).run_case(case_id, package=package, produce_pdf=produce_pdf)
                say("bo", "recording the Business Overview")
                session.commit()
                # Informational output is generated only AFTER the analytical run
                # and handoff are frozen. It is never passed to FO, RMS or BO agents.
                if stop is not None and stop.is_set():
                    return bo_summary(result, validators=bo_validators)
                say("bo", "describing the business model")
                stage("bo", "business_model", "running")
                try:
                    from app.services.bo.business_model import run_description
                    with session.begin_nested():
                        description = run_description(session, result.analysis_run_id, bo_backend)
                    session.commit()
                    informational_status = description['status']
                except Exception:
                    session.rollback()
                    informational_status = 'unavailable'
                    say("bo", "Business Model unavailable; saved credit analysis is unchanged")
                stage("bo", "business_model", "completed", {"informational_status": informational_status})
        finally:
            engine.dispose()
        return bo_summary(result, validators=bo_validators)

    def fo():
        staging = data_root / "staging" / f"fo-{uuid.uuid4().hex[:16]}.db"
        staging.parent.mkdir(parents=True, exist_ok=True)
        engine, factory = create_engine_and_session(f"sqlite:///{staging.as_posix()}")
        try:
            init_db(engine)
            _seed(staging, database, lock_wait)
            with factory() as session:
                stage("fo", "workflow", "running")
                result = FinancialOverviewRunner(
                    session, output_root=output_root, agent_backend=fo_backend, agent_mode=fo_mode,
                    check_stop=checker("fo"), on_work=lambda d, t: tally("fo", d, t),
                    on_stage=lambda name, status, detail=None: stage("fo", name, status, detail),
                ).run_filing(folder, case_id)
                session.commit()
        except BaseException:
            engine.dispose()
            staging.unlink(missing_ok=True)  # nothing was recorded; the staging copy holds nothing of value
            raise
        engine.dispose()
        say("fo", "copying the Financial Overview into the main database (waits for the BO to finish writing)")
        try:
            merge(staging, database, lock_wait)
        except Exception as exc:
            raise StagingKept(f"{exc} The Financial Overview run is kept in {staging}.", staging) from exc
        staging.unlink(missing_ok=True)
        stage("fo", "reporting", "completed")
        return result.summary()

    outcome = {"case_id": case_id, "folder": folder, "cutoff": settled["cutoff"].isoformat()}
    if bo_only:
        outcome["fo"] = {"status": "skipped", "reason": "Business Overview only run."}
    if fo_only:
        outcome["bo"] = {"status": "skipped", "reason": "Financial Overview only run."}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="bo-fo") as pool:
        futures = {}
        if not fo_only:
            futures[pool.submit(bo)] = "bo"
        if not bo_only:
            futures[pool.submit(fo)] = "fo"
        for future in as_completed(futures):
            section = futures[future]
            try:
                outcome[section] = {"status": "completed", "summary": future.result()}
                if on_stage:
                    on_stage(section, "recorded_output", "completed", outcome[section]["summary"])
                say(section, "completed")
            except RunStopped as exc:
                outcome[section] = {"status": "stopped", "reason": str(exc)}
                say(section, "stopped")
            except Exception as exc:  # one section's failure is reported, never raised over the other's result
                outcome[section] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                                    "traceback": traceback.format_exc(limit=8)}
                if isinstance(exc, StagingKept):
                    outcome[section]["staging_database"] = str(exc.staging)
                say(section, "failed")
    if stop is not None and stop.is_set():
        outcome["rms"] = {"status": "skipped", "reason": "The run was stopped."}
        if not bo_only and not fo_only:
            say("rms", "skipped")
    else:
        outcome["rms"] = run_rms(outcome, rms_request, output_root, say)
    return outcome


def run_rms(outcome: dict, request: rms.RmsRequest | None, output_root, say) -> dict:
    """Risk Mitigation & Structuring over the two sections' recorded outputs, once both have completed. Without a
    request (or a requested amount) it is a debt capacity report."""
    request = request or rms.RmsRequest()
    if outcome["fo"]["status"] == "skipped":
        say("rms", "skipped")
        return {"status": "skipped", "reason": "Needs both sections; this run was Business Overview only."}
    if outcome["bo"]["status"] == "skipped":
        say("rms", "skipped")
        return {"status": "skipped", "reason": "Needs both sections; this run was Financial Overview only."}
    unfinished = [s.upper() for s in ("bo", "fo") if outcome[s]["status"] != "completed"]
    if unfinished:
        say("rms", "skipped")
        return {"status": "skipped",
                "reason": f"Needs both sections completed; the {' and '.join(unfinished)} did not complete."}
    try:
        say("rms", "assessing the loan request" if request.requested_amount_m is not None
            else "sizing the debt capacity (no requested amount)")
        fo_path = Path(outcome["fo"]["summary"]["outputs"]["financial_overview.json"])
        handoff_path = outcome["bo"]["summary"].get("handoff_path")
        handoff = json.loads(Path(handoff_path).read_text(encoding="utf-8")) if handoff_path else None
        run_id = rms_runner.new_run_id()
        result = rms.assess(request, json.loads(fo_path.read_text(encoding="utf-8")), handoff=handoff,
                            analysis_run_id=run_id)
        record, path = rms_runner.write_record(
            result, run_id=run_id, case_id=outcome["case_id"], output_root=output_root,
            sources={"bo_analysis_run_id": outcome["bo"]["summary"]["analysis_run_id"],
                     "bo_handoff_id": (handoff or {}).get("handoff_id"),
                     "bo_review_status": (handoff or {}).get("human_review_status"),
                     "bo_validators_enforced": (handoff or {}).get("validators_enforced", True),
                     "fo_run_id": outcome["fo"]["summary"]["run_id"],
                     "fo_content_hash": outcome["fo"]["summary"]["content_hash"],
                     "fo_decisions": {"review": None, "overrides": []},  # a new run has no decisions yet
                     "bo_handoff": handoff_path, "fo_overview": str(fo_path)})
    except Exception as exc:  # reported like a section's failure; the BO and FO results stand
        say("rms", "failed")
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=8)}
    say("rms", "completed")
    return {"status": "completed", "summary": rms_runner.rms_summary(record, path)}


class RunStopped(RuntimeError):
    """The analyst stopped the run; the section recorded nothing."""


class StagingKept(RuntimeError):
    def __init__(self, message, staging):
        super().__init__(message)
        self.staging = staging


def bo_summary(result, *, validators: bool = True) -> dict:
    return {
        "case_id": result.case_id,
        "analysis_run_id": result.analysis_run_id,
        "scope": "business_overview_only",
        "execution_mode": result.execution_mode,
        "bo_roster": BO_ROSTER,
        "validators_enforced": validators,
        "conclusion_status": result.conclusion_status,
        "human_review_status": "pending",
        "has_synthesis": bool((result.handoff or {}).get("business_topic_conclusion_id")),
        "business_orchestrator_contract": ((result.handoff or {}).get('canonical_references') or {}).get('business_orchestrator_contract'),
        "editorial_selection_policy": ({BROWSER_BO_CONTRACT: BROWSER_SELECTION_POLICY,
            'bo-competitive-positioning-output-1.0.0': 'bo-editorial-selection-1.0.0'}.get(
            ((result.handoff or {}).get('canonical_references') or {}).get('business_orchestrator_contract'))),
        "evidence_snapshot_version": result.snapshot_version,
        "four_section_memo": ((result.handoff or {}).get('canonical_references') or {}).get('four_section_memo'),
        "handoff_id": (result.handoff or {}).get("handoff_id"),
        "outputs": sorted({str(Path(p).parent) for p in result.output_paths.values()}),
        "handoff_path": str(result.output_paths["handoff.json"]) if "handoff.json" in result.output_paths else None,
    }


# --- the FO staging database ------------------------------------------------------------------------


def _connect(database: Path, lock_wait: float) -> sqlite3.Connection:
    # Autocommit mode, so BEGIN IMMEDIATE below is the only transaction: it takes the write lock up front
    # (waiting for the BO's) instead of upgrading a read lock, which SQLite can refuse without waiting.
    return sqlite3.connect(str(database), timeout=lock_wait, isolation_level=None)


def _columns(con, schema: str, table: str) -> list[str]:
    return [row[1] for row in con.execute(f'PRAGMA {schema}.table_info("{table}")')]


def _seed(staging: Path, database: Path, lock_wait: float) -> None:
    con = _connect(staging, lock_wait)
    try:
        con.execute("ATTACH DATABASE ? AS main_db", (str(database),))
        for table in SEEDED_TABLES:
            cols = [c for c in _columns(con, "main", table) if c in set(_columns(con, "main_db", table))]
            if cols:
                names = ", ".join(f'"{c}"' for c in cols)
                con.execute(f'INSERT INTO main."{table}" ({names}) SELECT {names} FROM main_db."{table}"')
        con.execute("DETACH DATABASE main_db")
    finally:
        con.close()


def merge(staging: Path, database: Path, lock_wait: float = LOCK_WAIT_SECONDS) -> dict[str, int]:
    """Copy an FO staging database's rows into the main database in one transaction; returns rows per table."""
    con = _connect(database, lock_wait)
    copied: dict[str, int] = {}
    try:
        con.execute("ATTACH DATABASE ? AS staging", (str(staging),))
        con.execute("BEGIN IMMEDIATE")
        try:
            for table in (t.name for t in Base.metadata.sorted_tables):
                if not con.execute(f'SELECT 1 FROM staging."{table}" LIMIT 1').fetchone():
                    continue
                main_cols = set(_columns(con, "main", table))
                cols = _columns(con, "staging", table)
                missing = [c for c in cols if c not in main_cols]
                if missing:
                    raise RuntimeError(
                        f"The main database's {table} table lacks {missing}; run python -m app.migrate first.")
                if table in SEEDED_TABLES:
                    copied[table] = _merge_prompt_versions(con, cols)
                    continue
                names = ", ".join(f'"{c}"' for c in cols)
                cursor = con.execute(f'INSERT INTO main."{table}" ({names}) SELECT {names} FROM staging."{table}"')
                copied[table] = cursor.rowcount
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        con.execute("DETACH DATABASE staging")
    finally:
        con.close()
    return copied


def _merge_prompt_versions(con, cols) -> int:
    """New prompt versions the FO registered; a version already in the main database must be the same prompt."""
    clash = con.execute(
        'SELECT s.name, s.version FROM staging.prompt_versions s JOIN main.prompt_versions m '
        'ON m.name = s.name AND m.version = s.version WHERE m.content_hash != s.content_hash').fetchone()
    if clash:
        raise RuntimeError(f"Prompt {clash[0]} version {clash[1]} differs between the FO run and the main database.")
    names = ", ".join(f'"{c}"' for c in cols if c != "id")  # the main database allocates its own ids
    cursor = con.execute(
        f'INSERT INTO main.prompt_versions ({names}) SELECT {names} FROM staging.prompt_versions s '
        'WHERE NOT EXISTS (SELECT 1 FROM main.prompt_versions m WHERE m.name = s.name AND m.version = s.version)')
    return cursor.rowcount


# --- background jobs for the browser -------------------------------------------------------------------


class Jobs:
    """Existing server-side worker with durable progress, cancellation and submission claims."""

    def __init__(self, store_path=None):
        self._lock = threading.RLock()
        self._jobs, self._meters, self._stops = {}, {}, {}
        self._persistent = set()
        self._job_stores = {}
        self._store_path = store_path

    def _store(self, database=None):
        from app.services.analysis_jobs import JobStore, store_path
        if self._store_path:
            return JobStore(self._store_path)
        if database is None:
            from app.core.config import get_settings
            database = sqlite_path(get_settings().database_url)
        return JobStore(store_path(database))

    def start(self, *, metadata=None, idempotency_key=None, request_hash=None, **kwargs) -> str:
        from app.services.analysis_jobs import (StoredStop, now, register_worker, forget_worker,
            publish_terminal, finish_record, persistence_health, JobStorageUnavailable, storage_failure)
        store = self._store(kwargs['database']) if kwargs.get('database') or self._store_path else None
        job_id = uuid.uuid4().hex
        bo_only, fo_only = kwargs.get('bo_only', False), kwargs.get('fo_only', False)
        job = dict(job_id=job_id, status='running', execution_status='pending', created_at=now(),
                   started_at=None, finished_at=None, folder=kwargs['folder'], case_id=kwargs.get('case_id'),
                   bo_only=bo_only, fo_only=fo_only, bo_validators=kwargs.get('bo_validators', True), stop_requested=False,
                   result=None, error=None, stages={}, events=[], memo_status='draft', worker_tracking='thread-v1',
                   metadata=metadata or {}, cutoff=kwargs.get('cutoff').isoformat() if kwargs.get('cutoff') else None)
        selective = kwargs.get('business_orchestrator_contract') == BROWSER_BO_CONTRACT
        writer_label = ('Competitive Positioning selection & validation' if selective else
                        'Competitive Positioning writing & validation' if kwargs.get('business_orchestrator_contract') else
                        'Cross-module synthesis & validation')
        if selective and not fo_only:
            job['business_overview_workflow'] = {'bo_roster': BO_ROSTER,
                'business_orchestrator_contract': BROWSER_BO_CONTRACT, 'editorial_selection_policy': BROWSER_SELECTION_POLICY}
        skipped = lambda section: bo_only and section != 'bo' or fo_only and section != 'fo'
        job['sections'] = {section: dict(status='skipped' if skipped(section) else 'waiting',
                                        step='not selected' if skipped(section) else 'starting', steps=[], work=None)
                           for section in ('bo', 'fo', 'rms')}
        for name in () if fo_only else ('foundation', 'primary_specialists', 'reconciliation', 'orchestrator', *(() if selective else ('challenger',)), 'memo_preparation'):
            job['stages']['bo:' + name] = dict(section='bo', label={'primary_specialists':'Specialist analysis & validation','foundation':'Evidence preparation & management analysis','reconciliation':'Validation & reconciliation','orchestrator':writer_label,'challenger':'Independent challenge'}.get(name,name.replace('_',' ').title()), status='pending', order={'foundation':10,'primary_specialists':20,'reconciliation':50,'orchestrator':60,'challenger':70,'memo_preparation':90}[name])
        if not bo_only:
            job['stages']['fo:workflow'] = dict(section='fo', label='Financial preparation, analysis and validation', status='pending', order=0)
            job['stages']['fo:reporting'] = dict(section='fo', label='Financial reporting', status='pending', order=1000)
        # Publish thread ownership BEFORE the atomic claim becomes visible to
        # polling. This thread cannot run until all callbacks below are ready.
        thread = threading.Thread(target=lambda: work(), name=f'bo-fo-{job_id}', daemon=True)
        if store:
            register_worker(store.path, job_id, thread)
            try:
                ident, created = store.claim(job, idempotency_key, request_hash)
            except BaseException:
                forget_worker(store.path, job_id)
                raise
            if not created:
                forget_worker(store.path, job_id)
                return ident

        with self._lock:
            self._jobs[job_id] = job
            if store:
                self._persistent.add(job_id)
                self._job_stores[job_id] = str(store.path.resolve())
            self._meters[job_id] = {section: usage.meter_of(kwargs.get(key)) for section,key in
                                   (('bo','bo_backend'),('fo','fo_backend'),('m3','m3_backend'))}
            stop = self._stops[job_id] = StoredStop(store, job_id) if store else threading.Event()

        def save(*, final=False):
            self._with_cost(job)
            if store:
                try:
                    store.save(job)
                    persistence_health(store.path, job_id, failed=False)
                except (OSError, sqlite3.Error, JobStorageUnavailable) as exc:
                    persistence_health(store.path, job_id, failed=True)
                    failure = exc if isinstance(exc, JobStorageUnavailable) else storage_failure(exc)
                    job['persistence_error'] = str(failure)
                    job['persistence_error_at'] = now()
                    if final:
                        publish_terminal(store.path, job)
                        return  # One final attempt only; later reads reconcile.
                    if failure is exc:
                        raise
                    raise failure from exc

        def stage(section, name, status, detail=None):
            with self._lock:
                state = job['stages'].setdefault(section + ':' + name,
                          dict(section=section, label=name.replace('_',' ').title(), status='pending'))
                if 'order' not in state:
                    state['order'] = (100 if name == 'recorded_output' else 15 if name == 'management_analysis_and_validator7' else 45 if 'debt' in name else 60 if 'orchestrator' in name else 70 if 'challeng' in name else 35) if section == 'bo' else len(job['stages'])
                labels = {'primary_specialists':'Specialist analysis & validation', 'reconciliation':'Validation & reconciliation', 'orchestrator':writer_label, 'challenger':'Independent challenge', 'foundation':'Evidence preparation & management analysis', 'memo_preparation':'Memo preparation'}
                state['label'] = labels.get(name, state['label'])
                state.update(status=status, detail=detail, updated_at=now())
                if status == 'running':
                    state['started_at'] = now()
                else:
                    state['finished_at'] = now()
                if name == 'recorded_output' and isinstance(detail, dict):
                    job.setdefault('run_ids', {})[section] = detail.get('analysis_run_id') or detail.get('run_id')
                    job.setdefault('artifacts', {})[section] = detail.get('outputs', [])
                    if job['result'] is None:
                        job['result'] = {key: {'status':'pending', 'summary':{}} for key in ('bo','fo','rms')}
                    job['result'][section] = dict(status='completed', summary=detail)
                job['events'].append(dict(section=section, stage=name, status=status, detail=detail, at=now()))
                save()

        def progress(section, message):
            with self._lock:
                state = job['sections'][section]
                if message in ('completed', 'failed', 'skipped', 'stopped'):
                    state['status'] = message
                else:
                    state.update(status='running', step=message)
                    state['steps'].append(message)
                save()

        def tally(section, done, total):
            with self._lock:
                job['sections'][section]['work'] = dict(done=done, total=total)
                save()

        def work():
            try:
                with self._lock:
                    job.update(execution_status='running', started_at=now())
                    save()
                result = run_bo_fo(on_progress=progress, on_work=tally, on_stage=stage, stop=stop, **kwargs)
                with self._lock:
                    statuses = [value['status'] for value in result.values() if isinstance(value, dict) and 'status' in value]
                    execution = 'failed' if 'failed' in statuses else 'stopped' if 'stopped' in statuses else 'completed'
                    job.update(result=result, case_id=result['case_id'], execution_status=execution,
                               status='finished' if execution == 'completed' else execution,
                               memo_status='human_review_required' if execution == 'completed' else 'unavailable_or_incomplete')
                    for section in ('bo','fo','rms'):
                        job['sections'][section]['status'] = result[section]['status']
                        job['sections'][section]['step'] = result[section].get('reason', result[section].get('error', result[section]['status']))
                    bo_conclusion = result.get('bo', {}).get('summary', {}).get('conclusion_status')
                    if bo_conclusion in {'failed', 'rejected', 'incomplete', 'unavailable'} or result.get('bo', {}).get('summary', {}).get('has_synthesis') is False:
                        job['memo_status'] = 'unavailable_or_incomplete'
                    errors = [value.get('error') for value in result.values() if isinstance(value, dict) and value.get('error')]
                    job['error'] = '\n'.join(errors) or None
            except BaseException as exc:
                with self._lock:
                    terminal = 'failed' if isinstance(exc, Exception) else 'interrupted'
                    job.update(status=terminal, execution_status=terminal, memo_status='unavailable_or_incomplete',
                               error=f'{type(exc).__name__}: {exc}')
            finally:
                with self._lock:
                    finish_record(job)
                    if store:
                        publish_terminal(store.path, job)
                    save(final=True)
        try:
            thread.start()
        except Exception as exc:
            with self._lock:
                job.update(status='failed', execution_status='failed', error='The analysis worker could not start.',
                           memo_status='unavailable_or_incomplete', finished_at=now())
                finish_record(job)
                if store:
                    publish_terminal(store.path, job, launch_failed=True)
                save(final=True)
        return job_id

    def stop(self, job_id):
        store = self._store()
        if store.request_stop(job_id):
            with self._lock:
                if job_id in self._stops:
                    self._stops[job_id].set()
            return True
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job['execution_status'] not in {'pending','running'}:
                return False
            job['stop_requested'] = True
            self._stops[job_id].set()
            return True

    def delete(self, job_id):
        """Drop a finished analysis from the history. Its BO/FO runs and artifacts are kept for audit.
        None when unknown, False while the analysis is still pending or running."""
        deleted = self._store().delete(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job_id not in self._persistent:
                if job['execution_status'] in {'pending', 'running'}:
                    return False
                deleted = True
            if deleted:
                for registry in (self._jobs, self._meters, self._stops, self._job_stores):
                    registry.pop(job_id, None)
                self._persistent.discard(job_id)
        return deleted

    def get(self, job_id):
        store = self._store()
        saved = store.get(job_id)
        if saved is not None:
            return self._verified(saved)
        with self._lock:
            if job_id in self._persistent and self._job_stores.get(job_id) == str(store.path.resolve()):
                from app.services.analysis_jobs import JobStorageUnavailable
                raise JobStorageUnavailable('Analysis status cannot currently be verified because its job record is unavailable. No analysis has been restarted.')
            job = self._jobs.get(job_id) if job_id not in self._persistent else None
            return self._with_cost(_copy(job)) if job else None

    def recent(self):
        store = self._store()
        saved = {j['job_id']: self._verified(j) for j in store.recent()}
        with self._lock:
            local = {ident for ident in self._persistent
                     if self._job_stores.get(ident) == str(store.path.resolve())}
            if local - saved.keys():
                from app.services.analysis_jobs import JobStorageUnavailable
                raise JobStorageUnavailable('Analysis history cannot currently be verified because job records are unavailable. No analysis has been restarted.')
            for ident, job in self._jobs.items():
                if ident not in self._persistent:
                    saved.setdefault(ident, self._with_cost(_copy(job)))
        return sorted(saved.values(), key=lambda j: j['created_at'], reverse=True)

    @staticmethod
    def _verified(job):
        from app.services.analysis_jobs import JobStatusUnavailable, TERMINAL
        if job.get('worker_health') == 'unverified' and job.get('execution_status') not in TERMINAL:
            raise JobStatusUnavailable('Analysis worker status cannot currently be verified. No analysis has been restarted.')
        return job

    def _with_cost(self, job):
        meters = self._meters.get(job['job_id'], {})
        job['cost'] = {**{s: usage.summary(meters=[meters.get(s)]) for s in ('bo','fo','m3')},
                       'total': usage.summary(meters=meters.values())}
        return job


def _copy(job):
    import copy
    return copy.deepcopy(job)


jobs = Jobs()
