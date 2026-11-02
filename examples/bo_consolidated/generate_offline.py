import os,sys,types,socket,tempfile,json
from pathlib import Path
sys.path.insert(0,os.getcwd())
pdf=types.ModuleType('pdfplumber')
def blocked(*a,**k):raise AssertionError('Offline fixture: network/PDF extraction forbidden')
pdf.open=blocked
sys.modules['pdfplumber']=pdf
socket.socket.connect=blocked
from app.core.config import Settings,get_settings
Settings.model_config['env_file']=None
get_settings.cache_clear()
from app.models.base import create_engine_and_session,init_db
from app.services.bo.runner import BusinessOverviewRunner
from app.services.bo.offline import ScriptedBoBackend
from app.services.bo.consolidated import load
from tests.integration.test_bo_consolidated import script
from tests.integration.test_bo_m4_dual_specialist import _debt_evidence
from tests.fixtures.hca_module4 import hca_module4_output
from tests import bo_helpers as h
answers=script();answers['m4_debt']=hca_module4_output()
engine,factory=create_engine_and_session('sqlite://');init_db(engine)
with tempfile.TemporaryDirectory() as directory, factory() as session:
    result=BusinessOverviewRunner(session,backend=ScriptedBoBackend(answers),bo_roster='v3',
        consolidated=True,sector=None,enable_m4_debt_specialist=True,
        data_root=Path(directory)/'data',output_root=Path(directory)/'out').run_prepared(
            h.CASE,_debt_evidence(),h.metrics())
    artifact=load(session,h.CASE,result.analysis_run_id,result.snapshot_version)
    target=Path('examples/bo_consolidated')
    (target/'consolidated.json').write_text(json.dumps(artifact,indent=2)+'\n')
    (target/'audit.json').write_text(json.dumps(result.audit,indent=2)+'\n')
    (target/'preview.html').write_text(result.output_paths['business_overview.html'].read_text())
    from app.services.analysis_workspace import load_review, analysis_tabs
    from app.api.analysis import _env
    job=dict(job_id='offline-consolidated-preview',case_id=h.CASE,status='finished',execution_status='completed',
             bo_only=True,fo_only=False,bo_validators=True,metadata={'company':'OFFLINE SYNTHETIC FIXTURE'},
             run_ids={'bo':result.analysis_run_id},result={})
    (target/'review-preview.html').write_text(_env.get_template('analysis_review.html.j2').render(
        job=job,view=load_review(session,job),analysis=analysis_tabs(job,'memo')))
    from app.schemas.bo_consolidated import ConsolidatedBO,CompetitiveSynthesis
    (target/'artifact.schema.json').write_text(json.dumps(ConsolidatedBO.model_json_schema(),indent=2)+'\n')
    (target/'competitive.schema.json').write_text(json.dumps(CompetitiveSynthesis.model_json_schema(),indent=2)+'\n')
print('Wrote offline sample, full audit, schemas and HTML preview')
