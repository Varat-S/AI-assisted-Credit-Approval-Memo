"""UI-only execution refinement: synthetic states, no providers or persistence changes."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from lxml import html
from app.api import analysis

TEMPLATES=Path(analysis.__file__).parent/'templates'
JS_ENGINE=shutil.which('jsc') or shutil.which('node') or '/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc'


def job(*,bo_only=False,states=None,section='running',execution='running',stop=False):
    stages={
        'foundation':'completed','primary_specialists':'running','reconciliation':'pending',
        'orchestrator':'pending','challenger':'pending','memo_preparation':'pending',**(states or {})}
    return dict(job_id='technical-job-id',started_at='2026-11-01T12:00:00Z',created_at='2026-11-01T11:59:00Z',
                metadata={'company':'HCA Healthcare (HCA)','reporting_period':'2024-12-31'},
                folder='HCA 10-K FY2024',case_id='HCA',bo_only=bo_only,bo_validators=True,
                execution_status=execution,memo_status='human_review_required',stop_requested=stop,
                error=None,result=None,cost={},sections={'bo':{'status':section}},
                stages={**{'bo:'+key:{'section':'bo','status':value,'label':key,'order':index}
                           for index,(key,value) in enumerate(stages.items())},
                        'fo:workflow':{'section':'fo','label':'Financial preparation, analysis and validation','status':'running','order':0},
                        'fo:reporting':{'section':'fo','label':'Financial reporting','status':'pending','order':1000}},events=[])


def presentation(tmp_path,value,function="businessProgress"):
    if not Path(JS_ENGINE).is_file():pytest.skip('JavaScript runtime required for frontend state tests')
    code=(TEMPLATES/'analysis_execution_progress.js.j2').read_text(encoding='utf-8')
    script=tmp_path/'presentation.js'
    script.write_text(code+'\nvar output=JSON.stringify('+function+'('+json.dumps(value)+'));\n'
                      +("print(output);" if Path(JS_ENGINE).name=='jsc' else 'console.log(output);'),encoding='utf-8')
    completed=subprocess.run([JS_ENGINE,str(script)],capture_output=True,text=True,encoding='utf-8',check=True)
    return json.loads(completed.stdout)


def page(value):
    return html.fromstring(analysis._env.get_template('analysis_execution.html.j2').render(
        job=value, analysis=analysis.analysis_workspace.analysis_tabs({'job_id':'job-1',**value}, 'execution')))


def test_summary_has_only_requested_fields_and_consistent_buttons():
    document=page(job())
    summary=document.xpath('//section[@aria-label="Analysis summary"]')[0]
    assert summary.xpath('.//dt/text()')==['Company','Analysis Scope','Validation Mode']
    assert summary.xpath('.//dd/text()')==['HCA Healthcare (HCA)','Business + Financial Overview','Standard']
    for forbidden in ['2024-12-31','technical-job-id','2026-11-01','Execution:','Credit Memo:']:
        assert forbidden not in summary.text_content()
    assert summary.xpath('.//a[contains(@class,"execution-button")]/@href')==['/','/credit-memos']
    assert summary.xpath('.//a[contains(@class,"accent")]/text()')==['Credit Memos']
    assert summary.xpath('.//button[contains(@class,"destructive")]/text()')==['Stop Analysis']
    assert summary.xpath('.//form/@method')==['post']
    assert summary.xpath('.//form/@action')==['/analysis/technical-job-id/stop']
    assert not document.xpath('//details[@open]')


def test_two_matching_bars_per_section_with_accessible_labels():
    document=page(job())
    bo=document.xpath('//section[@aria-labelledby="bo-title"]')[0]
    assert len(bo.xpath('.//progress'))==2
    assert bo.xpath('.//label/text()')==['1. Evidence Preparation','2. Specialist Findings']
    assert bo.xpath('.//progress/@aria-describedby')==['preparation-state','findings-state']
    for forbidden in ['Orchestrator','Challenger','Memo Preparation','Cross-module','Job ID']:
        assert forbidden not in bo.text_content()
    assert document.xpath('//*[@id="fo-stages"]')
    fo=document.xpath('//section[@aria-labelledby="fo-title"]')[0]
    assert fo.xpath('.//label/text()')==['1. Financial Preparation, Analysis & Validation','2. Financial Reporting']
    assert fo.xpath('.//progress/@aria-describedby')==['financial-preparation-state','financial-reporting-state']
    assert len(fo.xpath('.//div[@class="bo-progress-row"]'))==2
    assert len(bo.xpath('.//div[@class="bo-progress-row"]'))==2
    assert len(document.xpath('//progress'))==4


def test_fo_only_scope_hides_business_overview_progress():
    value=job();value['fo_only']=True
    document=page(value)
    assert document.xpath('//dd/text()')[1]=='Financial Overview Only'
    assert document.xpath('//*[@id="fo-stages"]')
    assert document.xpath('//section[@aria-labelledby="bo-title"]/@hidden')


def test_bo_only_scope_and_exploratory_label():
    value=job(bo_only=True);value['bo_validators']=False
    document=page(value)
    assert document.xpath('//dd/text()')==['HCA Healthcare (HCA)','Business Overview Only','Exploratory']
    assert not document.xpath('//*[@id="fo-stages"]')
    assert document.xpath('//div[contains(@class,"bo-only")]')


@pytest.mark.parametrize('execution', ['completed','failed','stopped','interrupted'])
def test_stop_hidden_for_terminal_jobs(execution):
    assert page(job(execution=execution)).xpath('//form[@id="stop-form"][@hidden]')


def test_stop_disabled_while_request_pending():
    assert page(job(stop=True)).xpath('//button[@id="stop-button"][@disabled]')


@pytest.mark.parametrize('state,expected', [('pending','pending'),('running','running'),('completed','completed'),('failed','failed'),('stopped','stopped')])
def test_evidence_uses_recorded_foundation_state(tmp_path,state,expected):
    assert presentation(tmp_path,job(states={'foundation':state}))['preparation']==expected


def test_retrieval_keeps_evidence_active_after_foundation(tmp_path):
    assert presentation(tmp_path,job(states={'follow_up_retrieval':'running'}))['preparation']=='running'


def test_specialists_wait_for_validation_reconciliation(tmp_path):
    value=job(states={'primary_specialists':'completed','reconciliation':'running'})
    assert presentation(tmp_path,value)['findings']=='running'
    value['stages']['bo:reconciliation']['status']='completed'
    view=presentation(tmp_path,value)
    assert view['findings']=='completed' and view['complete'] is False
    assert view['message']=='Finalising credit assessment…'


@pytest.mark.parametrize('stage', ['orchestrator','challenger','memo_preparation'])
def test_hidden_work_shows_finalising_without_completion(tmp_path,stage):
    view=presentation(tmp_path,job(states={'primary_specialists':'completed','reconciliation':'completed',stage:'running'}))
    assert view['findings']=='completed'
    assert view['complete'] is False and view['message']=='Finalising credit assessment…'


@pytest.mark.parametrize('stage', ['orchestrator','challenger','memo_preparation'])
def test_hidden_failure_is_visible_even_if_worker_reports_completion(tmp_path,stage):
    value=job(states={'primary_specialists':'completed','reconciliation':'completed',stage:'failed'},section='completed',execution='completed')
    view=presentation(tmp_path,value)
    assert view['status']=='failed' and view['complete'] is False
    assert 'could not be completed' in view['message']


def test_actual_memo_and_section_completion_required(tmp_path):
    value=job(states={key:'completed' for key in ['primary_specialists','reconciliation','orchestrator','challenger','memo_preparation']})
    assert presentation(tmp_path,value)['complete'] is False # still committing the report
    value['sections']['bo']['status']='completed'
    view=presentation(tmp_path,value)
    assert view['complete'] and view['status']=='completed'
    assert 'Human review remains required' in view['message']
    value['result']={'bo':{'summary':{'has_synthesis':False}}}
    assert not presentation(tmp_path,value)['complete']


def test_bounded_repair_does_not_leave_a_stale_failure(tmp_path):
    value=job(states={'primary_specialists':'completed','reconciliation':'completed','orchestrator':'failed',
                      'orchestrator_validation_repair':'completed','challenger':'running'})
    value['events']=[{'section':'bo','stage':'orchestrator','status':'failed'},
                     {'section':'bo','stage':'orchestrator_validation_repair','status':'completed'},
                     {'section':'bo','stage':'challenger','status':'running'}]
    view=presentation(tmp_path,value)
    assert view['status']=='running' and view['message']=='Finalising credit assessment…'


def test_later_remediation_uses_latest_real_specialist_events(tmp_path):
    value=job(states={'primary_specialists':'completed','reconciliation':'completed','rerun_primary_specialists':'running'})
    value['events']=[{'section':'bo','stage':'primary_specialists','status':'completed'},
                     {'section':'bo','stage':'rerun_primary_specialists','status':'running'}]
    assert presentation(tmp_path,value)['findings']=='running'


@pytest.mark.parametrize('stage', ['workflow','reporting'])
@pytest.mark.parametrize('state', ['pending','running','completed','failed','stopped','interrupted','skipped'])
def test_financial_bars_follow_recorded_stage_states(tmp_path,stage,state):
    value=job()
    value['stages']['fo:'+stage]['status']=state
    view=presentation(tmp_path,value,'financialProgress')
    assert view['preparation' if stage=='workflow' else 'reporting']==state


def test_financial_workflow_completion_does_not_complete_reporting(tmp_path):
    value=job()
    value['stages']['fo:workflow']['status']='completed'
    value['stages']['fo:reporting']['status']='running'
    assert presentation(tmp_path,value,'financialProgress')=={'preparation':'completed','reporting':'running'}
    value['sections']['fo']={'status':'completed'}
    assert presentation(tmp_path,value,'financialProgress')['reporting']=='running' # wait for its actual end event


def test_financial_latest_event_overrides_stale_stage_snapshot(tmp_path):
    value=job()
    value['events']=[{'section':'fo','stage':'workflow','status':'running'},
                     {'section':'fo','stage':'workflow','status':'completed'}]
    assert presentation(tmp_path,value,'financialProgress')['preparation']=='completed'


def test_financial_individual_check_failure_is_not_left_running(tmp_path):
    value=job()
    value['stages']['fo:check']={'section':'fo','status':'failed'}
    assert presentation(tmp_path,value,'financialProgress')['preparation']=='failed'


@pytest.mark.parametrize('terminal', ['failed','stopped','interrupted'])
def test_financial_terminal_states_preserve_completed_work(tmp_path,terminal):
    value=job(execution=terminal)
    value['sections']['fo']={'status':terminal}
    value['stages']['fo:workflow']['status']='completed'
    value['stages']['fo:reporting']['status']='running'
    assert presentation(tmp_path,value,'financialProgress')=={'preparation':'completed','reporting':terminal}


def test_financial_recovery_stopped_marker_displays_interrupted(tmp_path):
    value=job(execution='interrupted')
    value['stages']['fo:workflow']['status']='stopped'
    value['stages']['fo:reporting']['status']='stopped'
    assert presentation(tmp_path,value,'financialProgress')=={'preparation':'interrupted','reporting':'interrupted'}


def test_financial_stop_request_does_not_fabricate_checkpoint_acknowledgement(tmp_path):
    assert presentation(tmp_path,job(stop=True),'financialProgress')=={'preparation':'running','reporting':'pending'}


def test_business_bars_fill_from_finished_parts_and_name_the_current_step(tmp_path):
    value=job(states={'foundation':'pending','primary_specialists':'pending'})
    value['sections']['bo']['step']='starting'
    view=presentation(tmp_path,value,'businessDetail')
    assert view=={'preparation':0,'findings':0,'activity':'Current step: Preparing the evidence package'}
    value['events']=[{'section':'bo','stage':'foundation','status':'running'},
                     {'section':'bo','stage':'management_analysis_and_validator7','status':'running'}]
    view=presentation(tmp_path,value,'businessDetail')
    assert view['preparation'] is None and view['activity']=='Current step: Management analysis & validation'
    value['events']+=[{'section':'bo','stage':'management_analysis_and_validator7','status':'completed'}]
    view=presentation(tmp_path,value,'businessDetail')
    assert view['preparation']==50 and view['activity']=='Current step: Preparing evidence'
    value['events']+=[{'section':'bo','stage':'foundation','status':'completed'},
                      {'section':'bo','stage':'primary_specialists','status':'completed'},
                      {'section':'bo','stage':'resilience','status':'running'}]
    view=presentation(tmp_path,value,'businessDetail')
    assert view=={'preparation':100,'findings':25,'activity':'Current step: Resilience assessment'}


@pytest.mark.parametrize('stage', ['orchestrator','rerun_challenger','memo_preparation'])
def test_business_step_text_keeps_final_stages_together(tmp_path,stage):
    value=job(states={'primary_specialists':'completed','reconciliation':'completed'})
    value['events']=[{'section':'bo','stage':stage,'status':'running'}]
    view=presentation(tmp_path,value,'businessDetail')
    assert view['findings']==100 and view['activity']=='Current step: Finalising credit assessment'


def test_business_step_text_clears_when_the_run_ends(tmp_path):
    view=presentation(tmp_path,job(states={'primary_specialists':'failed'},section='failed',execution='failed'),'businessDetail')
    assert view['activity']=='' and view['findings']==0


def test_financial_bar_follows_the_runner_step_count(tmp_path):
    value=job()
    value['sections']['fo']={'status':'running','step':'the going-concern pre-check','work':{'done':0,'total':28}}
    assert presentation(tmp_path,value,'financialDetail')=={
        'preparation':None,'reporting':0,'activity':'Current step: The going-concern pre-check (step 1 of 28)'}
    value['sections']['fo'].update(step='the DSCR T2 check',work={'done':9,'total':28})
    assert presentation(tmp_path,value,'financialDetail')=={
        'preparation':33,'reporting':0,'activity':'Current step: The DSCR T2 check (step 10 of 28)'}
    value['stages']['fo:workflow']['status']='completed'
    value['stages']['fo:reporting']['status']='running'
    value['sections']['fo'].update(step='recording the run and writing its files',work={'done':27,'total':28})
    view=presentation(tmp_path,value,'financialDetail')
    assert view['preparation']==100 and view['reporting'] is None
    assert view['activity']=='Current step: Recording the run and writing its files (step 28 of 28)'
    value['stages']['fo:reporting']['status']='completed'
    value['sections']['fo']['status']='completed'
    assert presentation(tmp_path,value,'financialDetail')['activity']=='All Financial Overview steps are complete.'


def test_financial_failure_keeps_the_progress_it_reached(tmp_path):
    value=job(execution='failed')
    value['stages']['fo:workflow']['status']='failed'
    value['sections']['fo']={'status':'failed','work':{'done':14,'total':28}}
    assert presentation(tmp_path,value,'financialDetail')=={'preparation':52,'reporting':0,'activity':''}


def test_financial_missing_events_remain_pending_and_bo_only_omits_bars(tmp_path):
    value=job();value['stages']={};value['sections']['fo']={'status':'completed'}
    assert presentation(tmp_path,value,'financialProgress')=={'preparation':'pending','reporting':'pending'}
    assert len(page(job(bo_only=True)).xpath('//progress'))==2
