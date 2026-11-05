"""Offline HTTP regression tests over committed recorded viewer fixtures.

These tests exercise presentation and integrity, not live-model accuracy.
"""
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import create_app
from tests.registry_fixture import CASE, MANAGEMENT_ID, STRUCTURE_ID

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'pipeline_viewer'


@pytest.fixture()
def recorded(tmp_path, monkeypatch):
    root = tmp_path / 'recorded'
    shutil.copytree(FIXTURES, root)
    monkeypatch.setattr('app.api.pipeline_explorer._output_dir', lambda: str(root))
    return root, TestClient(create_app())


def url(aid, suffix=''):
    return f'/pipeline/{CASE}/node/{quote(aid, safe="")}{suffix}'


def digests(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_graph_requires_exact_run_and_preserves_specialist_mappings(recorded):
    _, client = recorded
    graph = client.get(f'/pipeline/{CASE}/graph.json').json()
    assert graph['selection_required']
    assert not any(n['artifact_id'] for n in graph['nodes'])
    graph = client.get(f'/pipeline/{CASE}/graph.json?run_id=bo-recorded').json()
    nodes = {n['id']: n for n in graph['nodes']}
    assert nodes['agent.m1_revenue_quality']['label'] == 'M1S1 Pricing Power'
    assert nodes['agent.m1_customer_stickiness']['label'] == 'M1S2 Demand Defensiveness'
    assert nodes['agent.m1_pricing_power']['label'] == 'M1S3 Customer Stickiness'
    assert {'agent.m4_strategy_capital','agent.m4_debt_structure'} <= nodes.keys()
    assert nodes['synthesis_v2']['illustration'] and nodes['synthesis_v2']['artifact_id'] is None
    assert not any(n.get('artifact_id', '').endswith('fo-recorded') for n in nodes.values() if n.get('artifact_id'))
    assert client.get(f'/pipeline/{CASE}/graph.json?run_id=missing').status_code == 404
    assert all(e['kind'] in {'recorded', 'architecture'} for e in graph['edges'])
    assert any(e['kind'] == 'recorded' and e['source'] == 'agent.m1_revenue_quality'
               and e['target'] == 'agent.m2_industry' for e in graph['edges'])


@pytest.mark.parametrize('aid,expected', [
    ('bo.agent.m1_revenue_quality.bo-recorded', 'Analytical findings'),
    ('bo.agent.m2_industry.bo-recorded', 'Supporting measures and factors'),
    ('bo.m4_debt.bo-recorded', 'Debt schedules and creditor priority'),
    ('bo.validator8_debt.bo-recorded', 'Checks performed'),
    ('fo.overview.fo-recorded', 'Financial measures and calculations'),
    (MANAGEMENT_ID, 'Management credit assessment'),
    (STRUCTURE_ID, 'Corporate structure and entity relationships'),
    ('rms.assessment.rms-recorded', 'Gate warnings and recorded waivers'),
])
def test_stage_reports_have_substantive_sections_and_three_tabs(recorded, aid, expected):
    _, client = recorded
    report = client.get(url(aid, '/report.html'))
    assert report.status_code == 200, report.text
    assert expected in report.text
    for tab in ['Report', 'Evidence &amp; Audit', 'Raw JSON']:
        assert tab in report.text
    assert 'memo-title:28px' in report.text  # shared memo typography
    assert 'Original download preserves recorded file bytes' in report.text


def test_m3_diagram_and_simulation_provenance_are_visible(recorded):
    _, client = recorded
    report = client.get(url(STRUCTURE_ID, '/report.html')).text
    assert '<svg' in report
    assert 'simulat' in report.lower()
    graph = client.get(f'/pipeline/{CASE}/graph.json?run_id=run_fixture').json()
    m3 = [n for n in graph['nodes'] if n['group'] == 'M3']
    assert len(m3) == 2 and all(n['artifact_id'] for n in m3)


def test_execution_validation_and_governance_are_independent(recorded):
    _, client = recorded
    ch = client.get(url('bo.challenger.bo-recorded')).json()
    assert ch['states']['execution'] == 'completed'
    assert ch['states']['validation'] == 'failed'
    handoff = client.get(url('bo.handoff.bo-recorded')).json()
    assert handoff['states']['governance'] == 'pending'
    assert 'Concentration risk is unresolved.' in client.get(url('bo.challenger.bo-recorded', '/report.html')).text
    fo = client.get(url('fo.overview.fo-recorded')).json()
    assert fo['states']['execution'] == 'completed'
    assert fo['states']['validation'] == 'unavailable'  # scoring is not validation


def test_evidence_excerpt_and_source_link_are_bound_to_the_selected_artifact(recorded):
    _, client = recorded
    report = client.get(url('bo.agent.m1_revenue_quality.bo-recorded', '/report.html')).text
    assert 'fixture-e1' in report and 'Fixture filing' in report
    assert 'Renewal rates reflect contractual reimbursement terms.' in report
    assert 'https://www.sec.gov/' in report
    assert 'Synthetic recorded viewer fixture' in report
    # A source ID may first occur as a short quote, then as a full source row.
    # Preserve both; do not discard document/page/excerpt metadata on deduplication.
    from app.services.registry.stage_report import presentation
    info=client.get(url('bo.agent.m1_revenue_quality.bo-recorded')).json()
    info['payload']['sources']=[{'evidence_id':'fixture-e1','filename':'Full fixture filing.pdf','page':19,'excerpt':'Full source context'}]
    source=next(e for e in presentation(info)['evidence'] if e['id']=='fixture-e1')
    assert any(r.get('page')==19 and r.get('excerpt')=='Full source context' for r in source['records'])


def test_rms_uses_recorded_sources_and_keeps_warning_waiver_provisional(recorded):
    _, client = recorded
    graph = client.get(f'/pipeline/{CASE}/graph.json?run_id=rms-recorded').json()
    aids = {n['artifact_id'] for n in graph['nodes'] if n['artifact_id']}
    assert {'rms.assessment.rms-recorded','bo.handoff.bo-recorded','fo.overview.fo-recorded'} <= aids
    report = client.get(url('rms.assessment.rms-recorded','/report.html')).text
    assert 'not final credit approval' in report
    assert 'Unresolved business challenge' in report
    assert 'Going concern accepted by human reviewer' in report
    assert 'Waived after human acceptance' in report
    assert 'bo_run=bo-recorded' in report and 'fo_run=fo-recorded' in report


@pytest.mark.parametrize('suffix', ['', '/report.html','/view.html','/original.json','/normalized.json','/download.json','/export.pdf'])
def test_m3_tampering_is_rejected_on_every_route(recorded, suffix):
    root, client = recorded
    manifest = json.loads(next((root/'m3_rebuild').rglob('m3_rebuild_manifest.json')).read_text())
    path = next((root/'m3_rebuild').rglob(manifest['components']['management']['artifact']))
    doc = json.loads(path.read_text()); doc['company'] = 'Tampered company'
    path.write_text(json.dumps(doc))
    response = client.get(url(MANAGEMENT_ID, suffix))
    assert response.status_code == 409
    assert 'integrity' in response.text.lower()


@pytest.mark.parametrize('suffix', ['', '/report.html','/view.html','/original.json','/normalized.json','/download.json','/export.pdf'])
def test_exact_source_bytes_pin_rejects_later_changes(recorded, suffix):
    root, client = recorded
    aid = 'fo.overview.fo-recorded'
    info = client.get(url(aid)).json()
    path = root/'fo'/CASE/'fo-recorded'/'financial_overview.json'
    path.write_bytes(path.read_bytes() + b'\n')  # semantic JSON identical, bytes differ
    assert client.get(url(aid, suffix), params={'expected_source_hash':info['source_file_sha256']}).status_code == 409


def test_exact_slice_pin_and_unknown_run_do_not_fall_back(recorded):
    root, client = recorded
    aid = 'bo.agent.m1_revenue_quality.bo-recorded'
    info = client.get(url(aid)).json()
    path = root/'bo'/CASE/'bo-recorded'/'audit_report.json'
    doc = json.loads(path.read_text()); doc['hypotheses']['records'][0]['claim'] = 'Changed'
    path.write_text(json.dumps(doc))
    assert client.get(url(aid, '/report.html'), params={'expected_hash':info['canonical_content_hash']}).status_code == 409
    assert client.get(url('bo.agent.m1_revenue_quality.another-run')).status_code == 404


def test_corrupt_wrong_case_missing_partial_and_historical_outputs(recorded):
    root, client = recorded
    path = root/'fo'/CASE/'fo-recorded'/'financial_overview.json'
    doc = json.loads(path.read_text())
    path.write_text('{corrupt')
    assert client.get(url('fo.overview.fo-recorded','/report.html')).status_code == 409
    doc['case_id'] = 'wrong-case'; path.write_text(json.dumps(doc))
    assert client.get(url('fo.overview.fo-recorded','/report.html')).status_code == 409
    del doc['case_id']; doc.pop('composite'); path.write_text(json.dumps(doc))
    info = client.get(url('fo.overview.fo-recorded')).json()
    assert info['states']['completeness'] == 'partial'
    missing = client.get(url('fo.precheck_transcript.fo-recorded','/report.html'))
    assert missing.status_code == 200 and 'Output unavailable' in missing.text
    # An archived unknown schema stays inspectable without inventing a renderer.
    path = root/'bo'/CASE/'historical'/'audit_report.json'; path.parent.mkdir()
    path.write_text(json.dumps({'schema_version':'archived-0.1','old_result':'Historical recorded result'}))
    old = client.get(url('bo.audit.historical','/report.html'))
    assert old.status_code == 200 and 'Generic presentation' in old.text
    assert 'Historical recorded result' in old.text


def test_rms_source_hash_mismatch_is_rejected(recorded):
    root, client = recorded
    path = root/'rms'/CASE/'rms-recorded'/'rms.json'
    doc = json.loads(path.read_text()); doc['sources']['fo_content_hash'] = '0'*64
    path.write_text(json.dumps(doc))
    assert client.get(url('rms.assessment.rms-recorded','/report.html')).status_code == 409


def test_opening_every_view_is_read_only_and_preserves_original_bytes(recorded, db_session, monkeypatch):
    root, client = recorded
    before = digests(root)
    writes = []
    def observe(conn, cursor, statement, *args):
        if statement.lstrip().split(' ',1)[0].upper() in {'INSERT','UPDATE','DELETE','CREATE','DROP','ALTER'}:
            writes.append(statement)
    event.listen(db_session.bind, 'before_cursor_execute', observe)
    def forbidden(*args, **kwargs): raise AssertionError('Viewer must never execute analytics or models.')
    monkeypatch.setattr('app.services.bo.runner.BusinessOverviewRunner.run_prepared', forbidden)
    monkeypatch.setattr('app.services.rms.runner.assess_case', forbidden)
    monkeypatch.setattr('app.services.fo.runner.composite_for', forbidden)
    monkeypatch.setattr('app.api.deps._session_factory', forbidden)
    monkeypatch.setattr('app.services.bo.offline.ScriptedBoBackend.generate', forbidden)
    monkeypatch.setattr('app.services.llm.providers.RealProviderBackend.generate', forbidden)
    aid = 'fo.overview.fo-recorded'
    for suffix in ['', '/report.html','/view.html','/original.json','/normalized.json','/download.json','/export.pdf']:
        assert client.get(url(aid,suffix)).status_code == 200
    for aid in [MANAGEMENT_ID, STRUCTURE_ID,'bo.m4_debt.bo-recorded','rms.assessment.rms-recorded']:
        assert client.get(url(aid,'/report.html')).status_code == 200
    original = client.get(url('fo.overview.fo-recorded','/original.json'))
    path = root/'fo'/CASE/'fo-recorded'/'financial_overview.json'
    assert original.content == path.read_bytes()
    assert original.headers['x-original-sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert client.post(url('fo.overview.fo-recorded','/report.html')).status_code == 405
    assert digests(root) == before and not writes
    event.remove(db_session.bind, 'before_cursor_execute', observe)


def test_artifact_text_is_escaped_and_unsafe_sources_are_not_linked(recorded):
    root, client = recorded
    path=root/'bo'/CASE/'bo-recorded'/'audit_report.json'
    doc=json.loads(path.read_text())
    doc['hypotheses']['records'][0]['claim']='<script>alert(1)</script>'
    doc['evidence_packets'][0]['items'][0]['source_url']='javascript:alert(1)'
    path.write_text(json.dumps(doc))
    report=client.get(url('bo.agent.m1_revenue_quality.bo-recorded','/report.html')).text
    assert '<script>alert(1)</script>' not in report
    assert 'href="javascript:' not in report
    assert '&lt;script&gt;' in report


def test_skipped_and_running_failed_execution_are_preserved(recorded):
    root, client = recorded
    path = root/'bo'/CASE/'bo-recorded'/'audit_report.json'
    doc = json.loads(path.read_text())
    doc['agents'][0]['status'] = 'skipped'
    doc['agents'][1]['status'] = 'running'
    doc['agents'][2]['runs'][0]['error_state'] = 'provider_timeout'
    path.write_text(json.dumps(doc))
    skipped = client.get(url('bo.agent.m1_revenue_quality.bo-recorded','/report.html'))
    assert skipped.status_code == 200 and 'Output unavailable' in skipped.text
    graph = client.get(f'/pipeline/{CASE}/graph.json?run_id=bo-recorded').json()
    nodes = {n['id']: n for n in graph['nodes']}
    assert nodes['agent.m2_industry']['states']['execution'] == 'running'
    assert nodes['agent.m4_strategy_capital']['states']['execution'] == 'failed'


def test_review_rejection_acceptance_and_acknowledgement_are_recorded(recorded):
    root, client = recorded
    path = root/'bo'/CASE/'bo-recorded'/'handoff.json'
    doc = json.loads(path.read_text())
    for decision in ['rejected','accepted']:
        doc['human_review_status'] = decision
        doc['reviewer'] = 'Recorded reviewer'
        doc['review_reason'] = 'Unresolved challenge acknowledged explicitly.'
        path.write_text(json.dumps(doc))
        info = client.get(url('bo.handoff.bo-recorded')).json()
        assert info['states']['governance'] == decision
        report = client.get(url('bo.handoff.bo-recorded','/report.html')).text
        assert 'Unresolved challenge acknowledged explicitly.' in report
        assert 'Recorded reviewer' in report


def test_corrupt_m3_manifest_has_explicit_graph_error(recorded):
    root, client = recorded
    manifest = next((root/'m3_rebuild').rglob('m3_rebuild_manifest.json'))
    manifest.write_text('{corrupt')
    graph = client.get(f'/pipeline/{CASE}/graph.json?run_id=run_fixture')
    assert graph.status_code == 200
    entry = next(n for n in graph.json()['nodes'] if n.get('artifact_id') == 'm3.manifest.run_fixture')
    assert entry['status'] == 'error' and 'corrupt' in entry['status_reason']
    assert client.get(url('m3.manifest.run_fixture','/report.html')).status_code == 409


def test_final_memo_preserves_recorded_source_binding_and_content_hash(recorded):
    from app.schemas.bo_four_section import FILENAME
    root, client = recorded
    docs = Path(__file__).parents[2]/'docs'/'simplified-business-overview-v1'
    bundle = json.loads((docs/'four-section.sample-sources.v1.json').read_text())['samples']['populated']
    memo = json.loads((docs/bundle['memo_file']).read_text())
    identity = memo['identity']; case, run = identity['case_id'], identity['analysis_run_id']
    target = root/'bo'/case/run; target.mkdir(parents=True)
    shutil.copyfile(docs/bundle['memo_file'], target/FILENAME)
    audit = bundle['verified_saved_inputs']['audit']
    (target/'audit_report.json').write_text(json.dumps(audit))
    base=f'/pipeline/{case}/node/bo.four_section.{run}'
    report = client.get(base+'/report.html')
    assert report.status_code == 200 and 'Memo sections' in report.text
    assert f'/cases/{case}/bo/runs/{run}/memo.html' in report.text
    audit['changed_after_recording'] = True
    (target/'audit_report.json').write_text(json.dumps(audit))
    for suffix in ['/report.html','/original.json','/normalized.json']:
        response=client.get(base+suffix)
        assert response.status_code == 409 and 'binding' in response.text


def test_memo_does_not_stand_in_for_missing_synthesis(recorded):
    root, client = recorded
    path = root/'bo'/CASE/'bo-recorded'/'audit_report.json'
    doc = json.loads(path.read_text())
    doc['agents'] = [a for a in doc['agents'] if a['agent_id'] != 'business_orchestrator']
    path.write_text(json.dumps(doc))
    graph=client.get(f'/pipeline/{CASE}/graph.json?run_id=bo-recorded').json()
    synthesis=next(n for n in graph['nodes'] if n['id']=='synthesis_v1')
    assert synthesis['artifact_id'] is None and synthesis['illustration']
    assert any(n.get('artifact_id')=='bo.memo.bo-recorded' for n in graph['nodes'])
