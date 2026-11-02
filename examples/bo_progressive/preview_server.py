"""Read-only UI verification over previously persisted offline fixture runs.
Usage: python examples/bo_progressive/preview_server.py /path/to/existing/fixture-store
Never seeds, reruns, rewrites or regenerates an analysis.
"""
import os,sys
from pathlib import Path
sys.path.insert(0,os.getcwd())
from app.core.config import Settings,get_settings
Settings.model_config['env_file']=None;get_settings.cache_clear()
root=Path(sys.argv[1]).resolve()
if not (root/'preview.sqlite').is_file() or not (root/'jobs.sqlite').is_file():
    raise RuntimeError('Existing offline fixture database and sidecar are required')
def forbidden(*args,**kwargs):raise AssertionError('Read-only offline styling preview: inference and acquisition forbidden')
from app.services.llm.providers import RealProviderBackend
from app.services.llm.providers_vertex import VertexProviderBackend
from app.services.acquisition.sec_edgar import UrllibTransport
RealProviderBackend.generate=VertexProviderBackend.generate=UrllibTransport.get=forbidden
from app.models.base import create_engine_and_session
from app.services import bo_fo
engine,factory=create_engine_and_session('sqlite:///'+str(root/'preview.sqlite'))
bo_fo.jobs=bo_fo.Jobs(root/'jobs.sqlite');bo_fo.run_bo_fo=forbidden
from app.main import create_app
from app.api.deps import get_session
app=create_app()
def sessions():
    with factory() as session:yield session
app.dependency_overrides[get_session]=sessions
from fastapi import Request
from fastapi.responses import JSONResponse
@app.middleware('http')
async def read_only(request:Request,call_next):
    if request.method not in ('GET','HEAD'):
        return JSONResponse({'detail':'Read-only styling preview; analysis and approval writes disabled.'},status_code=405)
    return await call_next(request)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8773)
