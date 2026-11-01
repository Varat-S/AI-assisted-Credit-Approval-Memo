"""Milestone 3: exact-run presentation, synthetic recorded artefacts, no paid calls."""
import copy
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from lxml import html
from app.api.deps import get_session
from app.main import create_app
from app.models.orm import AgenticAnalysisRun, AcceptedBusinessOverviewRow, TopicConclusionRow
from app.services import bo_fo
from app.services.bo.reporting import handoff_content_hash
from app.services.pipeline.artifacts import StageRecorder
from app.schemas.bo import AcceptedBusinessOverview


def seed_run(session, name, version=1, *, missing=False, exploratory=False, challenged=True, reports=True):
    rid='bo-'+name
    session.add(AgenticAnalysisRun(analysis_run_id=rid,case_id='HCA_2024',evidence_snapshot_version=version,
        status='completed',analysis_mode='business_overview',router_version='fixture',
        agent_registry_version='fixture',agent_registry_hash='fixture',scoring_config_version=1,scoring_config_hash='fixture'))
    session.flush()
    handoff=AcceptedBusinessOverview(handoff_id='handoff-'+name,analysis_run_id=rid,case_id='HCA_2024',
        evidence_snapshot_version=version,business_topic_conclusion_id=None if missing else 'conclusion-'+name,
        conclusion_status='unavailable' if missing else 'human_review_required',
        agent_registry_version='fixture',agent_registry_hash='fixture',scoring_config_version=1,
        scoring_config_hash='fixture',validators_enforced=not exploratory).model_dump(mode='json')
    session.add(AcceptedBusinessOverviewRow(handoff_id=handoff['handoff_id'],analysis_run_id=rid,
        case_id='HCA_2024',snapshot_version=version,payload=handoff,content_hash=handoff_content_hash(handoff)))
    memo={'document':'business_overview_memo','version':'bo-memo-1.0',
          'case':{'case_id':'HCA_2024','borrower':'SYNTHETIC HCA Healthcare','as_of_date':'2024-12-31',
                  'evidence_snapshot_version':version},
          'run':{'analysis_run_id':rid,'execution_mode':'offline_simulation','validators_enforced':not exploratory},
          'status':{'conclusion_status':handoff['conclusion_status']},
          'executive':{'provisional_view':None if missing else {'claim_id':'assessment-'+name,'text':'Synthesized assessment '+name,'citations':[1]},
                       'principal_uncertainties':[], 'follow_up':[]},
          'strengths_and_vulnerabilities':{'strengths':[],'weaknesses':[]},
          'sections':[], 'outstanding':{'open_questions':['Outstanding '+name]},
          'sources':[{'n':1,'evidence_id':'evidence-'+name,'document_id':'doc-'+name,'filename':'hca-fixture.txt',
                      'source_url':'https://www.sec.gov/Archives/fixture/'+name,'excerpt':'Recorded quote '+name}],
          'module_conclusions':{'M1':{'findings':[{'claim':'AUDIT ONLY SPECIALIST '+name}]}}}
    audit={'document':'business_overview_audit_report','version':'bo-audit-1.0',
           'case':memo['case'],'run':memo['run'],'agents':[],'hypotheses':{'records':[]},'conclusions':[],
           'orchestrator':{'history':[],'claims':[]},'challenger':{'rounds':'not_executed','recorded_findings':[]},
           'sources':{'documents':[],'rejected_sources':[]},'reconciliation':{'contradictions':[],'duplicate_groups':[]},'evidence_packets':[],
           'retrieval':{},'module_conclusions':{},'rerun':'not_performed','execution':{},
           'final_conclusion':{'conclusion_id':'conclusion-'+name,'challenge_status':'escalated'}}
    if not missing:
        payload={'analysis_run_id':rid,'topic':'business','orchestrator_run_id':'orchestrator-'+name,
                 'challenge_status':'escalated','overall_assessment':{
                     'claim_id':'assessment-'+name,'text':'Synthesized assessment '+name,
                     'evidence_ids':['evidence-'+name],'hypothesis_ids':['hyp-'+name]},
                 'strengths':[{'claim_id':'strength-'+name,'text':'Synthesized strength '+name,'evidence_ids':['evidence-'+name]}],
                 'weaknesses':[{'claim_id':'risk-'+name,'text':'Synthesized vulnerability '+name,'evidence_ids':['evidence-'+name]}],
                 'key_drivers':[{'claim_id':'integrated-'+name,'text':'Integrated conclusion '+name,'evidence_ids':['evidence-'+name]},
                                {'claim_id':'COV-hyp-'+name,'text':'COPIED SPECIALIST '+name,'evidence_ids':['evidence-'+name]}],
                 'material_risks':[],'open_questions':['Outstanding '+name],'unresolved_contradictions':[]}
        session.add(TopicConclusionRow(id='conclusion-'+name,analysis_run_id=rid,case_id='HCA_2024',
                    snapshot_version=version,topic='business',payload=payload,orchestrator_run_id='orchestrator-'+name,
                    challenge_status='escalated',acceptance_state='accepted'))
        audit['conclusions']=[{'conclusion_id':'conclusion-'+name,'acceptance_state':'accepted','payload':payload,
                               'orchestrator_run_id':'orchestrator-'+name,'challenge_status':'escalated'}]
        audit['challenger']['rounds']=[{'conclusion_id':'conclusion-'+name,'status':'validated' if challenged else 'rejected',
                                       'outcome':'human_review_required','round':0,'findings':[]}]
        audit['agents']=[{'agent_id':'business_orchestrator','status':'validated',
                         'validator_adjustments':[{'claim_id':'COV-hyp-'+name,
                          'note':'Included a validated specialist finding omitted from the model synthesis.'}]}]
    from app.models.orm import AgentRunRow, HypothesisRecordRow
    from app.core.hashing import content_hash
    import json
    document={'document_id':'doc-'+name,'filename':'hca-fixture.txt','form':'10-K',
              'source_url':'https://www.sec.gov/Archives/fixture/'+name,'sha256':'fixture-digest'}
    canonical={'documents':[document],'narrative_evidence':[{'evidence_id':'evidence-'+name,
               'document_id':'doc-'+name,'text':'Recorded quote '+name,'location':'Item 1, paragraph 2'}], 'facts':[]}
    audit['sources']={'documents':[document],'rejected_sources':[{'filename':'unadmitted-source.pdf','reason':'After cutoff'}]}
    audit['evidence_snapshot']={'case_id':'HCA_2024','snapshot_version':version,'content_hash':content_hash(canonical),
                               'fact_count':0,'narrative_passage_count':1,'human_verified_fact_count':0}
    audit['retrieval']={'gaps':[],'attempts':[]}
    audit['hypotheses']['statistics']={'overall':{'qualified':1,'rejected':1},'by_agent':{}}
    memo['status']['text']='Synthetic post-challenge assessment; human review required.'
    memo['run']['execution_label']='SYNTHETIC OFFLINE FIXTURE'
    raw_hypotheses=[{'hypothesis_id':'hyp-'+name,'claim':'Original specialist wording '+name},
                    {'hypothesis_id':'rejected-'+name,'claim':'Original rejected wording '+name}]
    agent_specs=[('specialist-'+name,'m1_business_model',{'hypotheses':raw_hypotheses,'api_key':'fixture-secret-never-display'}),
                 ('orchestrator-'+name,'business_orchestrator',{'overall_assessment':{'text':'Original synthesis '+name}}),
                 ('challenger-'+name,'business_challenge',{'challenges':[{'reason':'Challenge concerns '+name}]}),
                 ('validator7-'+name,'m3_validator7',{'decisions':[{'outcome':'qualified','reason':'Recorded validator decision'}]})]
    for agent_run_id,agent_id,parsed in agent_specs:
        session.add(AgentRunRow(run_id=agent_run_id,analysis_run_id=rid,agent_id=agent_id,
            agent_definition_hash='fixture',topic='business',case_id='HCA_2024',snapshot_version=version,
            prompt_id='fixture',prompt_hash='fixture',model_id='scripted-fixture',input_hash='fixture',
            validation_status='passed',raw_response=json.dumps(parsed),parsed_response=parsed,
            validation_detail='Recorded schema validation passed'))
    if not missing:
        for record_id,hid,disposition,state,text in [
                ('old-'+name,'hyp-'+name,'supported','superseded','Earlier specialist wording '+name),
                ('finding-'+name,'hyp-'+name,'qualified','accepted','AUDIT ONLY SPECIALIST '+name),
                ('rejected-record-'+name,'rejected-'+name,'rejected','accepted','REJECTED SPECIALIST '+name)]:
            hypothesis={'hypothesis_id':hid,'agent_id':'m1_business_model','section':'M1S1','claim':text,
                'claim_type':'inference','direction':'negative','disposition':disposition,
                'admissibility':'audit_only' if disposition=='rejected' else 'qualified_narrative',
                'confidence':'medium','materiality':'high','supporting_evidence_ids':['evidence-'+name],
                'contradicting_evidence_ids':[],'evidence_quotes':[{'evidence_id':'evidence-'+name,'quote':'Recorded quote '+name}],
                'validation_notes':['Qualification recorded '+name],'model_stated':{'disposition':'supported'},
                'validator_id':'validator-fixture','validator_version':'test-v1','review_flags':[],
                'evidence_basis':'company_specific_disclosure','acceptance_state':state}
            session.add(HypothesisRecordRow(id=record_id,hypothesis_id=hid,analysis_run_id=rid,case_id='HCA_2024',
                snapshot_version=version,agent_id='m1_business_model',agent_run_id='specialist-'+name,section='M1S1',
                claim_type='inference',direction='negative',disposition=disposition,
                admissibility=hypothesis['admissibility'],payload=hypothesis,acceptance_state=state))
            audit['hypotheses']['records'].append({**hypothesis,'record_id':record_id,'supersedes_id':None})
        audit['agents'].append({'agent_id':'m1_business_model','code':'M1S1','role':'Business model specialist',
            'status':'validated','detail':None,'runs':[],'validation_issues':[],
            'validator_adjustments':[{'note':'Qualification recorded '+name}]})
        audit['agents'][0].update(code=None,role='Cross-module synthesizer',detail=None,runs=[],validation_issues=[])
        audit['orchestrator']['history']=[{'round':0,'agent_run_id':'orchestrator-'+name,'status':'accepted','issues':[]}]
        finding={'challenge_id':'challenge-'+name,'target':'integrated-'+name,'severity':'high',
                 'reason':'Challenge concerns '+name,'requires_reanalysis':True,'requested_rerun_scope':['m1_business_model']}
        audit['challenger']['rounds'][0].update(summary='Independent challenge '+name,findings=[finding],
            agent_run_id='challenger-'+name,decision={'requires_rerun':False,'escalated':True})
        audit['challenger']['recorded_findings']=[finding]
        handoff['unresolved_challenges']=[finding]
        memo['outstanding']['unresolved_challenges']=[finding]
    handoff_row=session.get(AcceptedBusinessOverviewRow,'handoff-'+name)
    handoff_row.payload=handoff
    handoff_row.content_hash=handoff_content_hash(handoff)
    recorder=StageRecorder(session,'HCA_2024',version)
    recorder.record('canonical_evidence',canonical)
    if reports:
        recorder.record('bo_memo:'+rid,memo);recorder.record('bo_audit:'+rid,audit)
    session.flush()
    return {'job_id':name,'created_at':f'2026-11-{version:02d}T12:00:00+00:00','started_at':'2026-11-01T12:00:00Z',
        'metadata':{'company':'HCA Healthcare (HCA)','reporting_period':'2024-12-31',
                    'test_state':'SYNTHETIC UI FIXTURE — no live analysis'},
        'case_id':'HCA_2024','folder':'HCA 10-K FY2024','bo_only':True,'bo_validators':not exploratory,
        'execution_status':'completed','status':'finished','stop_requested':False,
        'memo_status':'human_review_required','error':None,'stages':{},'events':[],
        'sections':{'bo':{'status':'completed'}},
        'result':{'bo':{'status':'completed','summary':{'analysis_run_id':rid}}}}


@pytest.fixture
def memo_workspace(db_session,monkeypatch):
    from app.services.llm.providers_vertex import VertexProviderBackend
    from app.services.llm.providers import RealProviderBackend
    def forbidden(*args,**kwargs):pytest.fail('Read-only workspace must not run models or jobs')
    monkeypatch.setattr(VertexProviderBackend,'generate',forbidden)
    monkeypatch.setattr(RealProviderBackend,'generate',forbidden)
    jobs=[seed_run(db_session,'hca-first',1),seed_run(db_session,'hca-second',2,exploratory=True)]
    for ident,status in [('hca-active','running'),('hca-failed','failed'),('hca-interrupted','interrupted')]:
        value=copy.deepcopy(jobs[0]);value.update(job_id=ident,execution_status=status,created_at='2026-11-03T12:00:00Z',result=None)
        jobs.append(value)
    class Records:
        start=forbidden
        def recent(self):return copy.deepcopy(jobs)
        def get(self,ident):return copy.deepcopy(next((job for job in jobs if job['job_id']==ident),None))
    monkeypatch.setattr(bo_fo,'jobs',Records())
    app=create_app();app.dependency_overrides[get_session]=lambda:db_session
    with TestClient(app) as client:yield client,jobs,db_session


def test_history_search_filter_and_exact_run_links(memo_workspace):
    client,jobs,_=memo_workspace
    page=html.fromstring(client.get('/credit-memos').text)
    rows=page.xpath('//article[@data-job-id]')
    assert len(rows)==5
    assert rows[-1].get('data-job-id')=='hca-first'
    assert page.xpath('//article[@data-job-id="hca-first"]//h3/a/@href')==['/analysis/hca-first/review']
    for ident in ['hca-active','hca-failed','hca-interrupted']:
        assert page.xpath(f'//article[@data-job-id="{ident}"]//h3/a/@href')==[f'/analysis/{ident}/execution']
    assert len(html.fromstring(client.get('/credit-memos?search=HCA').text).xpath('//article'))==5
    assert len(html.fromstring(client.get('/credit-memos?search=hca-first').text).xpath('//article'))==1
    assert 'No analyses match' in client.get('/credit-memos?search=nope').text
    assert len(html.fromstring(client.get('/credit-memos?status=completed&mode=exploratory').text).xpath('//article'))==1
    assert 'Human review required' in page.text_content() and 'Draft' in page.text_content()
    assert client.get('/credit-memos?status=nonsense').status_code==400


def test_history_never_falls_back_to_latest_company_run(memo_workspace):
    client,jobs,_=memo_workspace
    jobs[0]['result']=None
    page=html.fromstring(client.get('/credit-memos').text)
    assert page.xpath('//article[@data-job-id="hca-first"]//h3/a/@href')==['/analysis/hca-first/execution']
    jobs[0]['result']={'bo':{'summary':{'analysis_run_id':'bo-hca-second'}}}
    jobs[0]['run_ids']={'bo':'bo-hca-first'}
    assert 'conflicting report references' in client.get('/credit-memos').text


def test_history_approval_is_not_execution_completion(memo_workspace):
    client,jobs,session=memo_workspace
    row=session.get(AcceptedBusinessOverviewRow,'handoff-hca-first');row.human_review_status='accepted';session.flush()
    page=html.fromstring(client.get('/credit-memos').text)
    assert 'Approved' in page.xpath('//article[@data-job-id="hca-first"]')[0].text_content()
    assert 'Approved' not in page.xpath('//article[@data-job-id="hca-second"]')[0].text_content()


def test_review_selects_historical_synthesis_not_latest_or_specialist_dump(memo_workspace):
    client,_,session=memo_workspace
    from app.models.orm import StageArtifact
    before={row.name:row.payload_json for row in session.query(StageArtifact)}
    first=client.get('/analysis/hca-first/review')
    assert first.status_code==200,first.text
    assert 'Synthesized assessment hca-first' in first.text
    assert 'Synthesized assessment hca-second' not in first.text
    assert 'Synthesized strength hca-first' in first.text
    assert 'Synthesized vulnerability hca-first' in first.text
    assert 'Integrated conclusion hca-first' in first.text
    assert 'COPIED SPECIALIST' not in first.text and 'AUDIT ONLY SPECIALIST' not in first.text
    assert 'Further validated findings' not in first.text and 'Further governed specialist findings' not in first.text
    page=html.fromstring(first.text)
    assert page.xpath('//a[text()="Audit & Review"]/@href')==['/analysis/hca-first/audit']
    citations=page.xpath('//a[@class="source-cite"]/@href')
    assert citations and all(page.xpath('//*[@id="'+href[1:]+'"]') for href in citations)
    assert page.xpath('//a[text()="Open source"]/@href')==['https://www.sec.gov/Archives/fixture/hca-first']
    assert 'Human review required' in first.text
    assert before=={row.name:row.payload_json for row in session.query(StageArtifact)}


def test_exploratory_review_is_unavailable_not_a_validated_assessment(memo_workspace):
    client,_,_=memo_workspace
    page=client.get('/analysis/hca-second/review')
    assert page.status_code==200
    assert 'No validated Business Credit Assessment is available for this run.' in page.text
    assert 'Synthesized assessment hca-second' not in page.text
    assert 'Final approval is prohibited' in page.text


def test_missing_synthesis_and_unknown_job_never_choose_other_run(memo_workspace):
    client,jobs,session=memo_workspace
    jobs.append(seed_run(session,'hca-missing',4,missing=True))
    page=client.get('/analysis/hca-missing/review')
    assert page.status_code==200 and 'No validated Business Credit Assessment is available for this run.' in page.text
    assert 'Synthesized assessment hca-first' not in page.text
    assert client.get('/analysis/not-a-job/review').status_code==404
    assert client.get('/analysis/hca-active/review',follow_redirects=False).headers['location']=='/analysis/hca-active/execution'


def test_cross_case_or_conflicting_refs_fail_closed(memo_workspace):
    client,jobs,session=memo_workspace
    jobs[0]['case_id']='WRONG_CASE'
    assert client.get('/analysis/hca-first/review').status_code==409
    jobs[0]['case_id']='HCA_2024';jobs[0]['run_ids']={'bo':'different'}
    assert client.get('/analysis/hca-first/review').status_code==409


def test_edited_conclusion_or_corrupt_frozen_artifact_not_rendered(memo_workspace):
    client,_,session=memo_workspace
    row=session.get(TopicConclusionRow,'conclusion-hca-first')
    row.payload={**row.payload,'overall_assessment':{'text':'UNRECORDED TAMPER'}};session.flush()
    response=client.get('/analysis/hca-first/review')
    assert response.status_code==409 and 'UNRECORDED TAMPER' not in response.text


def test_post_challenge_gate_and_unsafe_sources():
    from app.services.analysis_workspace import safe_url
    assert safe_url('javascript:alert(1)') is None
    assert safe_url('file:///private/key') is None
    assert safe_url('https://secret:key@example.com') is None


def test_unvalidated_challenge_cannot_be_presented_as_post_challenge(memo_workspace):
    client,jobs,session=memo_workspace
    jobs.append(seed_run(session,'unchallenged',5,challenged=False))
    response=client.get('/analysis/unchallenged/review')
    assert response.status_code==200
    assert 'No validated Business Credit Assessment is available for this run.' in response.text
    assert 'Synthesized assessment unchallenged' not in response.text


def test_audit_five_sections_and_full_specialist_traceability(memo_workspace):
    client,_,_=memo_workspace
    response=client.get('/analysis/hca-first/audit')
    assert response.status_code==200,response.text
    page=html.fromstring(response.text)
    assert page.xpath('//article/section/@id')==['specialists','validators','synthesizer','challenger','evidence']
    for text in ['Original specialist wording hca-first','AUDIT ONLY SPECIALIST hca-first',
                 'REJECTED SPECIALIST hca-first','superseded','Qualification recorded hca-first',
                 'Original synthesis hca-first','Challenge concerns hca-first','Synthesized assessment hca-first',
                 'COPIED SPECIALIST hca-first','Quotation verification: Not recorded',
                 'Analytical entailment verification: Not recorded · Finding disposition: qualified','unadmitted-source.pdf']:
        assert text in page.text_content(),text
    assert 'hca-second' not in page.text_content()
    assert 'm3_validator7' in page.xpath('//*[@id="validators"]')[0].text_content()
    assert 'm3_validator7' not in page.xpath('//*[@id="specialists"]')[0].text_content()
    assert 'fixture-secret-never-display' not in response.text and '[REDACTED]' in response.text
    local=page.xpath('//a[starts-with(@href,"#")]/@href')
    assert local and all(page.xpath('//*[@id="'+href[1:]+'"]') for href in local)
    assert '/cases/HCA_2024/bo.html?analysis_run_id=bo-hca-first' in response.text
    assert client.get('/analysis/missing/audit').status_code==404


def test_missing_original_or_raw_is_not_invented(memo_workspace):
    client,_,session=memo_workspace
    from app.models.orm import AgentRunRow
    row=session.get(AgentRunRow,'specialist-hca-first')
    row.raw_response=None;row.parsed_response=None;session.flush()
    response=client.get('/analysis/hca-first/audit')
    assert response.status_code==200
    assert 'Original specialist wording hca-first' not in response.text
    assert 'Not recorded' in response.text


def test_audit_rejects_cross_run_agent_logs_and_preserves_frozen_records(memo_workspace):
    client,_,session=memo_workspace
    from app.models.orm import AgentRunRow,StageArtifact
    before=[row.payload_json for row in session.query(StageArtifact)]
    assert client.get('/analysis/hca-first/audit').status_code==200
    assert before==[row.payload_json for row in session.query(StageArtifact)]
    row=session.get(AgentRunRow,'specialist-hca-first');row.case_id='WRONG';session.flush()
    assert client.get('/analysis/hca-first/audit').status_code==409


def test_exploratory_existing_approval_endpoint_remains_blocked(memo_workspace):
    client,_,session=memo_workspace
    response=client.post('/cases/HCA_2024/bo/runs/bo-hca-second/review',data={
        'reviewer':'analyst','reason':'Reviewed synthetic fixture','decision':'accept','acknowledge_unresolved':'on'})
    assert response.status_code==409,response.text
    assert 'Exploratory' in response.text
    assert session.get(AcceptedBusinessOverviewRow,'handoff-hca-second').human_review_status=='pending'


def test_public_audit_redacts_credentials_without_changing_inputs(monkeypatch):
    from app.services.analysis_audit import public_record,raw_output
    from app.core.config import Settings
    from pydantic import SecretStr
    import app.core.config as config
    settings=Settings(_env_file=None,vertex_api_key=SecretStr('configured-secret-123'))
    monkeypatch.setattr(config,'get_settings',lambda:settings)
    value={'api_key':'test-secret','data':'configured-secret-123','input_tokens':42,
           'nested':{'token':'private-token'},'response':'Authorization: Bearer private123'}
    original=copy.deepcopy(value);out=public_record(value)
    assert value==original
    assert out['api_key']=='[REDACTED]' and out['data']=='[REDACTED]' and out['input_tokens']==42
    assert out['nested']['token']=='[REDACTED]' and 'private123' not in out['response']
    assert 'test-secret' not in raw_output('{"api_key":"test-secret"}')


def test_run_without_reports_has_an_honest_empty_audit(memo_workspace):
    client,_,_=memo_workspace
    response=client.get('/analysis/hca-failed/audit')
    assert response.status_code==200,response.text
    assert 'Not recorded' in response.text
    assert 'Synthesized assessment' not in response.text


def test_existing_human_review_updates_only_selected_run_governance(memo_workspace,monkeypatch):
    client,_,_=memo_workspace
    from app.api import workbench
    monkeypatch.setattr(workbench,'_reassess_rms',lambda *args:None)
    response=client.post('/cases/HCA_2024/bo/runs/bo-hca-first/review',data={
        'reviewer':'analyst','reason':'Reviewed synthetic fixture','decision':'accept','acknowledge_unresolved':'on'})
    assert response.status_code==200,response.text
    assert 'Approved · Business Overview' in client.get('/analysis/hca-first/review').text
    assert 'Approved' not in client.get('/analysis/hca-second/review').text


def test_history_accepts_exact_backend_run_id_search(memo_workspace):
    client,_,_=memo_workspace
    page=html.fromstring(client.get('/credit-memos?search=bo-hca-first').text)
    assert page.xpath('//article/@data-job-id')==['hca-first']


def test_source_link_does_not_transmit_query_credentials():
    from app.services.analysis_workspace import safe_url
    assert safe_url('https://example.com/source?api_key=secret') is None
    assert safe_url('https://example.com/source?token=secret') is None
    assert safe_url('https://www.sec.gov/Archives/doc.htm')=='https://www.sec.gov/Archives/doc.htm'


def test_missing_archived_reports_show_incomplete_without_fallback(memo_workspace):
    client,jobs,session=memo_workspace
    jobs.append(seed_run(session,'missing-archive',6,reports=False))
    response=client.get('/analysis/missing-archive/review')
    assert response.status_code==200,response.text
    assert 'No validated Business Credit Assessment is available for this run.' in response.text
    assert 'Synthesized assessment hca-first' not in response.text
    assert client.get('/analysis/missing-archive/audit').status_code==200
