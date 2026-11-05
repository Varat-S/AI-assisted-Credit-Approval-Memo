"""Pipeline Explorer backing service — discover demonstrable cases and resolve
one into a manifest + dataflow graph, with artifact-access safety.

This layer is deliberately filesystem-driven so the Explorer is demonstrable
with real recorded artifacts even when no live DB run exists. It resolves the
configured ``output_dir`` (``<output>/bo/<case>``, ``<output>/fo/<case>`` and
``<output>/m3_rebuild/<case>``).

Artifact access is validated: an artifact id must resolve to a file *inside* the
configured roots, and resolved paths are confirmed not to escape them (no
traversal, no following into unrelated directories). Nothing outside the output
root can be read through the Explorer, so
credentials, ``.env`` and unrelated files are never exposed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.schemas.artifact_manifest import ArtifactManifest
from app.services.registry.graph import build_pipeline_graph
from app.services.registry.indexer import build_manifest


@dataclass(frozen=True)
class CaseSource:
    """A discoverable case the Explorer can render."""

    case_id: str
    label: str
    kind: str                      # "live"
    output_root: Path
    repo_root: Path
    m3_dirs: tuple[Path, ...] = ()
    note: Optional[str] = None


def discover_cases(
    output_dir: str | Path,
    *,
    repo_root: str | Path = ".",
) -> list[CaseSource]:
    """List the cases the Explorer can render (recorded pipeline output)."""
    output_root = Path(output_dir)
    repo = Path(repo_root)
    found: dict[str, CaseSource] = {}

    for family in ("bo", "fo", "m3_rebuild", "rms"):
        base = output_root / family
        if base.is_dir():
            for case_dir in sorted(p for p in base.iterdir() if p.is_dir()):
                cid = case_dir.name
                if cid not in found:
                    found[cid] = CaseSource(
                        case_id=cid, label=cid, kind="live",
                        output_root=output_root, repo_root=repo,
                        note="Recorded output of a pipeline run.",
                    )

    return list(found.values())


def _source_for(
    case_id: str, output_dir: str | Path, repo_root: str | Path
) -> Optional[CaseSource]:
    for source in discover_cases(output_dir, repo_root=repo_root):
        if source.case_id == case_id:
            return source
    return None


def manifest_for_case(
    case_id: str, output_dir: str | Path, *, repo_root: str | Path = "."
) -> Optional[ArtifactManifest]:
    source = _source_for(case_id, output_dir, repo_root)
    if source is None:
        return None
    return build_manifest(
        source.output_root, case_id,
        m3_dirs=list(source.m3_dirs), repo_root=source.repo_root,
    )


def graph_for_case(
    case_id: str, output_dir: str | Path, *, repo_root: str | Path = ".",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Return the dataflow graph for a case; illustration graph if unknown."""
    manifest = manifest_for_case(case_id, output_dir, repo_root=repo_root)
    if run_id and (manifest is None or not any(a.run_id == run_id for a in manifest.artifacts)):
        raise ArtifactAccessError('The selected run does not exist for this case.')
    graph = build_pipeline_graph(manifest, run_id=run_id)
    graph["case_id"] = case_id
    if manifest:
        from hashlib import sha256
        from app.services.registry.stage_report import states
        source = _source_for(case_id, output_dir, repo_root)
        hashes = {}
        documents = {}
        for node in graph['nodes']:
            entry = manifest.by_id(node.get('artifact_id'))
            if entry and entry.file_location:
                try:
                    path = _safe_resolve(source.repo_root / entry.file_location, [source.output_root])
                    if path not in hashes:
                        raw = path.read_bytes()
                        hashes[path] = sha256(raw).hexdigest()
                        documents[path] = json.loads(raw)
                    node['source_file_sha256'] = hashes[path]
                    payload = _extract_slice(documents[path], entry) if entry.audit_subpath else documents[path]
                    node['states'] = states(entry, payload)
                except (ArtifactAccessError, OSError, ValueError):
                    node['source_file_sha256'] = None
    return graph


class ArtifactAccessError(ValueError):
    """Raised when an artifact id cannot be safely resolved to a readable file."""


class ArtifactConflictError(ArtifactAccessError):
    """Recorded integrity or exact-run identity could not be verified."""


def _verified_read(path, entry, output_root=None):
    from app.core.hashing import content_hash
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as exc:
        raise ArtifactConflictError('Artifact is missing, corrupt or unreadable.') from exc
    if entry.status.value == 'error' or (entry.producer_module == 'M3' and
            entry.artifact_id.startswith('m3.rebuild.') and not entry.content_hash):
        raise ArtifactConflictError(entry.status_reason or 'Recorded component failed integrity verification.')
    if not entry.audit_subpath and entry.content_hash and content_hash(payload) != entry.content_hash:
        raise ArtifactConflictError('Artifact content hash differs from the indexed artifact.')
    if isinstance(payload, dict):
        for field, expected in [('case_id', entry.case_id), ('analysis_run_id', entry.run_id),
                                ('run_id', entry.run_id)]:
            if payload.get(field) is not None and expected and payload[field] != expected:
                raise ArtifactConflictError(f'Artifact {field} differs from its exact directory binding.')
        case = payload.get('case')
        run = payload.get('run')
        if isinstance(case, dict) and case.get('case_id') not in (None, entry.case_id):
            raise ArtifactConflictError('Artifact case differs from its exact directory binding.')
        if isinstance(run, dict) and run.get('analysis_run_id') not in (None, entry.run_id):
            raise ArtifactConflictError('Artifact run differs from its exact directory binding.')
        if entry.artifact_id.startswith('bo.four_section.'):
            from app.services.bo.four_section import verify_memo
            try:
                verify_memo(payload)
                identity = payload['identity']
                if identity['case_id'] != entry.case_id or identity['analysis_run_id'] != entry.run_id:
                    raise ValueError('Memo identity mismatch')
                audit_path = _safe_resolve(path.parent / 'audit_report.json',
                                           [Path(output_root) if output_root else path.parent])
                if audit_path.is_file():
                    from app.services.bo.four_section import _at
                    audit = json.loads(audit_path.read_bytes())
                    for ref in payload['sources']:
                        if (ref['stage_name'] != 'bo_audit:' + entry.run_id or
                                ref['sha256'] != content_hash(audit) or
                                ref['content_hash'] != content_hash(_at(audit, ref['source_path']))):
                            raise ValueError('Memo source differs from its exact-run recorded binding.')
            except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
                raise ArtifactConflictError(str(exc)) from exc
        if entry.producer_module == 'RMS' and output_root is not None:
            sources = payload.get('sources') or {}
            fo_run = sources.get('fo_run_id')
            if fo_run:
                fo_path = _safe_resolve(Path(output_root) / 'fo' / entry.case_id / fo_run /
                                        'financial_overview.json', [Path(output_root)])
                if fo_path.is_file() and sources.get('fo_content_hash'):
                    try:
                        digest = content_hash(json.loads(fo_path.read_bytes()))
                    except (OSError, ValueError) as exc:
                        raise ArtifactConflictError('RMS bound FO source is unreadable.') from exc
                    if digest != sources['fo_content_hash']:
                        raise ArtifactConflictError('RMS FO source differs from its recorded content-hash binding.')
    return raw, payload


def _read_entry(source, entry, expected_source_hash=None):
    path = _safe_resolve(source.repo_root / entry.file_location,
                         [source.output_root, *source.m3_dirs])
    if not path.is_file():
        raise ArtifactAccessError(f'artifact file missing: {entry.file_location}')
    raw, payload = _verified_read(path, entry, source.output_root)
    if expected_source_hash:
        from hashlib import sha256
        if sha256(raw).hexdigest() != expected_source_hash:
            raise ArtifactConflictError('Recorded source bytes changed since selection; no fallback run was loaded.')
    return raw, payload


def _safe_resolve(candidate: Path, roots: list[Path]) -> Path:
    """Resolve ``candidate`` and confirm it lives under one of ``roots``."""
    resolved = candidate.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise ArtifactAccessError("artifact path escapes the permitted roots")


def load_artifact(
    case_id: str,
    artifact_id: str,
    output_dir: str | Path,
    *,
    repo_root: str | Path = ".",
    expected_source_hash: str | None = None,
) -> tuple[Any, ArtifactManifest]:
    """Return ``(payload, manifest)`` for an artifact, enforcing access bounds.

    The ``artifact_id`` must appear in the case's manifest and resolve to a file
    under the case's permitted roots. Absent/skipped entries have no payload and
    raise :class:`ArtifactAccessError` with their recorded reason.
    """
    source = _source_for(case_id, output_dir, repo_root)
    if source is None:
        raise ArtifactAccessError(f"unknown case: {case_id}")
    manifest = manifest_for_case(case_id, output_dir, repo_root=repo_root)
    if manifest is None:
        raise ArtifactAccessError(f"no manifest for case: {case_id}")

    entry = manifest.by_id(artifact_id)
    if entry is None:
        raise ArtifactAccessError(f"unknown artifact: {artifact_id}")
    if not entry.file_location:
        raise ArtifactAccessError(
            f"artifact '{artifact_id}' has no payload ({entry.status.value}: "
            f"{entry.status_reason or 'not produced'})"
        )

    _, payload = _read_entry(source, entry, expected_source_hash)
    # Entries that index a slice of a shared recorded file (BO audit or memo)
    # return THAT producer's own recorded output, not the whole file.
    if entry.audit_subpath:
        payload = _extract_slice(payload, entry)
    return payload, manifest


def _extract_slice(doc: Any, entry) -> Any:
    """Resolve an ``audit_subpath`` to the producer's own recorded slice.

    Two forms: ``agents[agent_id=<id>]`` (per-agent / synthesis / challenger from
    the audit) or a dotted path (e.g. ``module_conclusions.M4.m4_debt_assessment``,
    ``final_conclusion``, ``evidence_snapshot``) into the memo or audit.
    """
    subpath = entry.audit_subpath or ""
    if subpath.startswith("agents[agent_id="):
        # The agent id is taken from the SUBPATH (authoritative), not from
        # entry.producer_agent, so a validator node (whose producer_agent may be
        # the agent it validates, or None) always resolves to the right block and
        # never falls back to records with agent_id == None.
        rest = subpath[len("agents[agent_id="):]
        agent_id, _, view = rest.partition("]")
        view = view.lstrip("#") or None
        return _extract_agent_slice(doc, entry, agent_id=agent_id, view=view)
    node: Any = doc
    for part in subpath.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise ArtifactConflictError(f"Recorded slice '{subpath}' not found in this run.")
    return node


def load_artifact_bytes(
    case_id: str,
    artifact_id: str,
    output_dir: str | Path,
    *,
    repo_root: str | Path = ".",
    expected_source_hash: str | None = None,
) -> tuple[bytes, str, ArtifactManifest]:
    """Return ``(raw_bytes, original_sha256, manifest)`` for a whole-file artifact.

    This is the EXACT recorded bytes on disk (not a re-serialisation), with the
    original SHA-256 of those bytes — so a download preserves byte-for-byte
    integrity. Per-agent slice artifacts (which index a section of a shared file,
    e.g. the BO audit) have no independent original file and raise
    :class:`ArtifactAccessError`; use the normalized export for those.
    """
    source = _source_for(case_id, output_dir, repo_root)
    if source is None:
        raise ArtifactAccessError(f"unknown case: {case_id}")
    manifest = manifest_for_case(case_id, output_dir, repo_root=repo_root)
    if manifest is None:
        raise ArtifactAccessError(f"no manifest for case: {case_id}")
    entry = manifest.by_id(artifact_id)
    if entry is None:
        raise ArtifactAccessError(f"unknown artifact: {artifact_id}")
    if entry.audit_subpath:
        raise ArtifactAccessError(
            f"artifact '{artifact_id}' indexes a slice of a shared file "
            f"({entry.file_location}); it has no independent original bytes. "
            f"Use the normalized export instead.")
    if not entry.file_location:
        raise ArtifactAccessError(
            f"artifact '{artifact_id}' has no payload ({entry.status.value}: "
            f"{entry.status_reason or 'not produced'})")

    import hashlib
    raw, _ = _read_entry(source, entry, expected_source_hash)
    original_sha256 = hashlib.sha256(raw).hexdigest()
    return raw, original_sha256, manifest


def _extract_agent_slice(audit: Any, entry, *, agent_id: str | None = None,
                         view: str | None = None) -> dict[str, Any]:
    """Pull one agent/validator/synthesis/challenger slice from a BO audit report.

    ``agent_id`` is the authoritative producer id taken from the audit subpath.
    ``view`` optionally narrows the slice: ``"validation"`` returns only the
    agent's recorded validation record (status, issues, validator adjustments,
    per-run validation outcomes) — used by validator nodes so they show their own
    validation result, never another producer's hypotheses/parameters.

    Returns the recorded output for that producer only, so the inspector shows
    the agent's actual output rather than the whole memo/audit.
    """
    if not isinstance(audit, dict):
        return {"error": "audit report is not an object"}
    if agent_id is None:
        agent_id = entry.producer_agent
    out: dict[str, Any] = {"agent_id": agent_id, "run_id": entry.run_id,
                           "schema_version": "bo-agent-record-1.0"}

    agent_block = next(
        (a for a in (audit.get("agents") or []) if isinstance(a, dict)
         and a.get("agent_id") == agent_id), None)

    if agent_block is None:
        # The named producer is not in this run's audit -> report absence
        # explicitly rather than selecting unrelated records.
        raise ArtifactConflictError(f"No recorded audit block for agent '{agent_id}' in this run.")

    # VALIDATION view: a validator node for this agent shows the validation
    # record only (the roster-v3 agent carries its validator's result).
    if view == "validation":
        out["view"] = "validation"
        out["validator_id"] = entry.producer_validator
        runs = agent_block.get("runs") or []
        out["validation"] = {
            "agent_id": agent_id,
            "status": agent_block.get("status"),
            "detail": agent_block.get("detail"),
            "validation_issues": agent_block.get("validation_issues") or [],
            "validator_adjustments": agent_block.get("validator_adjustments") or [],
            "runs": [{"agent_run_id": r.get("agent_run_id"),
                      "error_state": r.get("error_state"),
                      "validation_status": r.get("validation_status"),
                      "validation_detail": r.get("validation_detail")}
                     for r in runs],
        }
        return out

    out["agent"] = agent_block
    if agent_id == "business_orchestrator":
        out["synthesis"] = audit.get("orchestrator")
        out["conclusion"] = audit.get("final_conclusion") or audit.get("conclusions")
    elif agent_id == "business_challenge":
        out["challenge"] = audit.get("challenger")
    else:
        records = (audit.get("hypotheses", {}) or {}).get("records", []) \
            if isinstance(audit.get("hypotheses"), dict) else []
        out["hypotheses"] = [r for r in records if r.get("agent_id") == agent_id]
        out["parameters"] = [p for p in (audit.get("parameters") or [])
                             if p.get("agent_id") == agent_id]
        packets = audit.get("evidence_packets") or []
        out["evidence_packet"] = next(
            (p for p in packets if isinstance(p, dict) and p.get("agent_id") == agent_id),
            None)
    referenced = set(_collect_evidence_ids(out))
    out['sources'] = [record for record in audit.get('sources') or []
                      if isinstance(record, dict) and record.get('evidence_id') in referenced]
    return out


def _collect_evidence_ids(payload: Any) -> list[str]:
    """Best-effort pull of evidence ids referenced anywhere in a payload."""
    ids: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"evidence_ids", "packet_evidence_ids", "source_fact_ids",
                           "evidence_refs", "supporting_evidence_ids", "contradicting_evidence_ids",
                           "citation_ids"} and isinstance(value, list):
                    ids.update(str(v) for v in value if isinstance(v, (str, int)))
                elif key in {"evidence_id", "fact_id", "source_id"} and isinstance(
                        value, (str, int)):
                    ids.add(str(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return sorted(ids)


def inspect_node(
    case_id: str,
    artifact_id: str,
    output_dir: str | Path,
    *,
    repo_root: str | Path = ".",
    expected_source_hash: str | None = None,
) -> dict[str, Any]:
    """Assemble the node-inspector payload for one artifact.

    Returns identity, status, inputs/dependencies, evidence ids, validation and
    escalation signals, model/prompt provenance, a human-readable summary and the
    raw JSON. For an absent/skipped artifact it returns the *reason*, not mock
    output.
    """
    manifest = manifest_for_case(case_id, output_dir, repo_root=repo_root)
    if manifest is None:
        raise ArtifactAccessError(f"no manifest for case: {case_id}")
    entry = manifest.by_id(artifact_id)
    if entry is None:
        raise ArtifactAccessError(f"unknown artifact: {artifact_id}")

    info: dict[str, Any] = {
        "artifact_id": entry.artifact_id,
        "artifact_type": entry.artifact_type.value,
        "case_id": entry.case_id,
        "run_id": entry.run_id,
        "producer": {
            "module": entry.producer_module,
            "agent": entry.producer_agent,
            "validator": entry.producer_validator,
        },
        "status": entry.status.value,
        "status_reason": entry.status_reason,
        # Financial Overview facets (populated for FO artifacts).
        "rating_provisional": entry.rating_provisional,
        "composite_score": entry.composite_score,
        "credit_rating": entry.credit_rating,
        "risk_level": entry.risk_level,
        "fo_measures": list(entry.fo_measures),
        "fo_triggers_fired": list(entry.fo_triggers_fired),
        "fo_prechecks": list(entry.fo_prechecks),
        "schema_name": entry.schema_name,
        "schema_version": entry.schema_version,
        "content_hash": entry.content_hash,       # canonical SHA-256 of the payload
        "canonical_content_hash": entry.content_hash,
        "original_file_sha256": None,             # set below for whole-file artifacts
        "is_slice": bool(entry.audit_subpath),
        "audit_subpath": entry.audit_subpath,
        "source_evidence_snapshot": entry.source_evidence_snapshot,
        "provenance": entry.provenance.model_dump(mode="json") if entry.provenance else None,
        "depends_on": entry.depends_on,
        "validation_status": entry.validation_status,
        "validator_issues_count": entry.validator_issues_count,
        "human_review_status": entry.human_review_status.value,
        "escalations": entry.escalations,
        "model_id": entry.model_id,
        "prompt_version": entry.prompt_version,
        "model_invoked": entry.model_invoked,
        "file_location": entry.file_location,
        "payload_available": bool(entry.file_location),
        "payload": None,
        "evidence_ids": list(entry.evidence_ids),
    }
    from app.services.registry.stage_report import states, presentation
    info['states'] = states(entry)

    from app.schemas.artifact_manifest import ExecutionStatus
    if not entry.file_location or entry.status in (
            ExecutionStatus.ABSENT, ExecutionStatus.SKIPPED):
        # Absent/skipped: report the reason, never fabricate or load a payload.
        info['payload_available'] = False
        info['presentation'] = presentation(info)
        return info

    source = _source_for(case_id, output_dir, repo_root)
    raw, payload = _read_entry(source, entry, expected_source_hash)
    info['source_disclosures'] = {key: payload[key] for key in
        ['data_status', 'simulation_notice', 'simulation_provenance', 'agent_mode', 'synthetic', 'simulated']
        if isinstance(payload, dict) and key in payload}
    if entry.audit_subpath:
        payload = _extract_slice(payload, entry)
    info["payload"] = payload
    from app.core.hashing import content_hash
    from app.services.registry.stage_report import states, presentation
    info['canonical_content_hash'] = content_hash(payload)
    from hashlib import sha256
    info['source_file_sha256'] = sha256(raw).hexdigest()
    info['states'] = states(entry, payload)
    if not entry.audit_subpath:
        from hashlib import sha256
        info['original_file_sha256'] = sha256(raw).hexdigest()
    if not info["evidence_ids"]:
        info["evidence_ids"] = _collect_evidence_ids(payload)
    if isinstance(payload, dict):
        issues = payload.get("validation_issues")
        if isinstance(issues, list):
            info["validator_issues"] = issues
        if payload.get("rejected_items"):
            info["rejected_items"] = payload["rejected_items"]
    info['presentation'] = presentation(info)
    return info
