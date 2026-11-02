"""Local-only offline fixture preview over the actual application routes.
No production database, worker, live provider, or SEC acquisition is used.
Run from the repository root. Temporary persisted stores are intentionally isolated.
"""
import os,sys,json,types,tempfile
from pathlib import Path
sys.path.insert(0,os.getcwd())
pdf=types.ModuleType('pdfplumber')
def forbidden(*a,**k):raise AssertionError('Live inference/acquisition/PDF extraction disabled for illustrative preview')
pdf.open=forbidden;sys.modules['pdfplumber']=pdf
from app.core.config import Settings,get_settings
Settings.model_config['env_file']=None;get_settings.cache_clear()
from app.models.base import create_engine_and_session,init_db
from app.services import bo_fo
from app.services.bo.consolidated import load
from app.services.bo.reporting import render_consolidated_html
from app.services.analysis_jobs import JobStore
from app.services.llm.providers import RealProviderBackend
from app.services.llm.providers_vertex import VertexProviderBackend
RealProviderBackend.generate=VertexProviderBackend.generate=forbidden
from app.services.acquisition.sec_edgar import UrllibTransport
UrllibTransport.get=forbidden
from tests.fixtures.bo_editorial import build_run
from tests.integration.test_analysis_review_workspace import seed_run
root=Path(tempfile.mkdtemp(prefix='bo-corrective-'))
engine,factory=create_engine_and_session('sqlite:///'+str(root/'preview.sqlite'));init_db(engine)
store=JobStore(root/'jobs.sqlite')
output=Path('examples/bo_corrective')
with factory() as session:
    for tag in ['historical','newly-completed']:
        result,job,_=build_run(session,root/tag,tag=tag)
        store.claim(job)
        artifact=load(session,job['case_id'],result.analysis_run_id,result.snapshot_version)
        (output/(tag+'.json')).write_text(json.dumps(artifact,indent=2)+'\n')
        (output/(tag+'-audit.json')).write_text(json.dumps(result.audit,indent=2)+'\n')
        (output/(tag+'.html')).write_text(render_consolidated_html(artifact))
    legacy=seed_run(session,'legacy',3);store.claim(legacy)
    session.commit()
bo_fo.jobs=bo_fo.Jobs(root/'jobs.sqlite')
bo_fo.run_bo_fo=forbidden
# Read-only application fixture: users can inspect normal Execution, Review,
# history, audit and export routes; paid run submission is disabled.
from app.main import create_app
from app.api.deps import get_session
app=create_app()
def isolated_session():
    with factory() as session:yield session
app.dependency_overrides[get_session]=isolated_session
from fastapi import Request
from fastapi.responses import JSONResponse
@app.middleware('http')
async def offline_only(request:Request,call_next):
    if request.method not in ('GET','HEAD'):
        return JSONResponse({'detail':'Read-only illustrative preview: run submission and approvals disabled.'},status_code=405)
    return await call_next(request)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8771)
