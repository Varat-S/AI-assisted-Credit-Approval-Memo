"""Saved four-section presentation: real frozen runs, no models on reads."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from lxml import html

from app.api.deps import get_session
from app.core.hashing import content_hash
from app.main import create_app
from app.models.orm import StageArtifact
from app.prompts.competitive_positioning import OUTPUT_VERSION
from app.services import bo_fo, analysis_workspace
from app.services.bo.four_section_view import load_view, render_page
from app.services.bo.handoff import review_handoff
from app.services.bo.offline import ScriptedBoBackend
from app.services.bo.runner import BusinessOverviewRunner
from app.services.bo.workbench import bo_artifact
from app.services.pipeline.artifacts import ArtifactIntegrityError
from tests import competitive_positioning_helpers as cp, four_section_helpers as f, bo_helpers as h
from tests.m3_rebuild.review_fixtures import FixtureReviewerBackend


def run(session, path, *, missing=None):
    answers = cp.script()
    answers['m4_debt'] = f.debt_output()
    source = f.evidence()
    if missing == 'industry':
        answers['m2_industry'] = {'parameters': [], 'hypotheses': [], 'missing_information': ['Industry is unavailable.']}
    if missing == 'structure':
        source = source.model_copy(update={'structured_evidence': []})
    if missing == 'management':
        source = source.model_copy(update={'narrative_evidence': [p for p in source.narrative_evidence
            if (p.get('document_id') if isinstance(p, dict) else p.document_id) != 'mgmt-doc']})
    if missing == 'debt':
        answers['m4_debt'] = {'invalid': 'Offline missing debt assessment'}
    if missing == 'competitive':
        answers['orchestrate'] = {'invalid': 'Offline unavailable writer'}
    backend = ScriptedBoBackend(answers)
    runner = BusinessOverviewRunner(session, backend=backend, bo_roster='v3', sector=None,
        business_orchestrator_contract=OUTPUT_VERSION, enable_m4_debt_specialist=True,
        m3_extractor=f.ManagementExtractor(), m3_reviewer_backend=FixtureReviewerBackend(),
        data_root=path/'data', output_root=path/'out')
    runner.m3_config = {'corporate_source': 'corporate.json', 'management_source': 'management.pdf',
                        'company': f.COMPANY, 'filing_period': h.PERIOD, 'extraction': None}
    return runner.run_prepared(h.CASE, source, h.metrics(), write_outputs=True), backend


def job(result, name='saved'):
    return {'job_id': name, 'case_id': result.case_id, 'bo_only': True, 'bo_validators': True,
            'metadata': {'company': f.COMPANY, 'reporting_period': h.PERIOD}, 'folder': 'Offline fixture',
            'execution_status': 'completed', 'status': 'finished',
            'run_ids': {'bo': result.analysis_run_id}, 'created_at': '2026-11-02T00:00:00Z'}


def client_for(session, monkeypatch, jobs):
    class Records:
        def get(self, ident): return deepcopy(next((j for j in jobs if j['job_id'] == ident), None))
        def recent(self): return deepcopy(jobs)
    monkeypatch.setattr(bo_fo, 'jobs', Records())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def visible(page):
    root = deepcopy(page)
    for node in root.xpath('//details'):
        node.getparent().remove(node)
    return root.text_content()


def test_populated_review_routes_debt_and_closed_evidence(db_session, tmp_path, monkeypatch):
    result, backend = run(db_session, tmp_path)
    original = deepcopy(bo_artifact(db_session, result.analysis_run_id, 'four_section'))
    before = [(r.name, r.sha256, r.payload_json) for r in db_session.query(StageArtifact).all()]
    def forbidden(*args, **kwargs): pytest.fail('Rendering must not invoke analytical work')
    monkeypatch.setattr(backend, 'generate', forbidden)
    from app.services.bo import synthesis
    monkeypatch.setattr(synthesis, 'include_all_validated_findings', forbidden)
    with client_for(db_session, monkeypatch, [job(result)]) as client:
        response = client.get('/analysis/saved/review')
        assert response.status_code == 200, response.text
        page = html.fromstring(response.text)
        assert len(page.xpath('//*[@data-memo-section]')) == 4
        assert page.xpath('//details[contains(@class,"bo-structure-text") and not(@open)]/pre[@class="bo-tree"]')
        assert not page.xpath('//div[contains(@class,"bo-structure")]/pre[@class="bo-tree"]')
        assert [x.text_content().strip() for x in page.xpath('//*[@data-memo-section]/h2')] == [
            '01 Corporate Structure & Debt Obligations', '02 Management', '03 Competitive Positioning', '04 Industry']
        assert len(page.xpath('//*[@data-schedule="senior_notes"]//tbody/tr')) == 6
        assert len(page.xpath('//*[@data-schedule="non_note"]//tbody/tr')) == 4
        assert len(page.xpath('//*[@data-schedule="senior_notes"]//th')) == 8
        assert len(page.xpath('//*[@data-schedule="non_note"]//th')) == 9
        assert page.xpath('//svg')
        shown = visible(page)
        assert 'SIMULATED EDUCATIONAL EXAMPLE' in shown
        assert 'Tier 2 · Senior unsecured guaranteed' in shown
        assert 'Not recorded' in shown and '-436.0' in shown
        assert 'Admissions were stable during the year.' not in shown
        assert 'M1A6-H001' not in shown and 'M2-H001' not in shown and 'ev_payer' not in shown
        assert 'Our managed care contracts are generally multi-year agreements' not in shown
        assert page.xpath('//details') and not page.xpath('//details[@open]')
        assert all(d.get('data-run-id') == result.analysis_run_id for d in page.xpath('//details'))
        cp_content = original['sections'][2]['content']
        for claim in [cp_content['overall_assessment'], *cp_content['key_drivers'], *cp_content['material_risks']]:
            assert claim['text'] in shown
            if claim.get('uncertainty'): assert claim['uncertainty'] in shown
        base = f'/cases/{result.case_id}/bo/runs/{result.analysis_run_id}'
        assert client.get(base+'/memo.html').status_code == 200
        assert client.get(base+'/memo.json').json() == original
        assert client.get(base.replace(result.case_id, 'OTHER')+'/memo.html').status_code == 404
    assert bo_artifact(db_session, result.analysis_run_id, 'four_section') == original
    assert [(r.name, r.sha256, r.payload_json) for r in db_session.query(StageArtifact).all()] == before


@pytest.mark.parametrize('missing,section,component', [('industry',3,None), ('structure',0,'structure'),
    ('management',1,None), ('debt',0,'debt_obligations'), ('competitive',2,None)])
def test_missing_components_remain_independent(db_session, tmp_path, monkeypatch, missing, section, component):
    result, _ = run(db_session, tmp_path, missing=missing)
    canonical = bo_artifact(db_session, result.analysis_run_id, 'four_section')
    block = canonical['sections'][section]
    if component: block = block[component]
    assert block['status'] == 'unavailable', block
    with client_for(db_session, monkeypatch, [job(result)]) as client:
        response = client.get('/analysis/saved/review')
        assert response.status_code == 200, response.text
        page = html.fromstring(response.text)
        assert len(page.xpath('//*[@data-memo-section]')) == 4
        text = visible(page)
        assert 'Incomplete' in text and 'Current human review: Pending' in text
        if missing == 'industry': assert 'Industry analysis is not available in this version.' in text
        if missing != 'competitive': assert 'Multi-year managed-care agreements set negotiated rates.' in text
        if missing != 'debt': assert len(page.xpath('//*[@data-schedule="senior_notes"]//tbody/tr')) == 6
        if missing != 'structure': assert page.xpath('//svg')


def test_current_review_overlay_and_historical_selection(db_session, tmp_path, monkeypatch):
    first, _ = run(db_session, tmp_path/'one', missing='industry')
    second, _ = run(db_session, tmp_path/'two')
    original = deepcopy(bo_artifact(db_session, first.analysis_run_id, 'four_section'))
    review_handoff(db_session, first.handoff['handoff_id'], reviewer='Offline reviewer', reason='Offline review test',
                   decision='accept', acknowledge_unresolved=True)
    with client_for(db_session, monkeypatch, [job(first,'first'),job(second,'second')]) as client:
        a,b = client.get('/analysis/first/review'),client.get('/analysis/second/review')
        assert a.status_code == b.status_code == 200
        assert 'Current human review: <strong>Accepted</strong>' in a.text
        assert 'Current human review: <strong>Pending</strong>' in b.text
        assert 'Industry analysis is not available in this version.' in a.text
        assert 'Industry analysis is not available in this version.' not in b.text
        assert first.analysis_run_id in a.text and second.analysis_run_id not in a.text
        history = client.get('/credit-memos')
        assert '/analysis/first/review' in history.text and '/analysis/second/review' in history.text
    assert bo_artifact(db_session, first.analysis_run_id, 'four_section') == original
    assert original['governance']['human_review_status'] == 'pending'


def test_pdf_template_exports_all_content_and_evidence_appendix(db_session, tmp_path, monkeypatch):
    from app.api import analysis
    from app.services.reporting import memo as pdf_backend
    result, _ = run(db_session, tmp_path, missing='industry')
    view = analysis_workspace.load_review(db_session, job(result))
    printed = analysis._render_review(db_session, job(result), view, pdf=True)
    page = html.fromstring(printed)
    assert len(page.xpath('//*[@data-memo-section]')) == 4
    assert not page.xpath('//details')
    assert page.xpath('//aside[@aria-label="Business Overview evidence appendix"]')
    assert not page.xpath('//aside//pre') and 'M1A6-H001' not in page.text_content()  # no raw evidence JSON
    assert len(page.xpath('//*[@data-schedule="non_note"]//tbody/tr')) == 4
    captured = []
    monkeypatch.setattr(pdf_backend, 'detect_pdf_backend', lambda: 'weasyprint')
    def capture(backend, content):
        captured.append(content)
        return b'%PDF-offline-route-dispatch-proof'
    monkeypatch.setattr(pdf_backend, '_render_pdf_with', capture)
    with client_for(db_session, monkeypatch, [job(result)]) as client:
        assert client.get('/analysis/saved/memo.pdf').content.startswith(b'%PDF')
        assert client.get(f'/cases/{result.case_id}/bo/runs/{result.analysis_run_id}/memo.pdf').content.startswith(b'%PDF')
    assert len(captured) == 2 and all('Business Overview evidence appendix' in x for x in captured)
    assert all('Industry analysis is not available in this version.' in x for x in captured)


def test_invalid_binding_cannot_fallback_to_legacy(db_session, tmp_path):
    from app.models.orm import AcceptedBusinessOverviewRow
    from app.services.bo.reporting import handoff_content_hash
    result, _ = run(db_session, tmp_path)
    row = db_session.get(AcceptedBusinessOverviewRow, result.handoff['handoff_id'])
    payload = deepcopy(row.payload)
    payload['canonical_references']['four_section_memo']['content_hash'] = '0'*64
    payload['content_hash'] = handoff_content_hash(payload)
    row.payload, row.content_hash = payload, payload['content_hash']
    with pytest.raises(ArtifactIntegrityError): load_view(db_session, result.analysis_run_id)


def test_partial_display_escapes_text_and_withholds_unsupported_judgments(db_session, tmp_path):
    """Template-only defensive states; never persist modified presentation copies."""
    result, _ = run(db_session, tmp_path)
    original = bo_artifact(db_session, result.analysis_run_id, 'four_section')
    view = load_view(db_session, result.analysis_run_id)
    m = view['memo']['sections'][1]
    m['status'] = 'partial'
    m['visible_warnings'].append('Material management coverage remains partial.')
    m['content']['observations'].append({'review_outcome': 'unsupported', 'text': 'UNSUPPORTED JUDGMENT'})
    m['content']['profiles'][0]['name'] = '<script>alert("fixture")</script>'
    view['claims'][0]['claim']['text'] = '<img src=x onerror="alert(1)">'
    output = render_page(view)
    page = html.fromstring(output)
    assert 'UNSUPPORTED JUDGMENT' not in visible(page)
    assert 'Material management coverage remains partial.' in visible(page)
    assert 'data-status="partial"' in output
    assert not page.xpath('//script[not(@src) and contains(text(),"fixture")]')
    assert not page.xpath('//img[@onerror]')
    assert bo_artifact(db_session, result.analysis_run_id, 'four_section') == original


def test_new_renderer_retains_audit_and_review_controls(db_session, tmp_path, monkeypatch):
    result, _ = run(db_session, tmp_path)
    with client_for(db_session, monkeypatch, [job(result)]) as client:
        audit = client.get('/analysis/saved/audit')
        assert audit.status_code == 200, audit.text
        assert 'M1S2-H001' in audit.text  # deliberately omitted finding survives in Audit
        workbench = client.get(f'/cases/{result.case_id}/bo.html?analysis_run_id={result.analysis_run_id}&job=saved')
        assert workbench.status_code == 200, workbench.text
        assert f'/bo/runs/{result.analysis_run_id}/review' in workbench.text


@pytest.mark.parametrize('section,component', [(0,'structure'),(0,'debt_obligations'),(1,None),(2,None)])
def test_partial_template_states_preserve_supplied_content(db_session, tmp_path, section, component):
    result, _ = run(db_session, tmp_path)
    view = load_view(db_session, result.analysis_run_id)
    block = view['memo']['sections'][section]
    if component: block = block[component]
    before = deepcopy(block['content'])
    block['status'] = 'partial'
    block['visible_warnings'].append('Recorded component coverage remains partial.')
    output = html.fromstring(render_page(view))
    assert 'Recorded component coverage remains partial.' in visible(output)
    assert block['content'] == before
    assert len(output.xpath('//*[@data-memo-section]')) == 4
    assert len(output.xpath('//*[@data-schedule="senior_notes"]//tbody/tr')) == 6


def test_long_debt_display_records_are_not_truncated(db_session, tmp_path):
    result, _ = run(db_session, tmp_path)
    view = load_view(db_session, result.analysis_run_id)
    long_record = 'Recorded guarantee, security and legal support provisions. ' * 60
    debt = view['memo']['sections'][0]['debt_obligations']['content']
    debt['senior_notes_schedule'][0]['guarantors_credit_support'] = long_record
    page = html.fromstring(render_page(view))
    cells = page.xpath('//*[@data-schedule="senior_notes"]//tbody/tr[1]/td')
    assert cells[6].text_content() == long_record
    assert len(page.xpath('//*[@data-schedule="senior_notes"]//tbody/tr')) == 6


def test_portrait_print_summary_and_full_schedules_preserve_sources(db_session, tmp_path):
    from app.api.analysis import _render_review
    from tests.integration.test_analysis_review_workspace import seed_run
    result, _ = run(db_session, tmp_path)
    original = deepcopy(bo_artifact(db_session, result.analysis_run_id, 'four_section'))
    selected = job(result)
    view = analysis_workspace.load_review(db_session, selected)
    screen = html.fromstring(_render_review(db_session, selected, view))
    assert not screen.xpath('//*[@class="bo-debt-summary"]')
    printed = _render_review(db_session, selected, view, pdf=True)
    standalone = render_page(load_view(db_session, result.analysis_run_id), pdf=True)
    for output in (printed, standalone):
        assert '@page{size:A4;' in output and 'landscape' not in output
        page = html.fromstring(output)
        assert page.xpath('//*[@class="bo-structure"]/parent::*/*[@class="bo-debt-summary"]')
        assert page.xpath('//*[contains(@class,"bo-print-schedules")]')
        d1 = original['sections'][0]['debt_obligations']['content']
        summary = page.xpath('//table[contains(@class,"bo-debt-summary-table")]//tbody/tr')
        labels = view['four_section']['priority_columns'][:5]
        assert len(summary) == 5 + len(d1['reconciling_items'])
        for row, (field, label) in zip(summary, labels):
            assert row.findtext('th') == label
            assert row.findtext('td') == str(d1['creditor_priority_framework'][field])
        for schedule, source_key, columns in [('senior_notes','senior_notes_schedule','note_columns'),
                                               ('non_note','non_note_obligations_schedule','facility_columns')]:
            rows = page.xpath(f'//*[@data-schedule="{schedule}"]//tbody/tr')
            assert len(rows) == len(d1[source_key])
            for rendered, source in zip(rows, d1[source_key]):
                assert [cell.text_content() for cell in rendered.findall('td')] == [
                    str(view['four_section']['display'](source[field]))
                    for field, _ in view['four_section'][columns]]
    assert bo_artifact(db_session, result.analysis_run_id, 'four_section') == original
    legacy_job = seed_run(db_session, 'layout-legacy')
    legacy = analysis_workspace.load_review(db_session, legacy_job)
    assert '@page{size:A4;margin:16mm 14mm}' in _render_review(db_session, legacy_job, legacy, pdf=True)
