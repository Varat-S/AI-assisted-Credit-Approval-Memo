"""Read-only progressive disclosure over the exact saved run."""
from copy import deepcopy
from decimal import Decimal
import pytest
from lxml import html
from app.services.bo.memo_presentation import amount,classification,audit_url,notice,PRIORITY_LABELS
from app.services.bo.consolidated import load
from app.services.bo.reporting import render_consolidated_html
from tests.fixtures.bo_editorial import build_run
from tests.integration.test_analysis_workspace import evidence,workspace

@pytest.mark.parametrize('raw,expected',[(2207.0,'2,207.0'),(-436.0,'-436.0'),('1234.4500','1,234.4500'),(Decimal('-0.000100'),'-0.000100'),(0.0,'0.0'),(None,'Not recorded')])
def test_amount_fidelity(raw,expected):assert amount(raw)==expected

@pytest.mark.parametrize('code,label',list(PRIORITY_LABELS.items()))
def test_documented_priority_mapping(code,label):assert classification(code,'priority')==label

def test_safe_labels():
    assert classification('unsecured','security')=='Unsecured'
    assert classification('Unsecured','security')=='Unsecured'
    assert classification('unknown_rank','priority')=='Ranking not recognised — see details'
    assert classification(None,'priority')=='Not recorded'
    assert notice('quote_does_not_cover_claim: Evidence remains qualified.')=='Evidence remains qualified.'
    assert notice('Material conflict: Keep this qualification.')=='Material conflict: Keep this qualification.'


def default_tree(page):
    tree=html.fromstring(page)
    for el in tree.xpath('//script|//style|//*[contains(@class,"bo-print-only")]'):el.drop_tree()
    for el in tree.xpath('//details[not(@open)]'):
        for child in list(el):
            if child.tag!='summary':el.remove(child)
    return tree


def test_default_and_expanded_layers(db_session,tmp_path):
    result,job,_=build_run(db_session,tmp_path)
    data=load(db_session,result.case_id,result.analysis_run_id,result.snapshot_version);before=deepcopy(data)
    page=html.fromstring(render_consolidated_html(data));visible=default_tree(render_consolidated_html(data))
    assert data==before
    text=visible.text_content()
    assert 'tier_2_senior_unsecured_guaranteed' not in text
    assert 'Information Gaps' not in text and 'Validator 7' not in text
    assert 'Unsecured' in text and 'Tier 2 · Senior unsecured, guaranteed' in text
    assert not visible.xpath('//blockquote')
    assert not page.xpath('//details[@open]')
    rows=page.xpath('//tr[@class="bo-debt-row"]');details=page.xpath('//details[contains(@class,"bo-debt-details")]')
    debt=data['sections'][0]['items'][1]['content']
    records=[r for key in sorted(debt) if key in ('senior_notes_schedule','non_note_obligations_schedule','reconciling_items') for r in debt[key]]
    assert len(rows)==len(details)==len(records)==10
    for row,detail,record in zip(rows,details,records):
        # Every value is represented once in either the summary or expanded detail.
        for key,val in record.items():
            if val is None:continue
            expected=amount(val) if key.endswith('_m') else str(val)
            assert expected in (row.text_content()+detail.text_content()),(key,expected)
        assert 'Facility limit ($M), not outstanding debt' in detail.text_content() if 'available_facility_limit_m' in record else True
        assert 'aria-label' in detail.find('summary').attrib
    for p in data['sections'][2]['synthesis']['key_drivers']:
        assert all(paragraph in text for paragraph in p['analysis'].values())
        assert p['uncertainty'] in text
        block=page.get_element_by_id('bo-point-'+p['claim_id'])
        assert block.xpath('.//details/summary[text()="Supporting evidence"]')
    expanded=html.fromstring(render_consolidated_html(data,expand_evidence=True))
    printable=expanded.xpath('//details[contains(@class,"bo-print-expand")]')
    assert printable and all('open' in d.attrib for d in printable)
    assert data==before
    # Optional analytical qualifications remain visible, including historical layouts.
    qualified=deepcopy(data)
    qualified['sections'][2]['synthesis']['coverage_gaps']=['Coverage remains incomplete for this named market.']
    qualified['sections'][2]['synthesis']['overall_assessment']['analysis']={
        'company_evidence':'Recorded overall evidence.',
        'revenue_or_cost_mechanism':'Recorded overall mechanism.',
        'competitive_and_credit_implication':'Recorded overall credit implication.'}
    text=default_tree(render_consolidated_html(qualified)).text_content()
    assert 'Coverage remains incomplete for this named market.' in text
    assert 'Recorded overall credit implication.' in text
    d4=next(i['content'] for i in data['sections'][3]['items'] if i['field_path'][-1]=='deliverable_4')
    for finding in d4.get('strategy_capital_supplement',{}).get('findings',[]):
        assert finding['claim'] in text


def test_audit_links_bound_to_case_run():
    bo={'analysis_run_id':'run-one','case_id':'case'}
    job={'job_id':'job-one','case_id':'case','run_ids':{'bo':'run-one'}}
    assert audit_url(bo,job,'evidence').startswith('/analysis/job-one/audit#evidence-')
    assert audit_url(bo,{**job,'run_ids':{'bo':'other'}})=='/cases/case/bo/runs/run-one/audit.html'
    assert audit_url(bo)=='/cases/case/bo/runs/run-one/audit.html'


def test_filings_flow_is_secondary_and_collapsed(workspace):
    page=html.fromstring(workspace.get('/analysis/new').text)
    drawer=page.xpath('//details[contains(@class,"manage-filings")]')[0]
    assert 'open' not in drawer.attrib
    assert drawer.xpath('.//form[@action="/analysis/new/import"]//input[@type="file"]')
    assert drawer.xpath('.//form[@action="/analysis/new/reports#add-evidence"]')
    page=html.fromstring(workspace.get('/analysis/new?manage_filings=1').text)
    assert page.xpath('//details[contains(@class,"manage-filings")][@open]')
    page=html.fromstring(workspace.get('/credit-memos').text)
    assert page.xpath('//a[contains(@href,"manage_filings=1")]')
    assert not page.xpath('//input[@type="file"]')


def test_pdf_route_expands_evidence_without_model_calls(db_session,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.api.deps import get_session
    from app.services.reporting import memo
    result,_,_=build_run(db_session,tmp_path)
    captured=[]
    monkeypatch.setattr(memo,'detect_pdf_backend',lambda:'weasyprint')
    def pdf(backend,page):captured.append(page);return b'%PDF-offline-render-contract'
    monkeypatch.setattr(memo,'_render_pdf_with',pdf)
    app=create_app();app.dependency_overrides[get_session]=lambda:db_session
    with TestClient(app) as client:
        response=client.get(f'/cases/{result.case_id}/bo/runs/{result.analysis_run_id}/memo.pdf')
    assert response.status_code==200
    doc=html.fromstring(captured[0])
    assert all('open' in el.attrib for el in doc.xpath('//details[contains(@class,"bo-print-expand")]'))
    assert 'afterprint' in captured[0] and 'beforeprint' in captured[0]
    assert doc.xpath('//blockquote')
    assert result.analysis_run_id in doc.text_content()
