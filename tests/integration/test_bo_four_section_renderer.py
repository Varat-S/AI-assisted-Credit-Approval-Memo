"""Saved four-section presentation: real frozen runs, no models on reads."""
from copy import deepcopy
import json
import os
from pathlib import Path

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


def test_management_web_and_print_share_conservative_projection(db_session, tmp_path):
    result, _ = run(db_session, tmp_path)
    view = load_view(db_session, result.analysis_run_id)
    web = html.fromstring(render_page(view))
    printed = html.fromstring(render_page(view, pdf=True))
    web_management = web.xpath('//*[@data-memo-section="management"]')
    print_management = printed.xpath('//*[@data-memo-section="management"]')
    assert len(web_management) == len(print_management) == 1
    assert len(web_management[0].xpath('.//section[contains(@class,"bo-management-card")]')) == 1
    assert not web_management[0].xpath('.//div[@class="bo-management-assessment-gaps"]//li')
    assert not print_management[0].xpath('.//section[contains(@class,"bo-management-card")]')
    assert not print_management[0].xpath('.//div[@class="bo-management-assessment-gaps"]//li')
    assert web_management[0].xpath('.//details[contains(@class,"bo-management-support") and not(@open)]')
    assert not print_management[0].xpath('.//details[contains(@class,"bo-management-support")]')
    assert view['management']['overall_assessment']['text'] in web_management[0].text_content()
    assert view['management']['overall_assessment']['text'] in print_management[0].text_content()
    for finding in view['management']['key_strengths'] + view['management']['key_concerns']:
        assert finding['text'] in print_management[0].text_content()
    assert 'Appointment:' not in print_management[0].text_content()
    assert 'Recorded tenure:' not in print_management[0].text_content()
    assert not print_management[0].xpath('.//*[@data-source-id]')  # the PDF carries results, not evidence
    assert 'Sources' not in [h.text_content() for h in print_management[0].xpath('.//h4')]
    assert not web_management[0].xpath('.//a[starts-with(@href,"#bo-management-citation-")]')
    assert not web_management[0].xpath('.//*[@class="bo-management-sources"]')
    panels = web_management[0].xpath('.//div[contains(@class,"bo-management-finding")]/details[@class="bo-evidence"]')
    assert len(panels) == sum(len(g['findings']) for g in view['management']['finding_groups'])
    assert panels
    for panel in panels:
        assert panel.get('open') is None
        assert panel.xpath('.//article[@class="bo-source-quotation"]/blockquote')
        assert panel.xpath('.//dl[@class="bo-evidence-assessment"]')
        assert panel.xpath('.//details[@class="bo-evidence-technical"]')
    assert 'Passage offset' not in visible(web_management[0])
    for group in view['management']['finding_groups']:
        for finding in group['findings']:
            panel = finding['evidence']
            assert panel in view['evidence']
            selected = {view['management']['citations'][cid]['quote'] for cid in finding['citation_ids']}
            assert {q['quote'] for q in panel['quotations']} <= selected
    assert 'Areas Requiring Further Assessment' not in print_management[0].text_content()
    preview_dir = os.environ.get('BO_M3_PREVIEW_DIR')
    if preview_dir:
        folder = Path(preview_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'management_web_preview.html').write_text(render_page(view), encoding='utf-8')
        (folder / 'management_print_preview.html').write_text(render_page(view, pdf=True), encoding='utf-8')


def test_concerns_remain_visible_and_qualifications_stay_in_web_support(db_session, tmp_path):
    from app.services.bo.management_view import management_view

    result, _ = run(db_session, tmp_path)
    frozen = deepcopy(bo_artifact(db_session, result.analysis_run_id, 'four_section'))
    stage_bytes = [(r.name, r.sha256, r.payload_json) for r in db_session.query(StageArtifact).all()]
    view = load_view(db_session, result.analysis_run_id)
    artifact = deepcopy(frozen['sections'][1]['content'])
    observation = deepcopy(artifact['observations'][0])
    observation.update(observation_id='unclassified-reviewed', category='unclassified',
                       direction='negative', review_outcome='qualified',
                       text='Recorded concern without a reliable category.',
                       review_reason='Scope remains limited.', uncertainties=['Outcome evidence is unavailable.'])
    artifact['observations'] = [observation]
    artifact['validation']['validator_7']['overall']['limitations'] = ['Recorded overall qualification.']
    view['management'] = management_view(artifact)
    web = html.fromstring(render_page(view))
    printed = html.fromstring(render_page(view, pdf=True))
    section = web.xpath('//*[@data-memo-section="management"]')[0]
    other = section.xpath('.//details[@class="bo-management-other"]')[0]
    assert other.get('open') is not None  # Negative findings are visible by default.
    assert 'Other Reviewed Observations' in other.text_content()
    assert not section.xpath('.//section[@class="bo-management-card"]')
    assert not section.xpath('.//div[@class="bo-management-assessment-gaps"]//li')
    for page in (web, printed):
        assert observation['text'] in page.text_content()
        assert 'Recorded overall qualification.' not in visible(page)
        assert observation['review_reason'] not in visible(page)
        assert observation['uncertainties'][0] not in visible(page)
    support = section.xpath('.//details[@class="bo-management-support" and not(@open)]')[0]
    for text in (observation['review_reason'], observation['uncertainties'][0], 'Recorded overall qualification.'):
        assert text in support.text_content()
    assert not printed.xpath('//*[@data-memo-section="management"]//*[@data-source-id]')
    assert bo_artifact(db_session, result.analysis_run_id, 'four_section') == frozen
    assert [(r.name, r.sha256, r.payload_json) for r in db_session.query(StageArtifact).all()] == stage_bytes


def test_direction_groups_stay_visible_and_caveats_are_out_of_primary_memo():
    from app.services.bo.four_section_view import _env
    from app.services.bo.management_view import management_view

    observations = [dict(observation_id=str(i), category='continuity', direction=direction,
                         review_outcome=status, text=f'Exact reviewed statement {i}.',
                         review_reason='Material scope limitation.', uncertainties=['Performance remains unverified.'],
                         citation_ids=['c1']) for i, (direction, status) in enumerate([
                             ('positive', 'qualified'), ('negative', 'qualified'), ('mixed', 'qualified'),
                             ('neutral', 'accepted'), (None, 'qualified'), ('positive', 'unsupported')])]
    artifact = {'company': 'Recorded Company', 'source': {'path': 'sec-inline-xbrl:d1'},
                'overall_assessment': {'policy': 'Recorded overall statement.', 'outcome': 'mixed', 'information_gaps': True},
                'citations': [{'citation_id': 'c1', 'document_id': 'd1', 'source_id': 'a'*64,
                               'source_sha256': 'h', 'physical_page': 1, 'passage_offset': 600}],
                'observations': observations}
    view = management_view(artifact, documents={'d1': {'document_id': 'd1', 'sha256': 'h', 'filename': 'filing.htm',
                                                     'parser': 'inline_xbrl', 'form': '10-K', 'report_date': '2025-12-31'}})
    for pdf in (False, True):
        page = html.fromstring(_env.get_template('bo_management.html.j2').render(
            bo4={'management': view, 'memo': {'identity': {'analysis_run_id': 'recorded-run'}}}, pdf=pdf))
        shown = visible(page)
        assert 'Performance remains unverified.' in shown
        assert 'Material scope limitation.' not in shown
        assert 'Positive' in shown
        assert 'Supporting Factor' not in shown
        assert 'Areas Requiring Further Assessment' not in page.text_content()
        assert 'Limitations of Findings' in shown
        assert 'Negative' in shown
        assert 'Mixed' in shown and 'Unassessed' in page.text_content()
        assert 'Context · Qualified' not in shown
        assert page.xpath('//div[contains(@class,"bo-management-finding")]//span[contains(@class,"bo-type-inference")]')
        assert 'Recorded outcome:' not in shown
        assert 'Exact reviewed statement 5.' not in page.text_content()
        assert 'Passage offset 600' not in shown
        assert 'Page 1' not in shown and 'p. 1' not in shown
        assert 'a'*64 not in shown
    assert len(view['sources']) == 1


def test_saved_real_hca_run_renders_without_analysis_or_artifact_changes(monkeypatch):
    """Optional local recorded-run gate; never obtains a replacement from a model."""
    from hashlib import sha256
    from app.models.base import create_engine_and_session
    from app.models.orm import ModelRun
    from app.services.llm.providers_vertex import VertexProviderBackend
    from app.services.llm.providers import RealProviderBackend
    from app.services.pipeline.runner import CreditMemoPipeline

    folder = Path(__file__).parents[2] / 'output/hca_live_saved/20261103_management'
    if not (folder / 'case.db').exists():
        pytest.skip('Saved real HCA run is not installed; no live analysis is permitted in this test.')
    def forbidden(*args, **kwargs):
        pytest.fail('Saved HCA presentation must not invoke a model or re-ingest evidence.')
    monkeypatch.setattr(VertexProviderBackend, 'generate', forbidden)
    monkeypatch.setattr(RealProviderBackend, 'generate', forbidden)
    monkeypatch.setattr(CreditMemoPipeline, 'prepare_case', forbidden)
    manifest = json.loads((folder / 'saved_result_manifest.json').read_text(encoding='utf-8'))
    def unchanged():
        return all(sha256((folder / item['path']).read_bytes()).hexdigest() == item['sha256'] for item in manifest['files'])
    assert unchanged()
    engine, factory = create_engine_and_session('sqlite:///' + (folder / 'case.db').as_posix())
    try:
        with factory() as session:
            before = [(r.name, r.sha256, r.payload_json) for r in session.query(StageArtifact).all()]
            count = session.query(ModelRun).count()
            assert count == 14
            run_id = 'ar_70066e79dd954e3c'
            view = load_view(session, run_id, 'HCA_2025_M3_PRESENTATION_LIVE_20261103')
            web_text, print_text = render_page(view), render_page(view, pdf=True)
            web, printed = html.fromstring(web_text), html.fromstring(print_text)
            primary = printed.xpath('//*[@data-memo-section="management"]')[0]
            shown = primary.text_content()
            assert primary.xpath('.//*[@data-finding-group="supporting_factors"]//*[@data-review-status="qualified"]')
            assert not primary.xpath('.//*[@data-finding-group="credit_concerns"]')
            assert 'Reviewed assessment · Qualified' not in shown
            assert primary.xpath('.//*[contains(@class,"bo-badge-direction")]')
            assert view['management']['overall_assessment']['text'] in shown
            qualifier = 'Operational effectiveness depends on ongoing execution, which tenure alone does not guarantee.'
            assert qualifier not in shown
            assert 'Passage offset' not in shown
            assert 'f_01' not in shown and 'f_03' not in shown
            assert 'page 1' not in shown.lower() and 'p. 1' not in shown
            assert not __import__('re').search(r'\b[a-f0-9]{64}\b', shown)
            assert 'Appointment:' not in shown
            assert view['management']['pdf']['finding_count'] == 1
            assert view['management']['pdf']['eligible_excluded_by_categorization'] == 0
            assert len(primary.xpath('.//table[@class="bo-management-executive-table"]//tbody/tr')) == 7
            assert '1 distinct reviewed finding' in shown
            assert 'three to five distinct findings are not supported' in shown
            assert 'No management-specific monitoring indicators or thresholds were recorded.' in shown
            support = web.xpath('//details[@class="bo-management-support"]')[0]
            assert support.get('open') is None
            assert 'f_01' in support.text_content()  # Original rationale remains available.
            assert len(view['management']['sources']) == 3
            assert session.query(ModelRun).count() == count
            assert [(r.name, r.sha256, r.payload_json) for r in session.query(StageArtifact).all()] == before
            output = os.environ.get('BO_M3_HCA_PREVIEW_DIR')
            if output:
                target = Path(output)
                target.mkdir(parents=True, exist_ok=True)
                for name, text in [('web_full.html', web_text), ('print_full.html', print_text)]:
                    (target / name).write_text(text, encoding='utf-8')
                (target / 'verification.json').write_text(json.dumps({'run_id': run_id, 'new_model_calls': 0,
                    'frozen_stage_count': len(before), 'model_runs_before_and_after': count,
                    'canonical_files_verified': len(manifest['files']), 'canonical_files_unchanged': unchanged(),
                    'qualified_positive_group': 'supporting_factors', 'sources': view['management']['sources']}, indent=2), encoding='utf-8')
    finally:
        engine.dispose()
    assert unchanged()


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
        assert 'SIMULATED EDUCATIONAL EXAMPLE' not in shown
        assert not page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " notice-warning ")]')
        assert 'SIMULATED EDUCATIONAL EXAMPLE' in page.text_content()
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


def test_pdf_template_exports_all_results_without_evidence(db_session, tmp_path, monkeypatch):
    from app.api import analysis
    from app.services.reporting import memo as pdf_backend
    result, _ = run(db_session, tmp_path, missing='industry')
    view = analysis_workspace.load_review(db_session, job(result))
    printed = analysis._render_review(db_session, job(result), view, pdf=True)
    page = html.fromstring(printed)
    assert len(page.xpath('//*[@data-memo-section]')) == 4
    assert not page.xpath('//details')
    assert not page.xpath('//aside[@aria-label="Business Overview evidence appendix"]')
    assert not page.xpath('//*[contains(@class,"bo-evidence-body")]') and not page.xpath('//*[@data-source-id]')
    assert not page.xpath('//pre') and 'M1A6-H001' not in page.text_content()  # no raw evidence JSON
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
    assert len(captured) == 2 and not any('Business Overview evidence appendix' in x for x in captured)
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
    assert 'Material management coverage remains partial.' not in visible(page)
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
    assert 'Recorded component coverage remains partial.' not in visible(output)
    assert 'Recorded component coverage remains partial.' in block['visible_warnings']
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
        labels = view['four_section']['priority_columns'][:4]
        assert len(summary) == 4
        assert 'Structural subordination drag ratio' not in page.text_content()
        assert page.xpath('//section[@class="bo-loan-ranking"]')
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
    assert '@page{size:A4;margin:12mm 12mm 13mm;' in _render_review(db_session, legacy_job, legacy, pdf=True)


def test_pdf_omits_cross_dimensional_insights_but_screen_keeps_them(db_session, tmp_path):
    from app.api.analysis import _render_review
    result, _ = run(db_session, tmp_path)
    view = analysis_workspace.load_review(db_session, job(result))
    bo4 = view['four_section']
    def entry(claim, topic, text):
        e = deepcopy(claim)
        e['claim']['text'] = text
        return {**e, 'topic': topic, 'direction_label': 'Negative', 'source_hypothesis_id': text,
                'pointers': [{'label': 'Finding', 'parts': [{'text': text}], 'empty_text': ''}]}
    regular = entry(bo4['claims'][0], 'Pricing & reimbursement', 'REGULAR-FINDING')
    insight = entry(bo4['claims'][1], 'Cross-dimensional insight', 'CROSSDIM-FINDING')
    insight['evidence'] = {**insight['evidence'], 'title': 'Cross-dimensional insight'}
    bo4['finding_groups'] = [{'title': 'Revenue Drivers', 'entries': [regular]}, {'title': 'Cost Drivers', 'entries': []},
                             {'title': 'Revenue & Cost Interactions', 'entries': [insight]}]
    bo4['evidence'] = [x for x in bo4['evidence'] if x['id'] != insight['evidence']['id']] + [insight['evidence']]
    bo4['cross_dimensional'] = {insight['evidence']['id']}
    printed = _render_review(db_session, job(result), view, pdf=True)
    screen = _render_review(db_session, job(result), view)
    assert 'REGULAR-FINDING' in printed and 'CROSSDIM-FINDING' not in printed
    assert 'Revenue &amp; Cost Interactions' not in printed and 'Cross-dimensional insight' not in printed
    assert 'No selected findings were recorded in this category.' in printed
    assert 'CROSSDIM-FINDING' in screen and 'Revenue &amp; Cost Interactions' in screen
