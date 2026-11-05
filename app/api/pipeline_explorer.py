"""Read-only Pipeline Explorer — an interactive left-to-right dataflow view over
recorded BO / FO / M3 artifacts, with a per-node inspector and JSON/PDF export.

Every route is a read-only GET. Nothing here runs a model, mutates an artifact or
generates a credit conclusion; it only indexes and re-presents recorded outputs.
Artifact access is bounded by :mod:`app.services.registry.explorer` so only files
under the configured output root are reachable.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from markupsafe import Markup

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from jinja2 import Environment, FileSystemLoader

from app.core import get_settings
from app.core.hashing import canonical_json, content_hash
from app.services.registry.explorer import (
    ArtifactAccessError,
    ArtifactConflictError,
    discover_cases,
    graph_for_case,
    inspect_node,
    load_artifact,
    load_artifact_bytes,
    manifest_for_case,
)
from app.services.registry.json_render import render_json_html, render_json_pdf

router = APIRouter(tags=["pipeline_explorer"])
_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=True,
)


def _output_dir() -> str:
    return get_settings().output_dir


@router.get("/pipeline", response_class=HTMLResponse)
def pipeline_home() -> HTMLResponse:
    """Case picker + the interactive graph shell (renders even with no runs)."""
    cases = discover_cases(_output_dir(), repo_root=".")
    return HTMLResponse(
        _env.get_template("pipeline_explorer.html.j2").render(
            cases=[{"case_id": c.case_id, "label": c.label, "kind": c.kind,
                    "note": c.note} for c in cases],
        )
    )


@router.get("/pipeline/{case_id}/graph.json")
def pipeline_graph(case_id: str, run_id: str | None = None,
                   workflow_id: str | None = None) -> JSONResponse:
    """The dataflow graph (nodes + declared-dependency edges) for a case."""
    from app.services.registry.workflow_scope import recorded_workflows, WorkflowScopeError
    if workflow_id and run_id:
        raise HTTPException(400, 'Select either a workflow or an individual run.')
    try:
        workflows = recorded_workflows(get_settings().database_url, case_id)
    except WorkflowScopeError as exc:
        raise HTTPException(409, str(exc)) from exc
    workflow = next((w for w in workflows if w['workflow_id'] == workflow_id), None)
    if workflow_id and workflow is None:
        raise HTTPException(404, 'No recorded workflow for this case and identity.')
    if workflow and not workflow['available']:
        raise HTTPException(409, workflow['error'])
    try:
        graph = graph_for_case(case_id, _output_dir(), repo_root=".", run_id=run_id,
                               workflow=workflow)
    except ArtifactAccessError as exc:
        raise HTTPException(409 if isinstance(exc, ArtifactConflictError) else 404, str(exc)) from exc
    graph['workflows'] = workflows
    return JSONResponse(graph)


@router.get("/pipeline/{case_id}/manifest.json")
def pipeline_manifest(case_id: str) -> Response:
    """The versioned artifact manifest for a case."""
    manifest = manifest_for_case(case_id, _output_dir(), repo_root=".")
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
    return Response(
        content=canonical_json(manifest.model_dump(mode="json")) + "\n",
        media_type="application/json",
    )


@router.get("/pipeline/{case_id}/node/{artifact_id}")
def pipeline_node(case_id: str, artifact_id: str, expected_hash: str | None = None, expected_source_hash: str | None = None) -> JSONResponse:
    """The node-inspector payload for one artifact (reason, not mock, if absent)."""
    try:
        info = inspect_node(case_id, artifact_id, _output_dir(), repo_root=".", expected_source_hash=expected_source_hash)
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=409 if isinstance(exc, ArtifactConflictError) else 404, detail=str(exc)) from exc
    _check_pin(info.get("canonical_content_hash"), expected_hash)
    return JSONResponse(info)


@router.get("/pipeline/{case_id}/node/{artifact_id}/view.html",
            response_class=HTMLResponse)
def pipeline_node_html(case_id: str, artifact_id: str, expected_hash: str | None = None, expected_source_hash: str | None = None) -> HTMLResponse:
    """Generic hierarchical HTML viewer for an artifact's JSON."""
    try:
        payload, _ = load_artifact(case_id, artifact_id, _output_dir(), repo_root=".", expected_source_hash=expected_source_hash)
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=409 if isinstance(exc, ArtifactConflictError) else 404, detail=str(exc)) from exc
    _check_pin(content_hash(payload), expected_hash)
    return HTMLResponse(render_json_html(payload, title=artifact_id))


def _safe_name(artifact_id: str) -> str:
    return artifact_id.replace("/", "_").replace("..", "_")


@router.get("/pipeline/{case_id}/node/{artifact_id}/original.json")
def pipeline_node_original(case_id: str, artifact_id: str, expected_hash: str | None = None, expected_source_hash: str | None = None) -> Response:
    """Download the EXACT recorded file bytes, preserving the original SHA-256.

    Byte-for-byte identical to what the producer wrote. The ``X-Original-SHA256``
    header and strong ``ETag`` are the hash of those exact bytes. Not available
    for per-agent slice artifacts (they have no independent original file).
    """
    import hashlib

    try:
        raw, original_sha256, _ = load_artifact_bytes(
            case_id, artifact_id, _output_dir(), repo_root=".", expected_source_hash=expected_source_hash)
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=409 if isinstance(exc, ArtifactConflictError) else 404, detail=str(exc)) from exc
    import json
    _check_pin(content_hash(json.loads(raw)), expected_hash)
    return Response(
        content=raw,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_name(artifact_id)}.json"',
            "X-Original-SHA256": original_sha256,
            "X-Export-Kind": "original-bytes",
            "ETag": f'"{original_sha256}"',
        },
    )


@router.get("/pipeline/{case_id}/node/{artifact_id}/normalized.json")
def pipeline_node_normalized(case_id: str, artifact_id: str, expected_hash: str | None = None, expected_source_hash: str | None = None) -> Response:
    """Export NORMALIZED (canonical) JSON with a separate canonical content hash.

    Semantically equivalent to the recorded artifact but re-serialised with
    deterministic canonical form (sorted keys). Explicitly labelled normalized;
    the ``X-Canonical-SHA256`` header is the hash of the canonical bytes, which
    may differ from the original file hash. Works for per-agent slices too.
    """
    try:
        payload, _ = load_artifact(case_id, artifact_id, _output_dir(), repo_root=".", expected_source_hash=expected_source_hash)
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=409 if isinstance(exc, ArtifactConflictError) else 404, detail=str(exc)) from exc
    _check_pin(content_hash(payload), expected_hash)
    body = canonical_json(payload) + "\n"
    canonical_sha256 = content_hash(payload)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition":
                f'attachment; filename="{_safe_name(artifact_id)}.normalized.json"',
            "X-Canonical-SHA256": canonical_sha256,
            "X-Export-Kind": "normalized-canonical",
        },
    )


@router.get("/pipeline/{case_id}/node/{artifact_id}/download.json")
def pipeline_node_json(case_id: str, artifact_id: str, expected_hash: str | None = None, expected_source_hash: str | None = None) -> Response:
    """Backwards-compatible download.

    Returns the EXACT original bytes when the artifact is a whole file; for
    per-agent slice artifacts (no independent original file) it returns the
    normalized canonical slice, labelled as such. Integrity headers always
    describe exactly what is returned.
    """
    try:
        raw, original_sha256, _ = load_artifact_bytes(
            case_id, artifact_id, _output_dir(), repo_root=".", expected_source_hash=expected_source_hash)
        import json
        _check_pin(content_hash(json.loads(raw)), expected_hash)
        return Response(
            content=raw,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{_safe_name(artifact_id)}.json"',
                "X-Original-SHA256": original_sha256,
                "X-Export-Kind": "original-bytes",
                "ETag": f'"{original_sha256}"',
            },
        )
    except ArtifactConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ArtifactAccessError:
        # Slice artifact (or no original file): fall back to normalized export.
        try:
            payload, _ = load_artifact(case_id, artifact_id, _output_dir(), repo_root=".", expected_source_hash=expected_source_hash)
        except ArtifactAccessError as exc:
            raise HTTPException(status_code=409 if isinstance(exc, ArtifactConflictError) else 404, detail=str(exc)) from exc
        _check_pin(content_hash(payload), expected_hash)
        return Response(
            content=canonical_json(payload) + "\n",
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{_safe_name(artifact_id)}.json"',
                "X-Canonical-SHA256": content_hash(payload),
                "X-Export-Kind": "normalized-canonical",
            },
        )


@router.get("/pipeline/{case_id}/node/{artifact_id}/export.pdf")
def pipeline_node_pdf(case_id: str, artifact_id: str, expected_hash: str | None = None, expected_source_hash: str | None = None) -> Response:
    """Deterministic PDF export of an artifact's JSON (readable sections/tables)."""
    try:
        payload, manifest = load_artifact(
            case_id, artifact_id, _output_dir(), repo_root=".", expected_source_hash=expected_source_hash)
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=409 if isinstance(exc, ArtifactConflictError) else 404, detail=str(exc)) from exc
    _check_pin(content_hash(payload), expected_hash)
    entry = manifest.by_id(artifact_id)
    subtitle = f"Case {case_id} · {artifact_id}"
    if entry is not None and entry.schema_name:
        subtitle += f" · schema {entry.schema_name}"
    # render_json_pdf is robust to oversized content (it paginates / falls back to
    # text flow and never truncates). Any residual rendering error is surfaced as
    # a clear 422 rather than a bare 500, so the Explorer degrades gracefully.
    try:
        pdf = render_json_pdf(payload, title=artifact_id, subtitle=subtitle)
    except Exception as exc:  # pragma: no cover - defensive; renderer is robust
        raise HTTPException(
            status_code=422,
            detail=f"PDF rendering failed for '{artifact_id}': {exc}") from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{_safe_name(artifact_id)}.pdf"'},
    )


def _check_pin(actual, expected):
    if expected is not None and actual != expected:
        raise HTTPException(409, 'Artifact changed since selection. Reselect the recorded node; no other run was loaded.')


def _table_columns(items):
    if not isinstance(items, list) or not items or not all(isinstance(row, dict) for row in items):
        return []
    columns = list(dict.fromkeys(key for row in items for key in row))
    if len(columns) > 9 or any(isinstance(v, (list, dict)) for row in items for v in row.values()):
        return []
    return columns


@router.get('/pipeline/{case_id}/node/{artifact_id}/report.html', response_class=HTMLResponse)
def pipeline_stage_report(case_id: str, artifact_id: str, expected_hash: str | None = None,
                          embedded: bool = False, expected_source_hash: str | None = None):
    from app.services.registry.stage_report import humanize
    from app.services.analysis_workspace import anchor
    try:
        info = inspect_node(case_id, artifact_id, _output_dir(), repo_root='.', expected_source_hash=expected_source_hash)
    except ArtifactAccessError as exc:
        raise HTTPException(409 if isinstance(exc, ArtifactConflictError) else 404, str(exc)) from exc
    _check_pin(info.get('canonical_content_hash'), expected_hash)
    report = info['presentation']
    diagram = None
    if report['family'] == 'structure' and info['payload_available']:
        payload = info['payload']
        structure = payload.get('artifact') if isinstance(payload.get('artifact'), dict) else payload
        try:
            from app.services.bo.m3_rebuild.structure import validate_structure, render_svg
            validate_structure(structure)
            diagram = Markup(render_svg(structure))
        except (ValueError, KeyError, TypeError):
            report['rendering_note'] = 'Historical structure shape: inspect recorded fields; diagram unavailable.'
    base = '/pipeline/' + quote(case_id, safe='') + '/node/' + quote(artifact_id, safe='')
    pin = '?expected_hash=' + info['canonical_content_hash'] if info.get('canonical_content_hash') else ''
    if info.get('source_file_sha256'):
        pin += '&expected_source_hash=' + info['source_file_sha256']
    identity = {k: info.get(k) for k in ['artifact_id','artifact_type','case_id','run_id','schema_name',
        'schema_version','canonical_content_hash','original_file_sha256','source_file_sha256','source_evidence_snapshot',
        'provenance','audit_subpath','validation_status','human_review_status','model_id','prompt_version']}
    return HTMLResponse(_env.get_template('pipeline_stage_report.html.j2').render(
        info=info, report=report, title=_report_title(info), diagram=diagram, identity=identity,
        base=base, pin=pin, embedded=embedded, review_href=_review_href(info),
        memo_href=('/cases/' + quote(case_id, safe='') + '/bo/runs/' + quote(info['run_id'], safe='') + '/memo.html'
                   if info['presentation']['family']=='final' and info.get('run_id') else None),
        humanize=humanize, table_columns=_table_columns,
        evidence_anchor=lambda value: anchor('evidence', value),
        raw_html=Markup(render_json_html(info['payload'], title='Recorded output'))),
        headers={'Cache-Control':'no-store'})


def _report_title(info):
    agent = info['producer'].get('agent')
    from app.services.bo.roster_v3 import V3_SPECS
    spec = next((s for s in V3_SPECS if s.agent_id == agent), None)
    if spec:
        return spec.name if hasattr(spec, 'name') else spec.title
    return {'structure':'M3 · Corporate structure', 'management':'M3 · Management continuity',
            'financial':'Financial Overview', 'debt':'M4 · Debt structure & refinancing',
            'validator':'Validation report', 'challenger':'Independent challenge',
            'synthesis':'Cross-module synthesis', 'rms':'RMS · Risk, capacity & proposed terms',
            'final':'Governed output & memo'}.get(info['presentation']['family'], info['artifact_id'])


def _review_href(info):
    from urllib.parse import urlencode
    module, run = info['producer'].get('module'), info.get('run_id')
    params = {}
    if module in {'BO', 'M1', 'M2', 'M4'} and run:
        params['bo_run'] = run
    elif module == 'FO' and run:
        params['fo_run'] = run
    elif module == 'RMS':
        sources = (info.get('payload') or {}).get('sources') or {}
        params = {key: sources[name] for key, name in [('bo_run','bo_analysis_run_id'), ('fo_run','fo_run_id')] if sources.get(name)}
    return '/cases/' + quote(info['case_id'], safe='') + '/credit.html?' + urlencode(params) if params else None
