"""Real New Analysis -> durable job -> source ingestion -> frozen memo -> website."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from fastapi.testclient import TestClient
from lxml import html
import pytest
from sqlalchemy import select, update

from app.api import analysis
from app.api.deps import get_session
from app.core.config import get_settings
from app.core.hashing import content_hash, canonical_json
from app.main import create_app
from app.models.base import create_engine_and_session, init_db
from app.models.orm import AcceptedBusinessOverviewRow, AgenticAnalysisRun, StageArtifact, FinancialOverviewRunRow
from app.prompts.source_selection import OUTPUT_VERSION, INPUT_VERSION, POLICY_VERSION
from app.services import bo_fo, analysis_workspace
from app.services.bo.four_section import load_saved_inputs, assemble
from app.services.bo.handoff import HandoffError, review_handoff
from app.services.bo.workbench import bo_artifact
from app.services.fo import loader
from app.services.pipeline.artifacts import verified_artifacts
from tests.business_overview_browser_helpers import source_folder, business_backend, ManagementBackend, FOLDER


def completed(jobs, ident):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        record = jobs.get(ident)
        if record['execution_status'] not in {'pending','running'} and record.get('finished_at'):
            return record
        time.sleep(.01)
    raise AssertionError(jobs.get(ident))


@pytest.fixture
def browser_env(tmp_path, monkeypatch):
    source = source_folder(tmp_path/'filings')
    monkeypatch.setattr(loader, 'FILINGS_ROOT', source.parent)
    database = tmp_path/'main.db'
    engine, factory = create_engine_and_session('sqlite:///' + str(database))
    init_db(engine)
    settings = get_settings()
    for key,value in [('database_url','sqlite:///' + str(database)),('data_dir',tmp_path/'data'),('output_dir',tmp_path/'out')]:
        monkeypatch.setattr(settings, key, value)
    jobs = bo_fo.Jobs(tmp_path/'jobs.sqlite')
    monkeypatch.setattr(bo_fo, 'jobs', jobs)
    backends = []
    def offline(sections):
        bo, m3 = business_backend(), ManagementBackend()
        backends.append((bo,m3))
        return bo,m3,None
    monkeypatch.setattr(analysis, 'execution_backends', offline)
    monkeypatch.setattr(analysis, 'provider_configuration', lambda sections: {
        'configured':True,'bo_configured':True,'fo_configured':True,'bo_reason':None,'fo_reason':None})
    def forbidden(*args, **kwargs): pytest.fail('Live provider used by offline browser acceptance')
    from app.services.llm.providers import RealProviderBackend
    from app.services.llm.providers_vertex import VertexProviderBackend
    monkeypatch.setattr(RealProviderBackend, 'generate', forbidden)
    monkeypatch.setattr(VertexProviderBackend, 'generate', forbidden)
    app = create_app()
    def session():
        with factory() as s: yield s
    app.dependency_overrides[get_session] = session
    with TestClient(app) as client:
        yield {'client':client,'jobs':jobs,'factory':factory,'database':database,'source':source,
               'backends':backends,'root':tmp_path}
    for record in jobs.recent():
        if record['execution_status'] in {'pending','running'}:
            jobs.stop(record['job_id']);completed(jobs,record['job_id'])
    engine.dispose()


def launch(env, *, mode='standard', token=None):
    response = env['client'].post('/analysis/start', data={
        'company':'nfh-10-k-fy2025','sections':'bo','validation_mode':mode,
        'case_id':'NFH_BROWSER','submission_key':token or uuid.uuid4().hex}, follow_redirects=False)
    assert response.status_code == 303, response.text
    ident = response.headers['location'].split('/')[2]
    record = completed(env['jobs'], ident)
    assert record['execution_status'] == 'completed', record
    return record


def test_actual_new_analysis_pipeline_history_and_exports(browser_env):
    env=browser_env;client=env['client']
    setup=client.get('/analysis/new?company=nfh-10-k-fy2025&sections=bo')
    assert setup.status_code == 200 and 'Run Analysis' in setup.text
    record=launch(env)
    ident=record['job_id'];rid=record['run_ids']['bo'];summary=record['result']['bo']['summary']
    assert record['business_overview_workflow'] == record['metadata']['business_overview_workflow'] == {
        'bo_roster':'v3','business_orchestrator_contract':OUTPUT_VERSION,'editorial_selection_policy':POLICY_VERSION}
    assert summary['business_orchestrator_contract'] == OUTPUT_VERSION
    assert 'Competitive Positioning' in record['stages']['bo:orchestrator']['label']
    backend,m3=env['backends'][0]
    assert backend.calls('orchestrate') == 1
    assert backend.calls('challenge') == 0
    assert 'bo:challenger' not in record['stages']
    assert record['sections']['bo']['work']['done']==record['sections']['bo']['work']['total']
    assert m3.calls == ['m3_management_assessment','m3_validator_7']
    methods=[method for method,_ in backend.requests]
    assert methods.index('m1_resilience_integration') > max(methods.index(a) for a in (
        'm1_revenue_quality','m1_customer_stickiness','m1_pricing_power','m1_operating_model','m1_competitive_durability'))
    assert methods.index('orchestrate') > methods.index('m1_resilience_integration')
    assert 'challenge' not in methods
    writer=next(packet for method,packet in backend.requests if method=='orchestrate')
    assert writer['schema_version']==INPUT_VERSION and 'module_conclusions' not in writer
    assert all(h['agent_id'].startswith('m1_') for h in writer['hypotheses'])
    with env['factory']() as session:
        memo=bo_artifact(session,rid,'four_section')
        saved=load_saved_inputs(session,rid)
        assert assemble(saved)==memo
        from app.services.bo.synthesis import iter_claims
        from app.services.bo.source_selection import project
        projected=project(saved.audit['orchestrator']['editorial_selection']['selection_plan'], writer)
        cp_content=memo['sections'][2]['content']
        assert [(c['claim_id'],c['text'],c['evidence_ids'],c['parameter_result_ids']) for _,c in iter_claims(projected)] == [
            (c['claim_id'],c['text'],c['evidence_ids'],c['parameter_result_ids']) for _,c in iter_claims(cp_content)]
        assert all(c['text']==next(h['claim'] for h in writer['hypotheses'] if h['hypothesis_id']==c['hypothesis_ids'][0])
                   for _,c in iter_claims(cp_content))
        assert memo['identity']['analysis_run_id']==rid and memo['identity']['case_id']==record['case_id']
        assert memo['identity']['evidence_snapshot_hash']==saved.snapshot_hash
        run=session.get(AgenticAnalysisRun,rid)
        assert run.model_configuration['business_orchestrator_contract']==OUTPUT_VERSION
        assert run.model_configuration['editorial_selection_policy']==POLICY_VERSION
        assert memo['sections'][0]['structure']['status']=='complete'
        assert memo['sections'][0]['debt_obligations']['status']=='complete'
        assert memo['sections'][1]['status']==memo['sections'][2]['status']=='complete'
        assert memo['sections'][3]['status']=='unavailable'
        assert memo['governance']['memo_completeness']=='incomplete'
        assert memo['governance']['human_review_status']=='pending'
        assert saved.current_conclusion['payload']['challenge_status']=='not_performed'
        assert memo['governance']['independent_challenge_status']=='not_performed'
        assert saved.audit['challenger']['status']=='disabled_by_workflow'
        assert saved.audit['challenger']['rounds']=='not_executed'
        assert 'business_challenge' not in run.model_configuration['active_agents']
        assert any(h['hypothesis_id']=='M1S2-H001' for h in saved.audit['hypotheses']['records'])
        ledger=saved.audit['orchestrator']['editorial_selection']
        assert next(d for d in ledger['selection_decisions'] if d['hypothesis_id']=='M1S2-H001')['decision']=='omitted'
        before=[(r.name,r.sha256,r.payload_json) for r in verified_artifacts(session,record['case_id'],summary['evidence_snapshot_version'])]
        references=deepcopy(saved.handoff['canonical_references'])
        assert references['four_section_memo']==summary['four_section_memo']
    for bo,_ in env['backends']:
        bo.generate=lambda *a,**k: pytest.fail('A read triggered inference')
    m3.generate=lambda *a,**k: pytest.fail('A read triggered management inference')
    restored=bo_fo.Jobs(env['jobs']._store_path)
    assert restored.get(ident)['run_ids']==record['run_ids']
    review=client.get(f'/analysis/{ident}/review');assert review.status_code==200,review.text
    page=html.fromstring(review.text)
    assert len(page.xpath('//*[@data-memo-section]'))==4
    assert not page.xpath('//details[@open]')
    assert len(page.xpath('//*[@data-schedule="senior_notes"]//tbody/tr'))==6
    assert len(page.xpath('//*[@data-schedule="non_note"]//tbody/tr'))==4
    visible=deepcopy(page)
    for d in visible.xpath('//details'):d.getparent().remove(d)
    assert 'Industry analysis is not available in this version.' in visible.text_content()
    assert 'Admissions were stable during the year.' not in visible.text_content()
    assert 'Revenue Drivers' in visible.text_content() and 'Cost Drivers' in visible.text_content()
    assert 'Business driver' not in visible.text_content()
    assert 'Fact' in visible.text_content() and 'Inference' in visible.text_content()
    for finding in page.xpath('//*[@data-source-finding]'):
        assert finding.xpath('.//dl[@class="bo-finding-points"]/div[@class="bo-finding-point"]/dt/text()')==['Finding','Credit Implication','Watch Triggers']
        assert finding.xpath('.//dl[@class="bo-evidence-assessment"]/div/dt/text()') == [
            'Specialist Interpretation', 'Assumptions / Gaps', 'Validation Assessment']
        assert finding.xpath('.//dl[@class="bo-finding-points"]//dt/span[contains(@class,"bo-badge-type")]')
        assert not finding.xpath('./div[@class="bo-finding-badges"]/span[contains(@class,"bo-badge-type")]')
    assert 'Source Establishes' not in review.text
    assert page.xpath('//*[@data-source-finding]//article[@class="bo-source-quotation"]')
    assert page.xpath('//details[@class="bo-evidence-technical" and not(@open)]/pre')
    assert 'Open Referenced Passage' not in review.text
    source_links = set(page.xpath('//a[normalize-space()="Open Original 10-K"]/@href'))
    assert source_links
    for source_link in source_links:
        original = client.get(source_link)
        assert original.status_code == 200, original.text
        assert html.fromstring(original.text).xpath('//mark[@class="bo-original-highlight"]')
        assert "default-src 'none'" in original.headers['content-security-policy']
    bad_link = next(iter(source_links)).rsplit('/', 1)[0] + '/not-a-selected-quote'
    assert client.get(bad_link).status_code == 404
    audit=client.get(f'/analysis/{ident}/audit');assert audit.status_code==200
    assert 'M1S2-H001' in audit.text and 'omitted' in audit.text
    assert 'Independent challenge is disabled for this workflow.' in audit.text
    history=html.fromstring(client.get('/credit-memos').text)
    link=history.xpath(f'//article[@data-job-id="{ident}"]//h3/a/@href')[0]
    assert link==f'/analysis/{ident}/review'
    assert client.get(link).text==review.text
    execution=client.get(f'/analysis/{ident}/execution')
    assert f'/analysis/{ident}/review' in execution.text
    base=f'/cases/{record["case_id"]}/bo/runs/{rid}'
    assert client.get(base+'/memo.json').json()==memo
    assert client.get(base+'/memo.html').status_code==200
    with env['factory']() as session:
        assert bo_artifact(session,rid,'four_section')==memo
        assert [(r.name,r.sha256,r.payload_json) for r in verified_artifacts(session,record['case_id'],summary['evidence_snapshot_version'])]==before
    if os.environ.get('BO_M5_EVIDENCE'):
        out=Path(os.environ['BO_M5_EVIDENCE']);out.mkdir(parents=True,exist_ok=True)
        (out/'end-to-end-trace.json').write_text(json.dumps({'job':record,'backend_calls':methods,
            'management_calls':m3.calls,'contract':writer['schema_version'],'selection_policy':POLICY_VERSION,
            'identity':memo['identity'],'canonical_references':references,'content_hash':memo['content_hash'],
            'source_copy_equal':True,'review_history_identical':True,'read_only_hashes_unchanged':True},indent=2)+'\n')


def test_same_company_runs_review_decisions_and_corrupt_binding(browser_env):
    env=browser_env;a=launch(env);b=launch(env);client=env['client']
    aid,bid=a['run_ids']['bo'],b['run_ids']['bo']
    assert aid!=bid
    assert a['result']['bo']['summary']['evidence_snapshot_version']==1
    assert b['result']['bo']['summary']['evidence_snapshot_version']==2
    with env['factory']() as s:
        assert bo_artifact(s,aid,'four_section')['identity']['evidence_snapshot_version']==1
        assert bo_artifact(s,bid,'four_section')['identity']['evidence_snapshot_version']==2
        ah=a['result']['bo']['summary']['handoff_id'];bh=b['result']['bo']['summary']['handoff_id']
        with pytest.raises(HandoffError):review_handoff(s,ah,reviewer='',reason='')
        # Existing rules require acknowledgement only for recorded unresolved
        # challenges. Missing Industry alone does not create one. An explicit
        # signed decision is distinct from silently approving an incomplete run.
        if s.get(AcceptedBusinessOverviewRow,ah).payload['unresolved_challenges']:
            with pytest.raises(HandoffError):review_handoff(s,ah,reviewer='Fixture',reason='Missing acknowledgement')
        review_handoff(s,ah,reviewer='Offline reviewer',reason='Explicit offline acceptance with limitations acknowledged',acknowledge_unresolved=True)
        s.commit()
        assert s.get(AcceptedBusinessOverviewRow,bh).human_review_status=='pending'
    assert aid in client.get(f'/analysis/{a["job_id"]}/review').text
    assert bid not in client.get(f'/analysis/{a["job_id"]}/review').text
    assert 'Current human review: <strong>Accepted</strong>' in client.get(f'/analysis/{a["job_id"]}/review').text
    assert 'Current human review: <strong>Pending</strong>' in client.get(f'/analysis/{b["job_id"]}/review').text
    with env['factory']() as s:
        row=s.get(AcceptedBusinessOverviewRow,bh)
        from app.services.bo.reporting import handoff_content_hash
        payload=deepcopy(row.payload)
        payload['canonical_references']['four_section_memo']=a['result']['bo']['summary']['four_section_memo']
        payload['content_hash']=handoff_content_hash(payload)
        row.payload,row.content_hash=payload,payload['content_hash'];s.commit()
    assert client.get(f'/analysis/{b["job_id"]}/review').status_code==409
    assert client.get(f'/cases/{b["case_id"]}/bo/runs/{bid}/memo.json').status_code==409
    assert client.get(f'/analysis/{b["job_id"]}/memo.pdf').status_code==409
    assert client.get(f'/cases/{b["case_id"]}/bo/runs/{bid}/memo.pdf').status_code==409
    assert client.get(f'/cases/FOREIGN/bo/runs/{aid}/memo.html').status_code==404
    assert client.get(f'/analysis/{a["job_id"]}/review').status_code==200


@pytest.mark.parametrize('defect',['missing_database','missing_column','missing_source','bad_hash'])
def test_preflight_fails_before_provider_setup(browser_env, defect):
    env=browser_env
    if defect=='missing_database':env['database'].unlink()
    elif defect=='missing_column':
        with sqlite3.connect(env['database']) as con:con.execute('ALTER TABLE agentic_analysis_runs DROP COLUMN model_configuration')
    elif defect=='missing_source':(env['source']/'nfh-20251231.htm').unlink()
    else:
        p=env['source']/'nfh-20251231.htm';p.write_bytes(p.read_bytes()+b'corrupt')
    response=env['client'].post('/analysis/start',data={'company':'nfh-10-k-fy2025','sections':'bo','submission_key':uuid.uuid4().hex})
    assert response.status_code==400,response.text
    assert not env['backends'] and not env['jobs'].recent()


def test_exploratory_cannot_be_approved(browser_env):
    env=browser_env;record=launch(env,mode='exploratory')
    with env['factory']() as s:
        rid=record['run_ids']['bo'];memo=bo_artifact(s,rid,'four_section')
        assert memo['governance']['validators_enforced'] is False
        assert memo['governance']['memo_completeness']=='incomplete'
        with pytest.raises(HandoffError,match='Exploratory'):
            review_handoff(s,record['result']['bo']['summary']['handoff_id'],reviewer='Offline',reason='No approval',acknowledge_unresolved=True)


def test_real_combined_worker_stages_fo_and_rms(browser_env):
    env=browser_env
    from tests.integration.test_fo_runner_api import agent
    outcome=bo_fo.run_bo_fo(database=env['database'],folder=FOLDER,case_id='NFH_PAIR',
        bo_backend=business_backend(),m3_backend=ManagementBackend(),fo_backend=agent(),fo_mode='scripted',
        output_root=env['root']/'out',business_orchestrator_contract=OUTPUT_VERSION)
    assert outcome['bo']['status']==outcome['fo']['status']==outcome['rms']['status']=='completed',outcome
    assert not list((env['root']/'staging').glob('*.db'))
    br=outcome['bo']['summary']['analysis_run_id'];fr=outcome['fo']['summary']['run_id']
    selected={'job_id':'pair','case_id':'NFH_PAIR','bo_only':False,'bo_validators':True,'execution_status':'completed',
              'run_ids':{'bo':br,'fo':fr}}
    with env['factory']() as s:
        fo=s.get(FinancialOverviewRunRow,fr)
        before=deepcopy(fo.payload)
        view=analysis_workspace.load_review(s,selected)
        assert view['four_section'] and view['financial']
        review_handoff(s,outcome['bo']['summary']['handoff_id'],reviewer='Offline',reason='Explicit BO only decision',acknowledge_unresolved=True)
        s.commit()
        assert analysis_workspace.governance(s,selected,view['bo'],fo,True)!='Approved'
        assert fo.payload==before and content_hash(before)==fo.content_hash
    rms=json.loads(Path(outcome['rms']['summary']['output']).read_text())
    assert rms['sources']['bo_analysis_run_id']==br and rms['sources']['fo_run_id']==fr
    assert outcome['rms']['summary']['requires_human_review'] is True


def test_source_change_after_preflight_fails_without_generation(browser_env, monkeypatch):
    env=browser_env
    original=analysis.execution_backends
    def changed(sections):
        result=original(sections)
        path=env['source']/'nfh-20251231.htm'
        path.write_bytes(path.read_bytes()+b'changed after preflight')
        return result
    monkeypatch.setattr(analysis,'execution_backends',changed)
    response=env['client'].post('/analysis/start',data={'company':'nfh-10-k-fy2025','sections':'bo','submission_key':uuid.uuid4().hex},follow_redirects=False)
    assert response.status_code==303,response.text
    ident=response.headers['location'].split('/')[2]
    failed=completed(env['jobs'],ident)
    assert failed['execution_status']=='failed' and failed['error']
    backend,m3=env['backends'][0]
    assert not backend.requests and not m3.calls
    for _ in range(3):assert env['jobs'].get(ident)['execution_status']=='failed'
    with env['factory']() as session:
        assert session.query(AgenticAnalysisRun).count()==0
        assert session.query(AcceptedBusinessOverviewRow).count()==0


def test_real_worker_cancellation_rolls_back_and_does_not_restart(browser_env, monkeypatch):
    env=browser_env
    entered,release=threading.Event(),threading.Event()
    backend=business_backend();m3=ManagementBackend();original=backend.generate
    lock=threading.Lock()
    def waiting(request):
        with lock:
            first=not entered.is_set()
            entered.set()
        if first:assert release.wait(10)
        return original(request)
    backend.generate=waiting
    def offline(sections):
        env['backends'].append((backend,m3));return backend,m3,None
    monkeypatch.setattr(analysis,'execution_backends',offline)
    token=uuid.uuid4().hex
    data={'company':'nfh-10-k-fy2025','case_id':'NFH_BROWSER','sections':'bo','submission_key':token}
    response=env['client'].post('/analysis/start',data=data,follow_redirects=False)
    ident=response.headers['location'].split('/')[2]
    try:
        assert entered.wait(5)
        assert env['client'].post(f'/analysis/{ident}/stop',follow_redirects=False).status_code==303
    finally:release.set()
    stopped=completed(env['jobs'],ident)
    assert stopped['execution_status']=='stopped' and stopped['stop_requested']
    count=len(backend.requests)
    with env['factory']() as session:
        assert session.query(AgenticAnalysisRun).count()==0
        assert session.query(AcceptedBusinessOverviewRow).count()==0
        assert not any(r.name.startswith('bo_four_section_memo:') for r in session.query(StageArtifact))
    again=env['client'].post('/analysis/start',data=data,follow_redirects=False)
    assert again.headers['location']==response.headers['location']
    assert bo_fo.Jobs(env['jobs']._store_path).get(ident)['execution_status']=='stopped'
    assert len(backend.requests)==count
    assert not list((env['root']/'out').glob('bo/**/business_overview_four_section.v1.json'))


def test_locked_database_preflight_has_no_provider_calls(browser_env):
    env=browser_env
    with sqlite3.connect(env['database']) as connection:
        connection.execute('BEGIN IMMEDIATE')
        response=env['client'].post('/analysis/start',data={'company':'nfh-10-k-fy2025','sections':'bo','submission_key':uuid.uuid4().hex})
        connection.rollback()
    assert response.status_code==400 and 'database' in response.text.lower()
    assert not env['backends'] and not env['jobs'].recent()


@pytest.mark.parametrize('repair_succeeds,mode',[(True,'standard'),(False,'standard'),(False,'exploratory')])
def test_source_selector_repair_and_integrity_are_bounded(browser_env,repair_succeeds,mode):
    env=browser_env
    backend=business_backend()
    valid=deepcopy(backend._script['orchestrate'][0])
    invalid=deepcopy(valid)
    invalid['selections'].append(deepcopy(invalid['selections'][0]))
    backend._script['orchestrate']=[invalid,valid if repair_succeeds else invalid]
    management=ManagementBackend()
    analysis.execution_backends=lambda sections:(backend,management,None)
    record=launch(env,mode=mode)
    assert backend.calls('orchestrate')==2
    for aid in ['m1_revenue_quality','m1_customer_stickiness','m1_pricing_power','m1_operating_model','m1_competitive_durability']:
        assert backend.calls(aid)==1
    assert backend.calls('challenge')==0
    assert record['result']['bo']['summary']['has_synthesis'] is repair_succeeds
    with env['factory']() as session:
        memo=bo_artifact(session,record['run_ids']['bo'],'four_section')
        assert memo['sections'][2]['status']==('complete' if repair_succeeds else 'unavailable')
        assert memo['governance']['human_review_status']=='pending'
        if not repair_succeeds:
            assert memo['governance']['memo_completeness']=='incomplete'
    assert env['client'].get(f'/analysis/{record["job_id"]}/review').status_code==200


def test_disabled_challenge_requires_exact_persisted_policy(browser_env):
    from app.services.pipeline.artifacts import ArtifactIntegrityError
    env=browser_env;record=launch(env)
    rid=record['run_ids']['bo']
    with env['factory']() as session:
        original=bo_artifact(session,rid,'four_section')
        row=session.get(AgenticAnalysisRun,rid)
        row.model_configuration={**row.model_configuration,'independent_business_challenge_enabled':True}
        session.flush()
        with pytest.raises(ArtifactIntegrityError,match='Frozen root identity'):
            bo_artifact(session,rid,'four_section')
        session.rollback()
        assert bo_artifact(session,rid,'four_section')==original


def test_reviewed_partial_management_reaches_final_memo(browser_env,monkeypatch):
    from app.services.llm.client import LLMRawResult
    from app.models.orm import AgentRunRow
    env=browser_env
    class PartialManagement(ManagementBackend):
        def generate(self,request):
            result=super().generate(request)
            if request.prompt.name!='m3_management_assessment':
                return result
            payload=json.loads(result.raw_response)
            payload['facts'].append(dict(fact_id='unsupported-extra',executive='Alex Sample',
                statement='UNSUPPORTED PERFORMANCE CLAIM',
                citations=[dict(source_id='not-in-the-packet',quote='UNSUPPORTED PERFORMANCE CLAIM')]))
            payload['judgments'].append({**payload['judgments'][0],
                'judgment_id':'unsupported-observation','supporting_fact_ids':['unsupported-extra'],
                'explanation':'UNSUPPORTED PERFORMANCE CLAIM'})
            return LLMRawResult(json.dumps(payload),'offline-partial-management',{'backend':'fake'})
    bo,m3=business_backend(),PartialManagement()
    monkeypatch.setattr(analysis,'execution_backends',lambda sections:(bo,m3,None))
    record=launch(env)
    rid=record['run_ids']['bo']
    with env['factory']() as session:
        memo=bo_artifact(session,rid,'four_section')
        saved=load_saved_inputs(session,rid)
        source=saved.audit['module_conclusions']['M3']['m3_rebuild']['management']
        management=memo['sections'][1]
        assert source['status']==management['status']=='partial'
        assert management['content']==source['artifact']
        assert management['content']['profiles'] and management['content']['observations']
        assert all(f['fact_id']!='unsupported-extra' for f in management['content']['facts'])
        assert any(c['claim_id']=='unsupported-extra' and c['outcome']=='unsupported'
                   for c in management['content']['validation']['claim_results'])
        assert management['visible_warnings'] and memo['governance']['memo_completeness']=='incomplete'
        assert memo['governance']['human_review_status']=='pending'
        producers=list(session.scalars(select(AgentRunRow).where(AgentRunRow.analysis_run_id==rid,
            AgentRunRow.agent_id.in_(['m3_management_assessment','m3_validator_7']))))
        assert len(producers)==2 and all(p.validation_status=='valid' for p in producers)
    response=env['client'].get(f'/analysis/{record["job_id"]}/review')
    assert response.status_code==200
    page=html.fromstring(response.text)
    for details in page.xpath('//details'):details.getparent().remove(details)
    assert 'Alex Sample' in page.text_content()
    assert 'UNSUPPORTED PERFORMANCE CLAIM' not in page.text_content()


def test_failed_management_review_still_withholds_section(browser_env,monkeypatch):
    from app.services.llm.client import LLMRawResult
    env=browser_env
    class InvalidReviewer(ManagementBackend):
        def generate(self,request):
            if request.prompt.name=='m3_validator_7':
                return LLMRawResult('not JSON','offline-failed-management-review',{'backend':'fake'})
            return super().generate(request)
    monkeypatch.setattr(analysis,'execution_backends',lambda sections:(business_backend(),InvalidReviewer(),None))
    record=launch(env)
    with env['factory']() as session:
        memo=bo_artifact(session,record['run_ids']['bo'],'four_section')
        assert memo['sections'][1]['status']=='unavailable'
        assert memo['sections'][1]['content'] is None
        assert memo['sections'][1]['visible_warnings']
        assert memo['sections'][2]['content'] is not None
