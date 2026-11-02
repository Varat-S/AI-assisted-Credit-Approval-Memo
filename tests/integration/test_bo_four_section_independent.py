"""Independent verification: fresh producers, real frozen stages, no app patches."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import update

from app.core.hashing import canonical_json, content_hash
from app.models.base import create_engine_and_session, init_db
from app.models.orm import StageArtifact
from app.prompts.competitive_positioning import OUTPUT_VERSION
from app.services.bo.four_section import assemble, load_saved_inputs, persist, stage_name
from app.services.bo.offline import ScriptedBoBackend
from app.services.bo.runner import BusinessOverviewRunner
from app.services.bo.workbench import bo_artifact
from app.services.pipeline.artifacts import ArtifactIntegrityError, verified_artifacts
from tests import bo_helpers as h, competitive_positioning_helpers as cp
from tests.four_section_helpers import evidence, debt_output, ManagementExtractor, COMPANY
from tests.m3_rebuild.review_fixtures import FixtureReviewerBackend


def record(name, value):
    directory = Path(os.environ.get('BO_INDEPENDENT_PROOFS', '/private/tmp/bo-independent-proofs'))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')


def pointer(value, path):
    for token in path.lstrip('/').split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def build(session, path, *, industry=True):
    """Construct producers directly; do not import samples or the old run helper."""
    answers = cp.script()
    answers['m4_debt'] = debt_output()
    if not industry:
        answers['m2_industry'] = {
            'parameters': [], 'hypotheses': [],
            'missing_information': ['Independent proof: industry source analysis unavailable.'],
        }
    backend = ScriptedBoBackend(answers)
    runner = BusinessOverviewRunner(
        session, backend=backend, bo_roster='v3', sector=None,
        business_orchestrator_contract=OUTPUT_VERSION,
        data_root=path / 'data', output_root=path / 'out',
        enable_m4_debt_specialist=True, m3_extractor=ManagementExtractor(),
        m3_reviewer_backend=FixtureReviewerBackend())
    runner.m3_config = {'corporate_source': 'corporate.json', 'management_source': 'management.pdf',
                        'company': COMPANY, 'filing_period': h.PERIOD, 'extraction': None}
    result = runner.run_prepared(h.CASE, evidence(), h.metrics(), write_outputs=True)
    saved = load_saved_inputs(session, result.analysis_run_id)
    assert saved.audit['run']['validators_enforced'] is True
    assert saved.audit['challenger']['rounds'][-1]['status'] == 'validated'
    assert saved.audit['module_conclusions']['M4']['m4_debt_assessment']['validator_report']['passed'] is True
    assert backend.calls('orchestrate') == backend.calls('challenge') == 1
    return result, saved


def copied_sources(session, saved, memo, *, industry=True):
    """Read original stage bytes independently and check recursive full equality."""
    rows = {r.name: r for r in verified_artifacts(session, saved.handoff['case_id'],
                                                saved.handoff['evidence_snapshot_version'])}
    audit_stage = rows['bo_audit:' + saved.handoff['analysis_run_id']]
    audit = json.loads(audit_stage.payload_json)
    cid = saved.handoff['business_topic_conclusion_id']
    index = next(i for i, c in enumerate(audit['conclusions']) if c['conclusion_id'] == cid)
    pairs = [
        ('/module_conclusions/M3/m3_rebuild/structure/artifact', '/sections/0/structure/content'),
        ('/module_conclusions/M3/m3_rebuild/management/artifact', '/sections/1/content'),
        ('/module_conclusions/M4/m4_analysis/deliverable_1', '/sections/0/debt_obligations/content'),
        (f'/conclusions/{index}/payload', '/sections/2/content'),
        ('/orchestrator/editorial_selection', '/sections/2/editorial_selection'),
    ]
    if industry:
        pairs.append(('/module_conclusions/M2/findings', '/sections/3/content/findings'))
    checks = []
    for src, dst in pairs:
        original, copied = pointer(audit, src), pointer(memo, dst)
        assert original == copied
        assert canonical_json(original) == canonical_json(copied)
        checks.append({'source_pointer': src, 'output_pointer': dst,
                       'source_hash': content_hash(original), 'assembled_hash': content_hash(copied),
                       'deep_equal': True})
    for ref in memo['sources']:
        assert ref['stage_name'] == audit_stage.name
        assert ref['sha256'] == audit_stage.sha256
        assert ref['content_hash'] == content_hash(pointer(audit, ref['source_path']))
        assert ref['binding'] == 'same_run_verified'
    assert memo['sections'][2]['content'] == saved.current_conclusion['payload']
    selection = memo['sections'][2]['editorial_selection']
    challenge = audit['challenger']['rounds'][-1]
    assert challenge['conclusion_id'] == selection['conclusion_id'] == cid
    assert challenge['editorial_selection'] == selection
    assert selection['orchestrator_run_id'] == saved.current_conclusion['orchestrator_run_id']
    assert content_hash(selection) == saved.handoff['canonical_references']['editorial_selection_hash']
    return {'identity': memo['identity'], 'audit_stage_sha256': audit_stage.sha256,
            'snapshot_sha256': saved.snapshot_hash, 'provenance_sha256': saved.provenance_hash,
            'memo_content_hash': memo['content_hash'], 'checks': checks}


def test_independent_proof1_lossless_persisted_roundtrip(db_session, tmp_path):
    result, saved = build(db_session, tmp_path)
    memo = assemble(saved)
    before = copied_sources(db_session, saved, memo)
    assert memo['governance']['memo_completeness'] == 'complete'
    d1 = memo['sections'][0]['debt_obligations']['content']
    assert len(d1['senior_notes_schedule']) == 6
    assert len(d1['non_note_obligations_schedule']) == 4
    assert any(r['principal_drawn_m'] == 0 for r in d1['non_note_obligations_schedule'])
    assert any(r['available_facility_limit_m'] is None for r in d1['non_note_obligations_schedule'])
    assert d1['reconciling_items'][0]['amount_m'] < 0
    for row in [*d1['senior_notes_schedule'], *d1['non_note_obligations_schedule']]:
        assert {'guarantors_credit_support', 'collateral_security_status', 'priority_ranking_tier'} <= row.keys()
    path = tmp_path / 'independent-roundtrip.json'
    stage = persist(db_session, saved, memo, path=path)
    assert persist(db_session, saved, memo, path=path).sha256 == stage.sha256
    reread = bo_artifact(db_session, result.analysis_run_id, kind='four_section')
    assert json.loads(path.read_text()) == reread == memo
    assert before == copied_sources(db_session, saved, reread)
    record('proof1', {**before, 'stage_sha256': stage.sha256, 'before_and_after_persistence': 'PASS'})


def test_independent_proof2_missing_industry_producer_persists(db_session, tmp_path):
    full, full_saved = build(db_session, tmp_path / 'full')
    full_before = bo_artifact(db_session, full.analysis_run_id, kind='four_section')
    full_proof = copied_sources(db_session, full_saved, full_before)
    partial, saved = build(db_session, tmp_path / 'no-industry', industry=False)
    assert full.analysis_run_id != partial.analysis_run_id
    assert saved.audit['module_conclusions']['M2']['findings'] == []
    memo = assemble(saved)
    persist(db_session, saved, memo)
    reread = bo_artifact(db_session, partial.analysis_run_id, kind='four_section')
    assert memo == reread
    assert len(memo['sections']) == 4
    assert memo['sections'][3]['status'] == 'unavailable'
    assert memo['sections'][3]['content'] is None
    assert any('No governed M2 industry findings' in w for w in memo['sections'][3]['visible_warnings'])
    for index in (0, 1, 2):
        assert memo['sections'][index]['status'] == 'complete'
    proof = copied_sources(db_session, saved, reread, industry=False)
    # New runs have distinct provenance; compare business objects independently
    # of run-specific wrappers, and prove full exact copying within each run.
    assert memo['sections'][0]['structure']['content']['companies'] == full_before['sections'][0]['structure']['content']['companies']
    assert memo['sections'][0]['debt_obligations']['content'] == full_before['sections'][0]['debt_obligations']['content']
    management_a = deepcopy(memo['sections'][1]['content'])
    management_b = deepcopy(full_before['sections'][1]['content'])
    reviewer_a = management_a['validation']['validator_7'].pop('agent_run_id')
    reviewer_b = management_b['validation']['validator_7'].pop('agent_run_id')
    assert reviewer_a != reviewer_b
    for reviewer, source in ((reviewer_a, saved), (reviewer_b, full_saved)):
        assert any(p['agent_id'] == 'm3_validator_7' and p['agent_run_id'] == reviewer
                   and p['analysis_run_id'] == source.handoff['analysis_run_id']
                   for p in source.provenance['producer_records'])
    assert management_a == management_b
    a, b = deepcopy(memo['sections'][2]['content']), deepcopy(full_before['sections'][2]['content'])
    # Across runs only these named identity/governance fields may differ.
    # Within-run checks above compare the entire payload without exclusions.
    for payload, source, expected_challenge in (
            (a, saved, 'escalated'), (b, full_saved, 'clean')):
        assert payload.pop('analysis_run_id') == source.handoff['analysis_run_id']
        assert payload.pop('orchestrator_run_id') == source.current_conclusion['orchestrator_run_id']
        assert payload.pop('challenge_status') == expected_challenge
    assert a == b
    assert memo['governance']['memo_completeness'] == 'incomplete'
    assert memo['governance']['conclusion_status'] == saved.provenance['governance']['conclusion_status'] == 'human_review_required'
    assert full_before['governance']['conclusion_status'] == 'accepted'
    assert saved.current_conclusion['payload']['challenge_status'] == 'escalated'
    assert memo['sections'][2]['content']['challenge_status'] == 'escalated'
    assert memo['governance']['human_review_status'] == full_before['governance']['human_review_status'] == 'pending'
    assert bo_artifact(db_session, full.analysis_run_id, kind='four_section') == full_before
    record('proof2', {**proof, 'full_run_proof': full_proof, 'industry': memo['sections'][3],
                     'full_run_id': full.analysis_run_id, 'human_review_status': 'pending',
                     'memo_completeness': 'incomplete', 'producer_only_unavailability': 'PASS',
                     'substantive_content_unchanged': True,
                     'governance': {'full': full_before['governance'], 'partial': memo['governance']},
                     'challenge_status': {'full': 'clean', 'partial': 'escalated'}})


def foreign_debt(a, b):
    """Re-sign a detached envelope to isolate foreign identity from bad hashes."""
    audit, prov = deepcopy(a.audit), deepcopy(a.provenance)
    audit['module_conclusions']['M4'] = deepcopy(b.audit['module_conclusions']['M4'])
    prov['component_bindings']['debt'] = deepcopy(b.provenance['component_bindings']['debt'])
    for key in ('m4_producer_run_id', 'm4_producer_record'):
        prov[key] = deepcopy(b.provenance[key])
    prov['audit_sha256'] = content_hash(audit)
    return replace(a, audit=audit, provenance=prov, audit_hash=content_hash(audit),
                   provenance_hash=content_hash(prov))


def test_independent_proof3a_same_company_foreign_component(db_session, tmp_path):
    ra, a = build(db_session, tmp_path / 'a')
    rb, b = build(db_session, tmp_path / 'b')
    assert ra.analysis_run_id != rb.analysis_run_id
    assert a.provenance['identity']['reporting_company'] == b.provenance['identity']['reporting_company']
    original = bo_artifact(db_session, ra.analysis_run_id, kind='four_section')
    foreign = foreign_debt(a, b)
    binding = foreign.provenance['component_bindings']['debt']
    assert binding['content_hash'] == content_hash(b.audit['module_conclusions']['M4']['m4_analysis']['deliverable_1'])
    contaminated = assemble(foreign)
    debt = contaminated['sections'][0]['debt_obligations']
    assert debt['status'] == 'unavailable' and debt['content'] is None
    assert any('component identity differs' in w for w in debt['visible_warnings'])
    assert contaminated['sections'][0]['structure'] == original['sections'][0]['structure']
    assert contaminated['sections'][1:] == original['sections'][1:]
    assert bo_artifact(db_session, ra.analysis_run_id, kind='four_section') == original
    record('proof3a', {'run_a': ra.analysis_run_id, 'run_b': rb.analysis_run_id,
                      'foreign_debt_binding': binding, 'rejected_debt': debt,
                      'memo_completeness': contaminated['governance']['memo_completeness']})


def test_independent_proof3b_root_chain_tamper(db_session, tmp_path):
    result, saved = build(db_session, tmp_path)
    rows = verified_artifacts(db_session, result.case_id, result.snapshot_version)
    frozen = next(r for r in rows if r.name == stage_name(result.analysis_run_id))
    frozen_bytes, count = frozen.payload_json, len(rows)
    # Raw SQL in this disposable DB simulates corruption below the ORM guard.
    db_session.execute(update(StageArtifact).where(StageArtifact.name == 'bo_audit:' + result.analysis_run_id)
                       .values(payload_json='{"tampered":true}'), execution_options={'synchronize_session': False})
    db_session.expire_all()
    errors = []
    for operation in (lambda: assemble(load_saved_inputs(db_session, result.analysis_run_id)),
                      lambda: bo_artifact(db_session, result.analysis_run_id, kind='four_section'),
                      lambda: persist(db_session, saved, assemble(saved), path=tmp_path / 'must-not-publish.json')):
        with pytest.raises(ArtifactIntegrityError, match='integrity check failed') as exc:
            operation()
        errors.append(str(exc.value))
    assert not (tmp_path / 'must-not-publish.json').exists()
    assert db_session.query(StageArtifact).count() == count
    assert db_session.query(StageArtifact).filter_by(name=frozen.name).one().payload_json == frozen_bytes
    record('proof3b', {'run_id': result.analysis_run_id, 'errors': errors,
                      'new_file_published': False, 'existing_memo_overwritten': False})


def test_independent_proof3c_persistence_reloads_authority(db_session, tmp_path):
    ra, a = build(db_session, tmp_path / 'a')
    _, b = build(db_session, tmp_path / 'b')
    original = bo_artifact(db_session, ra.analysis_run_id, kind='four_section')
    stage = next(r for r in verified_artifacts(db_session, ra.case_id, ra.snapshot_version)
                 if r.name == stage_name(ra.analysis_run_id))
    before = (stage.payload_json, stage.sha256, stage.chain_hash)
    modified = foreign_debt(a, b)
    with pytest.raises(ArtifactIntegrityError, match='authoritative frozen stages') as modified_exc:
        persist(db_session, modified, assemble(modified), path=tmp_path / 'rejected.json')
    engine, factory = create_engine_and_session('sqlite://')
    init_db(engine)
    with factory() as empty:
        with pytest.raises(ArtifactIntegrityError, match='Selected BO run does not exist') as detached_exc:
            persist(empty, a, assemble(a))
        assert empty.query(StageArtifact).count() == 0
    engine.dispose()
    assert not (tmp_path / 'rejected.json').exists()
    assert (stage.payload_json, stage.sha256, stage.chain_hash) == before
    assert bo_artifact(db_session, ra.analysis_run_id, kind='four_section') == original
    record('proof3c', {'run_id': ra.analysis_run_id, 'modified_error': str(modified_exc.value),
                      'detached_error': str(detached_exc.value), 'existing_stage_sha256': stage.sha256,
                      'no_overwrite': True, 'no_detached_stage_created': True})
