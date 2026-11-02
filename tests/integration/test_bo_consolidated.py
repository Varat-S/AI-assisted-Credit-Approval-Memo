"""Offline consolidated-path acceptance, source fidelity and rendering."""
import copy
import json
import pytest
from app.core.hashing import content_hash
from app.schemas.bo_consolidated import CompetitiveSynthesis, ConsolidatedBO, TITLES
from app.services.bo.consolidated import load, at, MAPPINGS, selection_issues
from app.services.bo.offline import ScriptedBoBackend
from app.services.bo.runner import BusinessOverviewRunner
from app.services.bo.reporting import render_consolidated_html
from app.services.bo.workbench import bo_artifact
from tests.integration.test_bo_v3_complete import _script
from tests import bo_helpers as h


def script(count=5):
    answers = _script()
    specs = [('M1S1-H001','revenue','Negotiated managed-care rates anchor reimbursement.'),
             ('M1S2-H001','revenue','Stable admissions provide a volume foundation.'),
             ('M1S3-H001','vulnerability','Termination rights limit contractual durability.'),
             ('M1S4-H001','cost','Nursing scarcity exposes the business to contract labour costs.'),
             ('M1S5-H001','vulnerability','Hospital and ambulatory competition constrain the competitive position.')]
    points = []
    for i,(hid,dimension,text) in enumerate(specs[:count]):
        point = h.claim('point-'+str(i), 'driver', 'M1S'+str(i+1), text, [hid], claim_type='inference')
        point['analysis'] = {
            'company_evidence': [
                'The admitted fictional filing describes multi-year managed-care agreements with negotiated rates and no minimum patient volumes.',
                'The admitted fictional filing reports stable admissions and identifies patient services as the source of facility revenue.',
                'The admitted fictional filing permits either party to terminate managed-care agreements on notice.',
                'The admitted fictional filing identifies a nursing shortage and rising contract labour costs; workforce initiatives are not assured to succeed.',
                'The admitted fictional filing identifies hospital and ambulatory surgery competitors, including not-for-profit systems.'
            ][i],
            'revenue_or_cost_mechanism': [
                'Agreed rates provide a contractual basis for reimbursement, but the absence of volume commitments leaves revenue dependent on actual patient activity.',
                'Patient activity converts available clinical capacity into service revenue. Stable admissions support current utilisation, while any future volume decline would leave costs to be absorbed by fewer cases.',
                'Termination rights expose the provider to renegotiation or loss of network participation. Multi-year duration therefore does not by itself establish durable pricing power.',
                'Scarce clinical staff can require costly contract coverage to maintain services. If staffing availability limits usable capacity, the exposure can affect both the cost base and service revenue.',
                'Alternative treatment settings can compete for suitable procedures and payer relationships. A broad facility network does not establish superior margins without comparative evidence.'
            ][i],
            'competitive_and_credit_implication': [
                'For lenders, contractual rate visibility is a qualified strength rather than protection against demand or payer-mix deterioration. The evidence does not demonstrate unilateral price-setting ability.',
                'Observed volume stability is a revenue foundation rather than proof of a sustainable moat. Downside analysis still needs service-line profitability and sensitivity of fixed costs to activity.',
                'The lender should distinguish negotiated prices from bargaining dominance: the disclosed exit option leaves a competitive vulnerability whose scale requires contract concentration and renewal evidence.',
                'Labour availability is a competitive and credit sensitivity because continuity of service depends on clinical staffing. Announced training initiatives remain an unproven mitigant without demonstrated retention and cost outcomes.',
                'Credit assessment should retain competitive substitution as a downside exposure while avoiding unsupported conclusions about lost share or profitability. Local service-line outcomes and competitor economics remain evidence gaps.'
            ][i]}
        point.update(dimension=dimension,counterevidence=[], uncertainty="Based on disclosed conditions; competitive outcomes remain uncertain.")
        points.append(point)
    overall = h.claim('overall', 'assessment', 'executive',
                      'Negotiated reimbursement and stable volumes coexist with operating cost pressures.',
                      ['M1S1-H001','M1S2-H001','M1S4-H001'])
    if count < 4:
        overall['hypothesis_ids']=['M1S1-H001']
        overall['evidence_ids']=[{'$hypothesis_evidence':'M1S1-H001'}]
    overall["uncertainty"]="Based on disclosed conditions; effectiveness is not independently established."
    overall.update(dimension='uncertainty',counterevidence=[])
    decisions=[dict(hypothesis_id=hid,disposition='selected' if i<count else 'audit_only',
                    reason='Distinct economic driver' if i<count else 'Not selected in fixture',
                    point_id='point-'+str(i) if i<count else None) for i,(hid,_,_) in enumerate(specs)]
    decisions.append(dict(hypothesis_id='M1A6-H001', disposition='audit_only',
                          reason='Overlapping operating exposures already represented',point_id=None))
    answers['orchestrate']=dict(schema_version='bo-competitive-1.1',overall_assessment=overall,
        key_drivers=points,selections=decisions,coverage_gaps=[] if count>=5 else ['Insufficient distinct insights from admitted evidence.'],
        residual_uncertainty=['Competitor staffing evidence unavailable.'],
        completeness='complete' if count>=5 else 'incomplete',human_review_required=True)
    return answers


def run(session,tmp_path,count=5,answers=None):
    backend=ScriptedBoBackend(answers or script(count))
    result=BusinessOverviewRunner(session, backend=backend, bo_roster='v3', consolidated=True,
        sector=None, data_root=tmp_path/'data', output_root=tmp_path/'out').run_prepared(
            h.CASE,h.evidence_snapshot(),h.metrics(),write_outputs=True)
    return result,backend


def test_end_to_end(db_session,tmp_path):
    result,backend=run(db_session,tmp_path)
    artifact=load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)
    assert [s['title'] for s in artifact['sections']]==list(TITLES)
    assert artifact['sections'][2]['status']=='complete',result.audit['orchestrator']
    assert len(artifact['sections'][2]['synthesis']['key_drivers'])==5
    assert artifact['governance']['human_review_status']=='pending'
    assert artifact['challenge']['status']=='validated'
    assert backend.calls('challenge')==1
    assert not any(a.get('claim_id','').startswith('COV-') for a in result.memo['sections'])
    assert result.audit['competitive_selection']['selections'][-1]['disposition']=='audit_only'
    for index,path in MAPPINGS:
        value=at(result.memo,path)
        if value:
            item=next(i for i in artifact['sections'][index]['items'] if i['field_path']==list(path))
            assert item['content']==value and item['content_hash']==content_hash(value)
    assert artifact['sections'][0]['status'] in {'missing','incomplete'}
    html=render_consolidated_html(artifact)
    assert [html.index(t.replace('&','&amp;')) for t in TITLES]==sorted(html.index(t.replace('&','&amp;')) for t in TITLES)
    assert 'Overlapping operating exposures already represented' not in html
    assert 'overflow:hidden' not in html
    assert bo_artifact(db_session,result.analysis_run_id,'consolidated')==artifact
    assert load(db_session,h.CASE,'other-run',result.snapshot_version) is None


def test_shortfall_preserved_and_bounded(db_session,tmp_path):
    result,backend=run(db_session,tmp_path,count=2)
    artifact=load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)
    section=artifact['sections'][2]
    assert section['status']=='incomplete'
    assert len(section['synthesis']['key_drivers'])==2
    assert section['synthesis']['human_review_required']
    assert result.conclusion_status=='human_review_required'
    assert backend.calls('orchestrate')==2
    assert backend.calls('challenge')==1


def test_strict_schema():
    from pydantic import ValidationError
    data=script()['orchestrate']
    # Resolve fake evidence markers to strings for contract-only checks.
    data['unexpected']=True
    with pytest.raises(ValidationError):
        CompetitiveSynthesis.model_validate(data)


def test_duplicate_and_disposition_guards(db_session,tmp_path):
    result,_=run(db_session,tmp_path)
    from app.schemas.bo import HypothesisRecord
    from app.services.bo.reconcile import reconcile
    hypotheses={x['hypothesis_id']:HypothesisRecord.model_validate({k:v for k,v in x.items() if k in HypothesisRecord.model_fields}) for x in result.audit['hypotheses']['records'] if x['agent_id'].startswith('m1_') and x['acceptance_state']=='accepted'}
    data=copy.deepcopy(result.audit['competitive_selection'])
    data['key_drivers'][1]['hypothesis_ids']=data['key_drivers'][0]['hypothesis_ids']
    assert any('split' in i for i in selection_issues(data,hypotheses,reconcile(list(hypotheses.values()),[])))
    data=copy.deepcopy(result.audit['competitive_selection'])
    data['selections'][0]['disposition']='audit_only'
    assert any('Audit-only' in i for i in selection_issues(data,hypotheses,reconcile(list(hypotheses.values()),[])))


def test_debt_fidelity_long_reports_and_identity(db_session,tmp_path,monkeypatch):
    from app.services.bo.reporting import BoReportBuilder
    from tests.fixtures.hca_module4 import hca_module4_output
    from tests.integration.test_bo_m4_dual_specialist import _debt_evidence
    from app.services.pipeline.artifacts import ArtifactIntegrityError
    from app.models.orm import StageArtifact
    from sqlalchemy import select, text
    answers=script()
    answers['m4_debt']=hca_module4_output()
    backend=ScriptedBoBackend(answers)
    original=BoReportBuilder._memo
    def source_fixture(builder,*args):
        memo=original(builder,*args)
        # Deliberately long designated contents, clearly synthetic and incomplete.
        m3=memo['module_conclusions']['M3']
        m3['m3_rebuild']={
            'structure':{'artifact':{'simulation_disclaimer':'OFFLINE SYNTHETIC STRUCTURE',
                                    'tree':['Parent','Operating company']}},
            'management':{'artifact':{'simulation_label':'OFFLINE SYNTHETIC MANAGEMENT',
                                     'narrative':'Exact wording; qualified conclusion.\nSecond paragraph.',
                                     'citations':[{'quote':'Exact quotation','source':'fixture'}]}}}
        industry=memo['module_conclusions']['M2']['findings']
        industry.append({'claim':'OFFLINE LONG REPORT '+('Industry detail. '*300),
                         'table':[{'period':'2024','amount':'123.4500','currency':'USD'}]})
        return memo
    monkeypatch.setattr(BoReportBuilder,'_memo',source_fixture)
    result=BusinessOverviewRunner(db_session,backend=backend,bo_roster='v3',consolidated=True,
        sector=None,enable_m4_debt_specialist=True,data_root=tmp_path/'data',
        output_root=tmp_path/'out').run_prepared(h.CASE,_debt_evidence(),h.metrics())
    artifact=load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)
    for index,path in MAPPINGS:
        item=next(i for i in artifact['sections'][index]['items'] if i['field_path']==list(path))
        assert item['content']==at(result.memo,path)
    html=render_consolidated_html(artifact)
    assert '123.4500' in html and 'Second paragraph.' in html and 'OFFLINE SYNTHETIC STRUCTURE' in html
    assert html.count('Industry detail.')==300
    assert backend.calls('m4_debt')==1
    # Wrong case with an existing run must never load it.
    with pytest.raises(ArtifactIntegrityError):
        from app.services.bo.consolidated import assemble
        assemble(db_session,case_id='foreign-case',run_id=result.analysis_run_id,version=result.snapshot_version)
    # Tamper outside ORM to prove recorded-chain protection, not just immutability hook.
    stage=db_session.scalar(select(StageArtifact).where(StageArtifact.name=='bo_consolidated:'+result.analysis_run_id))
    db_session.execute(text('UPDATE stage_artifacts SET payload_json=:p WHERE case_id=:c AND evidence_version=:v AND name=:n'),
                       {'p':'{}','c':stage.case_id,'v':stage.evidence_version,'n':stage.name})
    db_session.expire_all()
    with pytest.raises(ArtifactIntegrityError):
        load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)


@pytest.mark.parametrize('fault',['number','unknown_basis','missing_decision','duplicate','unqualified'])
def test_invalid_selection_never_presented(db_session,tmp_path,fault):
    answers=script()
    data=answers['orchestrate']
    if fault=='number': data['key_drivers'][0]['text']='Revenue rose 987654321 percent.'
    elif fault=='unknown_basis': data['key_drivers'][0]['hypothesis_ids']=['NONEXISTENT']
    elif fault=='missing_decision': data['selections'].pop()
    elif fault=='duplicate': data['key_drivers'][1]=copy.deepcopy(data['key_drivers'][0])
    else: data['key_drivers'][2]['uncertainty']=None
    result,backend=run(db_session,tmp_path,answers=answers)
    artifact=load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)
    assert artifact['sections'][2]['synthesis'] is None
    assert backend.calls('orchestrate')==2
    assert backend.calls('challenge')==0
    assert result.conclusion_status in {'unavailable','human_review_required'}


def test_challenger_defect_remains_visible(db_session,tmp_path):
    answers=script()
    answers['challenge']={'challenges':[dict(challenge_id='semantic-defect',target='point-0',
        issue_type='ignored_counterevidence',severity='material',reason='Material competitive counterevidence omitted.',
        requires_reanalysis=False)]}
    result,backend=run(db_session,tmp_path,answers=answers)
    artifact=load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)
    assert result.conclusion_status=='human_review_required'
    assert artifact['challenge']['findings'][0]['reason']=='Material competitive counterevidence omitted.'
    assert backend.calls('challenge')==1


def test_failed_shortfall_repair_retains_supported_points(db_session,tmp_path):
    answers=script(2)
    invalid=copy.deepcopy(answers['orchestrate'])
    invalid['key_drivers'][0]['text']='An unsupported 987654321 percent benefit.'
    answers['orchestrate']=[answers['orchestrate'],invalid]
    result,backend=run(db_session,tmp_path,answers=answers)
    artifact=load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)
    assert len(artifact['sections'][2]['synthesis']['key_drivers'])==2
    assert '987654321' not in render_consolidated_html(artifact)
    assert backend.calls('orchestrate')==2 and backend.calls('challenge')==1


def test_new_review_and_exports_share_five_sections(db_session,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.api.deps import get_session
    from app.services import bo_fo
    result,_=run(db_session,tmp_path)
    job=dict(job_id='consolidated-job',case_id=h.CASE,status='finished',execution_status='completed',
             bo_only=True,fo_only=False,bo_validators=True,metadata={'company':'OFFLINE FIXTURE'},
             run_ids={'bo':result.analysis_run_id},result={})
    monkeypatch.setattr(bo_fo.jobs,'get',lambda key:job if key==job['job_id'] else None)
    app=create_app()
    app.dependency_overrides[get_session]=lambda:db_session
    with TestClient(app) as client:
        paths=[f'/analysis/{job["job_id"]}/review',
               f'/cases/{h.CASE}/bo/runs/{result.analysis_run_id}/memo.html']
        for path in paths:
            response=client.get(path)
            assert response.status_code==200,response.text
            from lxml import html
            headings=html.fromstring(response.text).xpath('//h2/text()')
            assert headings==list(TITLES)
            assert 'Executive Business Credit Assessment' not in response.text
        response=client.get(f'/cases/{h.CASE}/bo/runs/{result.analysis_run_id}/consolidated.json')
        assert response.status_code==200
        assert response.json()['analysis_run_id']==result.analysis_run_id
        response=client.get(f'/analysis/{job["job_id"]}/audit')
        assert response.status_code==200
        assert 'Competitive Position candidate selection decisions' in response.text


@pytest.mark.parametrize('fault',['case','run','source_hash','copy','approval','selection'])
def test_correctly_rehashed_forgery_rejected(db_session,tmp_path,fault):
    from app.models.orm import StageArtifact
    from app.services.pipeline.artifacts import chain_value,ArtifactIntegrityError
    from app.core.hashing import canonical_json
    from sqlalchemy import select,text
    from pydantic import ValidationError
    result,_=run(db_session,tmp_path)
    stage=db_session.scalar(select(StageArtifact).where(StageArtifact.name=='bo_consolidated:'+result.analysis_run_id))
    data=json.loads(stage.payload_json)
    if fault=='case':data['case_id']='foreign-case'
    elif fault=='run':data['analysis_run_id']='foreign-run'
    elif fault=='source_hash':data['sources'][0]['sha256']='0'*64
    elif fault=='copy':data['sections'][4]['items'][0]['content'][0]['claim']='Forged industry prose'
    elif fault=='approval':data['governance']['human_review_status']='accepted'
    else:data['sections'][2]['synthesis']['key_drivers'][0]['text']='Forged selected insight'
    digest=content_hash(data)
    db_session.execute(text('UPDATE stage_artifacts SET payload_json=:p,sha256=:s,chain_hash=:h WHERE case_id=:c AND evidence_version=:v AND name=:n'),
        dict(p=canonical_json(data),s=digest,h=chain_value(stage.name,stage.ordinal,digest,stage.previous_hash),
             c=stage.case_id,v=stage.evidence_version,n=stage.name))
    db_session.expire_all()
    with pytest.raises((ArtifactIntegrityError,ValidationError)):
        load(db_session,h.CASE,result.analysis_run_id,result.snapshot_version)
