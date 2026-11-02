"""Corrective visual contracts, depth, exact-run navigation; no live I/O."""
from copy import deepcopy
from pathlib import Path
import pytest
from lxml import html
from fastapi.testclient import TestClient
from app.schemas.bo_consolidated import CompetitiveSynthesis,TITLES
from app.services.bo.consolidated import load
from app.services.bo.reporting import render_consolidated_html
from tests.fixtures.bo_editorial import build_run


def test_rich_artifact_table_diagram_timeline_fidelity(db_session,tmp_path):
    result,job,backend=build_run(db_session,tmp_path)
    artifact=load(db_session,job['case_id'],result.analysis_run_id,result.snapshot_version)
    original=deepcopy(artifact)
    page=html.fromstring(render_consolidated_html(artifact))
    assert artifact==original
    assert page.xpath('//h2/text()')==list(TITLES)
    assert page.xpath('//img[contains(@src,"data:image/svg+xml;base64,")]')
    debt=next(i['content'] for i in artifact['sections'][0]['items'] if i['field_path'][-1]=='deliverable_1')
    assert len(page.xpath('//section[@id="bo-section-1"]//tbody/tr[@class="bo-debt-row"]'))==sum(len(debt.get(k,[])) for k in ['senior_notes_schedule','non_note_obligations_schedule','reconciling_items'])
    d2=artifact['sections'][3]['items'][0]['content']
    events=page.xpath('//li[@class="bo-event"]')
    assert len(events)==len(d2['refinancing_log'])>3
    for node,event in zip(events,d2['refinancing_log']):
        assert event['obligation_series_description'] in node.text_content()
        assert event['execution_date_fiscal_period'] in node.text_content()
        from app.services.bo.memo_presentation import amount
        assert amount(event['principal_amount_m']) in node.text_content()
    assert d2['refinancing_capacity_discipline_verdict'] in page.xpath('//div[@class="bo-conclusion"]')[0].text_content()
    selection=artifact['sections'][2]['synthesis']
    assert selection['schema_version']=='bo-competitive-1.1'
    for point in selection['key_drivers']:
        for paragraph in point['analysis'].values():assert paragraph in page.text_content()
        frozen=next(c for c in result.audit['conclusions'] if c['conclusion_id']==result.handoff['business_topic_conclusion_id'])
        stored=next(c for c in frozen['payload']['key_drivers'] if c['claim_id']==point['claim_id'])
        assert all(s in stored['text'] for s in point['analysis'].values())
    assert backend.calls('challenge')==1
    assert selection['selections'][-1]['disposition']=='audit_only'


def test_depth_is_required_for_new_contract_but_old_contract_reads():
    from pydantic import ValidationError
    from tests.integration.test_bo_consolidated import script
    data=script()['orchestrate']
    for p in [data['overall_assessment'],*data['key_drivers']]:p['evidence_ids']=['fixture-evidence']
    data['key_drivers'][0]['analysis']=None
    with pytest.raises(ValidationError):CompetitiveSynthesis.model_validate(data)
    data['schema_version']='bo-competitive-1.0'
    assert CompetitiveSynthesis.model_validate(data)


def test_persisted_history_and_new_completion_navigation(db_session,tmp_path,monkeypatch):
    from app.services import bo_fo
    from app.main import create_app
    from app.api.deps import get_session
    from app.services.analysis_jobs import JobStore
    from tests.integration.test_analysis_review_workspace import seed_run
    first,old,_=build_run(db_session,tmp_path/'old',tag='historical')
    second,new,_=build_run(db_session,tmp_path/'new',tag='newly-completed')
    store=JobStore(tmp_path/'jobs.sqlite')
    store.claim(old);store.claim(new)
    legacy=seed_run(db_session,'legacy',3)
    store.claim(legacy)
    db_session.commit()
    # Fresh manager resolves persisted sidecar rows: no process-local latest-run fallback.
    monkeypatch.setattr(bo_fo,'jobs',bo_fo.Jobs(tmp_path/'jobs.sqlite'))
    app=create_app();app.dependency_overrides[get_session]=lambda:db_session
    with TestClient(app) as client:
        for result,job in [(first,old),(second,new)]:
            execution=client.get('/analysis/'+job['job_id']+'/execution')
            assert execution.status_code==200
            assert '/review' in execution.text
            listing=html.fromstring(client.get('/credit-memos?search='+job['job_id']).text)
            href=listing.xpath('//article[@data-job-id="'+job['job_id']+'"]//h3/a/@href')[0]
            review=client.get(href)
            assert review.status_code==200
            assert result.analysis_run_id in review.text
            assert (second if result is first else first).analysis_run_id not in review.text
            assert html.fromstring(review.text).xpath('//h2/text()')==list(TITLES)
        legacy_page=client.get('/analysis/legacy/review')
        assert legacy_page.status_code==200 and 'no consolidated Business Overview artifact' in legacy_page.text

from tests.integration.test_analysis_workspace import evidence,workspace

def test_new_analysis_setup_execution_review_journey(workspace,db_session,tmp_path,monkeypatch):
    from app.api import analysis
    from app.services import bo_fo
    from tests.integration.test_analysis_execution import submit,wait_for
    from tests import bo_helpers as h
    monkeypatch.setattr(analysis,'execution_backends',lambda sections:(None,None,None))
    monkeypatch.setattr(bo_fo,'plan',lambda folder,case_id,cutoff:{'case_id':h.CASE,'cutoff':cutoff})
    jobs=bo_fo.Jobs(tmp_path/'submitted-jobs.sqlite')
    monkeypatch.setattr(bo_fo,'jobs',jobs)
    generated=[]
    def offline_worker(**kwargs):
        assert kwargs['consolidated'] is True
        result,_,_=build_run(db_session,tmp_path/'submitted-run',tag='submitted')
        db_session.commit();generated.append(result.analysis_run_id)
        return {'case_id':h.CASE,'bo':{'status':'completed','summary':{'analysis_run_id':result.analysis_run_id}},
                'fo':{'status':'skipped'},'rms':{'status':'skipped'}}
    monkeypatch.setattr(bo_fo,'run_bo_fo',offline_worker)
    assert workspace.get('/analysis/new').status_code==200
    response=submit(workspace,sections='bo')
    assert response.status_code==303,response.text
    execution_url=response.headers['location'];ident=execution_url.split('/')[2]
    wait_for(jobs,ident,'completed')
    assert workspace.get(execution_url).status_code==200
    review=workspace.get('/analysis/'+ident+'/review')
    assert review.status_code==200 and generated[0] in review.text
    assert html.fromstring(review.text).xpath('//h2/text()')==list(TITLES)


def test_unsupported_detail_is_checked_as_claim_text(db_session,tmp_path):
    from tests.integration.test_bo_consolidated import script,run
    data=script()
    data['orchestrate']['key_drivers'][0]['analysis']['company_evidence']='A fabricated 87654321 percent gain proves immunity.'
    result,_=run(db_session,tmp_path,answers=data)
    artifact=load(db_session,result.case_id,result.analysis_run_id,result.snapshot_version)
    assert artifact['sections'][2]['synthesis'] is None
    assert any('87654321' in str(x) for x in result.audit['orchestrator']['history'])
