"""Milestone 1: setup-only UI, using tiny synthetic source fixtures and no AI calls."""
import json
from datetime import date, datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from lxml import html
from app.main import create_app
from app.api.deps import get_session
from app.api import analysis
from app.services import analysis_setup
from app.services.fo import loader
from app.services.acquisition.sec_edgar import write_bundle
from app.services.extraction.sec.bundle import SecFilingBundle
from tests.sec_helpers import filing_file


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    """A tiny metadata fixture; no financial analysis or memo is generated."""
    root = tmp_path / 'edgar_filings'
    folder = root / 'HCA 10-K FY2024'
    primary = filing_file(filename='hca-test.htm').model_copy(update={'cik':'860730'})
    schema = filing_file(filename='hca-test.xsd', role='schema', content=b'<schema/>').model_copy(update={'cik':'860730'})
    bundle = SecFilingBundle(cik='860730', ticker='HCA', accession=primary.accession,
                            form='10-K', report_date=date(2024,12,31),
                            filing_date=primary.filing_date, primary_document=primary.filename,
                            files=[primary,schema])
    write_bundle(bundle, folder)
    manifest = json.loads((folder/'bundle.json').read_text())
    for entry in manifest['files']:
        (folder/entry['path']).rename(folder/entry['filename'])
        entry['path'] = entry['filename']
    (folder/'bundle.json').write_text(json.dumps(manifest))
    package = {'as_of_date':'2024-12-31','evidence_cutoff_timestamp':'2025-03-31T23:59:59Z',
               'borrower_entity_id':'HCA','entities':[{'entity_id':'HCA','legal_name':'HCA setup fixture',
               'tickers':['HCA'],'entity_type':'borrower','borrower_flag':True,
               'expected_consolidation_scope':'consolidated'}], 'sources':[],
               'sec_bundles':[{'bundle':'bundle.json','entity_id':'HCA'}]}
    (folder/'package.json').write_text(json.dumps(package))
    monkeypatch.setattr(loader, 'FILINGS_ROOT', root)
    return folder


@pytest.fixture
def workspace(evidence, db_session, monkeypatch):
    from app.services import bo_fo
    from app.services.llm.providers_vertex import VertexProviderBackend
    from app.services.llm.providers import RealProviderBackend
    def forbidden(*args, **kwargs):
        pytest.fail('Setup must never start a job or generate a model response')
    monkeypatch.setattr(bo_fo.jobs, 'start', forbidden)
    monkeypatch.setattr(VertexProviderBackend, 'generate', forbidden)
    monkeypatch.setattr(RealProviderBackend, 'generate', forbidden)
    monkeypatch.setattr(analysis, 'provider_configuration', lambda sections: {
        'configured':True,'bo_configured':True,'fo_configured':True,
        'bo_reason':None,'fo_reason':None})
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client


def test_home_title_and_exactly_two_primary_options(workspace):
    page = html.fromstring(workspace.get('/').text)
    assert page.xpath('string(//h1)') == 'Credit Analysis Workspace'
    assert page.xpath('//nav[@aria-label="Primary navigation"]/a/@href') == ['/analysis/new','/credit-memos']
    assert page.xpath('//a/@href') == ['/analysis/new','/credit-memos']
    assert len(page.xpath('//svg[@aria-hidden="true"]')) == 2
    assert not page.xpath('//button')
    assert 'Run Analysis' not in page.text_content()


def test_new_analysis_hca_only_and_defaults(workspace):
    page = html.fromstring(workspace.get('/analysis/new').text)
    assert page.xpath('//select[@name="company"]/option/@value') == ['hca']
    assert page.xpath('//select[@name="company"]/option[@selected]/text()') == ['HCA Healthcare (HCA)']
    assert page.xpath('//input[@name="sections"][@checked]/@value') == ['both']
    assert page.xpath('//input[@name="validation_mode"][@checked]/@value') == ['standard']
    assert page.xpath('//ol/li[@aria-current="step"]/text()')[-1].strip() == 'Setup'
    assert len(page.xpath('//ol/li[@aria-disabled="true"]')) == 2
    assert not page.xpath('//button[@id="run-analysis"][@disabled]')
    assert not page.xpath('//details[@open]')
    assert 'Run Analysis starts paid AI processing' in page.text_content()


def test_source_metadata_and_correct_backend_map(workspace):
    page = workspace.get('/analysis/new').text
    for value in ['31 December 2024','10 January 2025','31 Mar 2025, 23:59:59','HCA 10-K FY2024','0000000001-25-000001']:
        assert value in page
    selection = analysis_setup.validate_setup()
    assert selection.backend_parameters() == {'folder':'HCA 10-K FY2024','case_id':'',
        'sections':'both','cutoff':'2025-03-31T23:59:59+00:00','bo_validators':'on'}


@pytest.mark.parametrize('sections', ['both','bo'])
@pytest.mark.parametrize('mode,flag', [('standard','on'),('exploratory','off')])
def test_scope_modes_map_only_bo_enforcement(workspace, sections, mode, flag):
    page = html.fromstring(workspace.get('/analysis/new',params={
        'sections':sections,'validation_mode':mode,'check':'1'}).text)
    assert page.xpath('//input[@name="sections"][@checked]/@value') == [sections]
    assert page.xpath('//input[@name="validation_mode"][@checked]/@value') == [mode]
    assert 'Configuration checked' in page.text_content()
    selection = analysis_setup.validate_setup(sections=sections,validation_mode=mode)
    params = selection.backend_parameters()
    assert params['sections'] == sections and params['bo_validators'] == flag
    assert not any(k.startswith('fo_') for k in params)
    if mode == 'exploratory':
        assert selection.approval_policy == 'ineligible_for_final_approval'
        assert not page.xpath('//*[@id="exploratory-note"][@hidden]')
        assert 'Not eligible for final approval' in page.text_content()
    else:
        assert selection.approval_policy == 'existing_review_and_approval_required'


def test_missing_evidence_clear_error_and_no_execution(workspace, evidence):
    (evidence/'hca-test.htm').unlink()
    response = workspace.get('/analysis/new')
    assert response.status_code == 200
    page = html.fromstring(response.text)
    assert 'required FY2024 evidence package is unavailable' in page.text_content()
    assert 'Evidence unavailable' in page.text_content()
    assert page.xpath('//button[@id="run-analysis"][@disabled]')
    with pytest.raises(analysis_setup.SetupError):
        analysis_setup.validate_setup()


def test_tampered_source_is_not_accepted(workspace, evidence):
    (evidence/'hca-test.htm').write_text('tampered test bytes')
    response = workspace.get('/analysis/new?check=1')
    assert response.status_code == 400 and 'unavailable' in response.text


def test_wrong_company_package_is_not_accepted(workspace, evidence):
    package = json.loads((evidence/'package.json').read_text())
    package['entities'][0]['tickers'] = ['OTHER']
    (evidence/'package.json').write_text(json.dumps(package))
    assert workspace.get('/analysis/new?check=1').status_code == 400


@pytest.mark.parametrize('query', [
    {'company':'other'}, {'sections':'specialists'}, {'validation_mode':'skip_everything'},
    {'cutoff':'2025-03-31'}, {'cutoff':'2024-01-01T00:00:00Z'}, {'case_id':'../escape'}])
def test_invalid_setup_values_are_visible(workspace, query):
    response = workspace.get('/analysis/new',params={**query,'check':'1'})
    assert response.status_code == 400
    assert html.fromstring(response.text).xpath('//*[@role="alert"]')
    assert html.fromstring(response.text).xpath('//button[@id="run-analysis"][@disabled]')


def test_advanced_selections_survive_query_navigation(workspace):
    response = workspace.get('/analysis/new',params={'sections':'bo','validation_mode':'exploratory',
        'case_id':'HCA_REVIEW','cutoff':'2025-03-01T10:00:00+00:00','check':'1'})
    page = html.fromstring(response.text)
    assert response.status_code == 200
    assert page.xpath('//input[@id="case_id"]/@value') == ['HCA_REVIEW']
    assert page.xpath('//input[@id="cutoff"]/@value') == ['2025-03-01T10:00:00+00:00']


def test_missing_provider_configuration_is_explained(workspace, monkeypatch):
    monkeypatch.setattr(analysis, 'provider_configuration', lambda sections: {
        'configured':False,'bo_configured':False,'fo_configured':False})
    page = workspace.get('/analysis/new').text
    assert 'Business Overview provider settings are unavailable' in page
    assert 'Financial Overview provider settings are unavailable' in page
    assert 'Provider configuration needed' in page


def test_no_run_created_and_no_new_launch_endpoint(workspace, db_session):
    from app.models.orm import AgenticAnalysisRun, Case, Snapshot
    for url in ['/', '/analysis/new', '/analysis/new?check=1&run=1', '/credit-memos']:
        assert workspace.get(url).status_code == 200
    assert workspace.post('/analysis/start',data={'company':'hca'}).status_code == 422
    assert workspace.post('/analysis/new').status_code == 405
    assert workspace.get('/analysis/job1/execution').status_code == 404
    for model in [AgenticAnalysisRun, Case, Snapshot]:
        assert db_session.query(model).count() == 0


def test_history_is_only_a_placeholder_and_legacy_routes_remain(workspace):
    page = workspace.get('/credit-memos').text
    assert 'Analysis history' in page
    for url in ['/run','/bo','/health','/docs']:
        assert workspace.get(url).status_code == 200
    assert workspace.get('/cases/unknown/workbench.html').status_code == 404


def test_bo_only_configuration_check_does_not_apply_to_fo(monkeypatch):
    from app.services import bo_fo
    from app.services.fo import precheck
    monkeypatch.setattr(bo_fo, 'bo_live_backend', lambda: None)
    monkeypatch.setattr(precheck,'agent_available',lambda: pytest.fail('FO is not selected'))
    assert analysis_setup.provider_configuration('bo')['configured'] is True
