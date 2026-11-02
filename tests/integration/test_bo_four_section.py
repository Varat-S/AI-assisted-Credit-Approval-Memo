"""Losslessness, component isolation, root integrity and idempotent persistence."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from sqlalchemy import update

from app.core.hashing import canonical_json, content_hash
from app.models.orm import StageArtifact, TopicConclusionRow, AcceptedBusinessOverviewRow
from app.schemas.bo_four_section import SECTION_TITLES, FILENAME
from app.services.bo.four_section import (
    assemble, load_saved_inputs, persist, read_four_section, stage_name, provenance_stage, _at,
)
from app.services.pipeline.artifacts import ArtifactIntegrityError, verified_artifacts
from app.services.bo.workbench import bo_artifact
from tests import four_section_helpers as f


@pytest.fixture
def populated(db_session, tmp_path):
    result, backend = f.run(db_session, tmp_path)
    return result, backend, load_saved_inputs(db_session, result.analysis_run_id)


def edit(saved, change, *, rebind=()):
    """Adversarial saved component changes, leaving root source identity intact.

    Re-signing isolates identity checks from mere digest checks. This does not
    alter the DB/frozen records and is never available to a production reader.
    """
    audit, prov, handoff = deepcopy(saved.audit), deepcopy(saved.provenance), deepcopy(saved.handoff)
    change(audit, prov, handoff)
    for name in rebind:
        b = prov['component_bindings'][name]
        b['content_hash'] = content_hash(_at(audit, b['source_path']))
    prov['audit_sha256'] = content_hash(audit)
    return replace(saved, audit=audit, provenance=prov, handoff=handoff,
                   audit_hash=content_hash(audit), provenance_hash=content_hash(prov))


def test_populated_deep_equality_order_omissions_and_persistence(populated, db_session):
    result, backend, saved = populated
    memo = result.four_section_memo
    assert memo == read_four_section(db_session, result.analysis_run_id)
    assert [(s['id'], s['title']) for s in memo['sections']] == SECTION_TITLES
    assert memo['governance']['memo_completeness'] == 'complete', [s['visible_warnings'] for s in memo['sections']]
    assert memo['sections'][0]['layout'] == 'structure_left_debt_right'
    modules = saved.audit['module_conclusions']
    copies = [
        (memo['sections'][0]['structure']['content'], modules['M3']['m3_rebuild']['structure']['artifact']),
        (memo['sections'][0]['debt_obligations']['content'], modules['M4']['m4_analysis']['deliverable_1']),
        (memo['sections'][1]['content'], modules['M3']['m3_rebuild']['management']['artifact']),
        (memo['sections'][2]['content'], saved.current_conclusion['payload']),
        (memo['sections'][2]['editorial_selection'], saved.audit['orchestrator']['editorial_selection']),
        (memo['sections'][3]['content']['findings'], modules['M2']['findings']),
    ]
    for copied, source in copies:
        assert copied == source
        assert canonical_json(copied) == canonical_json(source)  # also checks numeric representations
    d1 = memo['sections'][0]['debt_obligations']['content']
    assert len(d1['senior_notes_schedule']) == 6
    assert len(d1['non_note_obligations_schedule']) == 4
    assert any(r['principal_drawn_m'] == 0.0 for r in d1['non_note_obligations_schedule'])
    assert any(r['available_facility_limit_m'] is None for r in d1['non_note_obligations_schedule'])
    assert any('Other senior' in r['senior_note_series'] for r in d1['senior_notes_schedule'])
    assert d1['reconciling_items'][0]['amount_m'] < 0
    assert 'guarantors_credit_support' in d1['senior_notes_schedule'][0]
    assert memo['sections'][0]['structure']['visible_warnings']
    assert 'SIMULATED' in memo['sections'][0]['structure']['content']['simulation_disclaimer']
    assert memo['governance']['human_review_status'] == 'pending'
    cp = memo['sections'][2]['content']
    narrative = '\n'.join(c['text'] for c in [cp['overall_assessment'], *cp['key_drivers'], *cp['material_risks']])
    assert 'Admissions were stable during the year.' not in narrative
    assert any(h['hypothesis_id'] == 'M1S2-H001' for h in saved.audit['hypotheses']['records'])
    assert not any(c['claim_id'].startswith('COV-') for c in cp['key_drivers'] + cp['material_risks'])
    assert json.loads(result.output_paths[FILENAME].read_text()) == memo
    assert result.handoff['canonical_references']['four_section_memo']['content_hash'] == memo['content_hash']
    before = deepcopy(saved)
    assert assemble(saved) == assemble(saved) == memo
    assert saved == before
    assert backend.calls('orchestrate') == backend.calls('challenge') == 1
    assert bo_artifact(db_session, result.analysis_run_id, 'memo') == result.memo
    assert bo_artifact(db_session, result.analysis_run_id, 'audit') == result.audit


@pytest.mark.parametrize('missing,unavailable', [('M2', 3), ('M4', 0), ('M1', 2)])
def test_missing_component_preserves_others(populated, missing, unavailable):
    _, _, saved = populated
    def change(a, p, h):
        if missing == 'M1':
            h['business_topic_conclusion_id'] = None
        else:
            del a['module_conclusions'][missing]
    memo = assemble(edit(saved, change))
    assert memo['governance']['memo_completeness'] == 'incomplete'
    if missing == 'M4':
        assert memo['sections'][0]['debt_obligations']['status'] == 'unavailable'
        assert memo['sections'][0]['structure']['status'] == 'complete'
    else:
        assert memo['sections'][unavailable]['status'] == 'unavailable'
    for i in {1, 2, 3} - {unavailable}:
        assert memo['sections'][i]['content'] is not None


def test_missing_structure_preserves_management_and_debt(populated):
    _, _, saved = populated
    def change(a, p, h):
        a['module_conclusions']['M3']['m3_rebuild']['structure'].update(status='not_attempted', artifact=None,
            validation_status='not_attempted', error='No submitted corporate input')
    memo = assemble(edit(saved, change))
    assert memo['sections'][0]['structure']['content'] is None
    assert memo['sections'][0]['debt_obligations']['content'] is not None
    assert memo['sections'][1]['content'] is not None


def test_malformed_structure_contract_is_component_local(populated):
    _, _, saved = populated
    def change(a, p, h):
        a['module_conclusions']['M3']['m3_rebuild']['structure']['artifact']['companies'] = {}
    memo = assemble(edit(saved, change, rebind=['structure']))
    assert memo['sections'][0]['structure']['status'] == 'unavailable'
    assert memo['sections'][0]['debt_obligations']['status'] == 'complete'
    assert memo['sections'][1]['status'] == 'complete'


def test_partial_reviewed_management_is_copied_whole(populated):
    _, _, saved = populated
    def change(a, p, h):
        c = a['module_conclusions']['M3']['m3_rebuild']['management']
        c.update(status='partial', validation_status='partial')
        c['artifact']['completion_status'] = 'partial'
        c['artifact']['coverage']['missing'] = ['Undisclosed executive biography']
        c['artifact']['limitations'].append('Coverage is partial.')
    adjusted = edit(saved, change, rebind=['management'])
    memo = assemble(adjusted)
    assert memo['sections'][1]['status'] == 'partial'
    assert memo['sections'][1]['content'] == adjusted.audit['module_conclusions']['M3']['m3_rebuild']['management']['artifact']
    assert memo['governance']['memo_completeness'] == 'incomplete'


@pytest.mark.parametrize('defect', ['failed', 'advisory', 'failed_check', 'wrong_hash', 'wrong_case', 'wrong_run', 'wrong_snapshot', 'wrong_period', 'wrong_company', 'wrong_producer', 'different_d1'])
def test_debt_integrity_failure_is_component_local(populated, defect):
    _, _, saved = populated
    def change(a, p, h):
        m = a['module_conclusions']['M4']
        if defect in {'failed', 'advisory'}:
            m['m4_debt_status'] = m['m4_debt_assessment']['status'] = defect
            m['m4_debt_assessment']['validated'] = False
        elif defect == 'failed_check':
            m['m4_debt_assessment']['validator_report']['checks'][0]['passed'] = False
        elif defect.startswith('wrong_') and defect[6:] in {'case', 'run', 'snapshot'}:
            key = {'case': 'case_id', 'run': 'analysis_run_id', 'snapshot': 'evidence_snapshot_version'}[defect[6:]]
            p['component_bindings']['debt']['identity'][key] = 'foreign'
        elif defect == 'wrong_hash':
            p['component_bindings']['debt']['content_hash'] = '0' * 64
        elif defect in {'wrong_period', 'wrong_company'}:
            target = 'Northfield Health Systems FY2024' if defect == 'wrong_period' else 'Another Company FY2025'
            m['m4_debt_assessment']['assessment']['deliverable_4']['executive_credit_summary_box']['target_entity_and_period'] = target
        elif defect == 'wrong_producer':
            p['m4_producer_record']['case_id'] = 'foreign'
        else:
            m['m4_analysis']['deliverable_1']['senior_notes_schedule'][0]['principal_amount_m'] = 123.12345
    memo = assemble(edit(saved, change, rebind=['debt'] if defect == 'different_d1' else []))
    assert memo['sections'][0]['debt_obligations']['status'] == 'unavailable'
    assert all(s['content'] is not None for s in memo['sections'][1:])


@pytest.mark.parametrize('defect', ['company', 'period', 'cutoff', 'source_hash', 'packet_run', 'packet_hash', 'binding'])
def test_management_integrity_failure_keeps_structure_and_other_modules(populated, defect):
    _, _, saved = populated
    def change(a, p, h):
        m = a['module_conclusions']['M3']['m3_rebuild']['management']['artifact']
        if defect == 'company': m['company'] = 'Other Company'
        elif defect == 'period': m['filing_period'] = '2024-12-31'
        elif defect == 'cutoff': m['roster_date'] = '2099-01-01'
        elif defect == 'source_hash': m['source']['sha256'] = '0' * 64
        elif defect == 'packet_run':
            p['m3_packet']['analysis_run_id'] = 'foreign'
            p['m3_packet']['packet_hash'] = content_hash({k: v for k, v in p['m3_packet'].items() if k != 'packet_hash'})
        elif defect == 'packet_hash': p['m3_packet']['packet_hash'] = '0' * 64
        else: p['component_bindings']['management']['identity']['case_id'] = 'foreign'
    memo = assemble(edit(saved, change, rebind=['management']))
    assert memo['sections'][1]['status'] == 'unavailable'
    assert memo['sections'][0]['debt_obligations']['content'] is not None
    assert memo['sections'][2]['content'] is not None and memo['sections'][3]['content'] is not None


@pytest.mark.parametrize('defect', ['conclusion', 'producer', 'challenge', 'selection_hash', 'superseded'])
def test_competitive_positioning_binding_is_component_local(populated, defect):
    _, _, saved = populated
    def change(a, p, h):
        if defect == 'conclusion': h['business_topic_conclusion_id'] = 'foreign-conclusion'
        elif defect == 'producer': a['orchestrator']['editorial_selection']['orchestrator_run_id'] = 'foreign-producer'
        elif defect == 'challenge': a['challenger']['rounds'][-1]['conclusion_id'] = 'foreign-conclusion'
        elif defect == 'selection_hash': h['canonical_references']['editorial_selection_hash'] = '0' * 64
        else: a['conclusions'][-1]['acceptance_state'] = 'superseded'
    memo = assemble(edit(saved, change))
    assert memo['sections'][2]['status'] == 'unavailable'
    assert memo['sections'][2]['content'] is None
    assert memo['sections'][1]['content'] is not None and memo['sections'][3]['content'] is not None


def test_industry_foreign_canonical_record_is_not_copied(populated):
    _, _, saved = populated
    def change(a, p, h):
        next(r for r in a['hypotheses']['records'] if r['agent_id'] == 'm2_industry')['analysis_run_id'] = 'foreign-run'
    memo = assemble(edit(saved, change))
    assert memo['sections'][3]['content'] is None
    assert memo['sections'][2]['content'] is not None


def test_root_frozen_audit_tamper_fails_closed(populated, db_session):
    result, _, _ = populated
    row = next(r for r in verified_artifacts(db_session, result.case_id, result.snapshot_version)
               if r.name == 'bo_audit:' + result.analysis_run_id)
    db_session.execute(update(StageArtifact).where(StageArtifact.case_id == row.case_id,
        StageArtifact.evidence_version == row.evidence_version, StageArtifact.name == row.name).values(payload_json='{}'))
    db_session.expire_all()
    with pytest.raises(ArtifactIntegrityError):
        read_four_section(db_session, result.analysis_run_id)


def test_saved_input_hash_tamper_is_root_error(populated):
    _, _, saved = populated
    changed = deepcopy(saved)
    changed.audit['case']['case_id'] = 'foreign'
    with pytest.raises(ArtifactIntegrityError): assemble(changed)


@pytest.mark.parametrize('field,value', [('case_id', 'another-company'), ('analysis_run_id', 'foreign-run'),
                                      ('as_of_date', '2024-12-31'), ('evidence_snapshot_version', 9)])
def test_correctly_hashed_foreign_root_still_fails_closed(populated, field, value):
    _, _, saved = populated
    def change(a, p, h):
        if field == 'analysis_run_id': a['run'][field] = value
        else: a['case'][field] = value
    bad = edit(saved, change)
    with pytest.raises(ArtifactIntegrityError): assemble(bad)


def test_idempotent_freeze_and_no_file_or_stage_overwrite(populated, db_session, tmp_path):
    result, _, saved = populated
    memo = result.four_section_memo
    before = len(verified_artifacts(db_session, result.case_id, result.snapshot_version))
    persist(db_session, saved, memo, path=result.output_paths[FILENAME])
    assert len(verified_artifacts(db_session, result.case_id, result.snapshot_version)) == before
    bad = deepcopy(memo)
    bad['sections'][0]['visible_warnings'].append('different')
    bad['content_hash'] = content_hash({k: v for k, v in bad.items() if k != 'content_hash'})
    with pytest.raises(ArtifactIntegrityError): persist(db_session, saved, bad)
    changed = edit(saved, lambda a, p, h: a['module_conclusions'].pop('M2'))
    with pytest.raises(ArtifactIntegrityError, match='authoritative frozen stages'):
        persist(db_session, changed, assemble(changed))
    path = tmp_path / FILENAME
    path.write_text('{"unverified":"old file"}')
    with pytest.raises(ArtifactIntegrityError): persist(db_session, saved, memo, path=path)
    assert path.read_text() == '{"unverified":"old file"}'


def test_partial_real_run_and_legacy_not_backfilled(db_session, tmp_path):
    result, _ = f.run(db_session, tmp_path, populated=False)
    memo = result.four_section_memo
    assert memo['governance']['memo_completeness'] == 'incomplete'
    assert memo['sections'][0]['status'] == 'unavailable'
    assert memo['sections'][1]['content'] is None
    assert memo['sections'][2]['content'] is not None and memo['sections'][3]['content'] is not None
    from tests.integration.test_bo_v3_complete import _run
    legacy, _ = _run(db_session, tmp_path / 'legacy')
    assert legacy.four_section_memo is None
    assert bo_artifact(db_session, legacy.analysis_run_id, 'memo') == legacy.memo
    with pytest.raises(ArtifactIntegrityError): read_four_section(db_session, legacy.analysis_run_id)


def test_industry_keeps_low_materiality_order_and_nested_precision(populated):
    _, _, saved = populated
    def change(a, p, h):
        original = a['module_conclusions']['M2']['findings'][0]
        extra = deepcopy(original)
        extra.update(hypothesis_id='M2-H002', materiality='low')
        extra['quoted_values'] = [{'parameter_result_id': 'saved-source-trace', 'value': 0.123456789012345,
                                    'unit': 'ratio', 'period': '2025-12-31', 'denominator': None}]
        canonical = deepcopy(next(r for r in a['hypotheses']['records'] if r['agent_id'] == 'm2_industry'))
        canonical.update(extra)
        a['hypotheses']['records'].append(canonical)
        a['module_conclusions']['M2']['findings'] = [extra, original]
        a['module_conclusions']['M2']['status'] = 'incomplete'
    adjusted = edit(saved, change, rebind=['industry'])
    section = assemble(adjusted)['sections'][3]
    assert section['status'] == 'partial'
    assert canonical_json(section['content']['findings']) == canonical_json(adjusted.audit['module_conclusions']['M2']['findings'])


def test_assembly_and_reads_never_invoke_models_validators_or_local_sources(populated, db_session, monkeypatch):
    from pathlib import Path
    from app.services.llm.client import LLMClient
    from app.services.bo.hypotheses import HypothesisValidator
    from app.services.modules.module4.debt_structure_validator import DebtStructureValidator
    from app.services.bo.m3_rebuild import structure, contracts

    result, backend, saved = populated
    before_calls = len(backend.requests)
    def forbidden(*args, **kwargs):
        pytest.fail('Assembly must not invoke inference, specialist validation or local source file reads.')
    monkeypatch.setattr(LLMClient, 'generate_only', forbidden)
    monkeypatch.setattr(HypothesisValidator, 'validate', forbidden)
    monkeypatch.setattr(DebtStructureValidator, 'validate', forbidden)
    monkeypatch.setattr(structure, 'validate_structure', forbidden)
    monkeypatch.setattr(contracts, 'validate_management', forbidden)
    monkeypatch.setattr(Path, 'read_text', forbidden)
    assert assemble(saved) == result.four_section_memo
    assert read_four_section(db_session, result.analysis_run_id) == result.four_section_memo
    assert len(backend.requests) == before_calls


def test_review_overlay_does_not_rewrite_frozen_memo(populated, db_session):
    from app.services.bo.handoff import review_handoff, read_handoff
    result, _, _ = populated
    before = read_four_section(db_session, result.analysis_run_id)
    review_handoff(db_session, result.handoff['handoff_id'], reviewer='Offline acceptance reviewer',
                   reason='Review of this exact fictional assembled output', acknowledge_unresolved=True)
    assert read_handoff(db_session, result.handoff['handoff_id']).human_review_status == 'accepted'
    assert read_four_section(db_session, result.analysis_run_id) == before
    assert before['governance']['human_review_status'] == 'pending'


def test_two_runs_of_same_company_never_use_latest_output(populated, db_session, tmp_path):
    first, _, _ = populated
    second, _ = f.run(db_session, tmp_path / 'second')
    assert first.analysis_run_id != second.analysis_run_id
    assert read_four_section(db_session, first.analysis_run_id)['identity']['analysis_run_id'] == first.analysis_run_id
    assert read_four_section(db_session, second.analysis_run_id)['identity']['analysis_run_id'] == second.analysis_run_id


def test_registry_discovers_new_artifact_without_changing_legacy_inventory(populated):
    from app.services.registry.indexer import _index_bo_run
    result, _, _ = populated
    root = result.output_paths[FILENAME].parents[3]
    entries = _index_bo_run(result.output_paths[FILENAME].parent, root, result.case_id)
    entry = next(e for e in entries if e.artifact_id == 'bo.four_section.' + result.analysis_run_id)
    assert entry.schema_version == result.four_section_memo['schema_version']
    assert entry.human_review_status.value == 'pending'
    assert entry.status.value == 'qualified'


def test_normal_prepared_pipeline_freezes_same_root_without_reacquisition(db_session, tmp_path):
    from app.services.bo.runner import BusinessOverviewRunner
    from app.services.bo.offline import ScriptedBoBackend
    from app.prompts.competitive_positioning import OUTPUT_VERSION
    from tests import competitive_positioning_helpers as cp
    from tests.m3_rebuild.test_shared_input_integration import _package, OfflinePacketExtractor
    from tests.m3_rebuild.review_fixtures import FixtureReviewerBackend

    result = BusinessOverviewRunner(
        db_session, backend=ScriptedBoBackend(cp.script()), bo_roster='v3', sector=None,
        business_orchestrator_contract=OUTPUT_VERSION, data_root=tmp_path / 'data', output_root=tmp_path / 'out',
        m3_extractor=OfflinePacketExtractor(), m3_reviewer_backend=FixtureReviewerBackend(),
    ).run_case('FOUR_SECTION_NORMAL_PREPARATION', package=_package(), write_outputs=False)
    memo = read_four_section(db_session, result.analysis_run_id)
    assert memo['sections'][0]['structure']['content'] is not None
    assert memo['sections'][1]['content']['company'] == 'Delta Synthetic Fixture'
    assert memo['identity']['as_of_date'] == '2024-12-31'


def test_handoff_cannot_point_at_an_incompatible_assembled_artifact(populated, db_session):
    from app.services.bo.reporting import handoff_content_hash
    result, _, _ = populated
    row = db_session.get(AcceptedBusinessOverviewRow, result.handoff['handoff_id'])
    handoff = deepcopy(row.payload)
    handoff['canonical_references']['four_section_memo']['content_hash'] = '0' * 64
    handoff['content_hash'] = handoff_content_hash(handoff)
    row.payload, row.content_hash = handoff, handoff['content_hash']
    with pytest.raises(ArtifactIntegrityError, match='handoff binding'):
        read_four_section(db_session, result.analysis_run_id)


def test_detached_example_cannot_be_persisted_without_authoritative_run(populated):
    from app.models.base import create_engine_and_session, init_db
    result, _, saved = populated
    engine, factory = create_engine_and_session('sqlite://')
    init_db(engine)
    with factory() as empty:
        with pytest.raises(ArtifactIntegrityError, match='Selected BO run does not exist'):
            persist(empty, saved, result.four_section_memo)
        assert empty.query(StageArtifact).count() == 0
    engine.dispose()
