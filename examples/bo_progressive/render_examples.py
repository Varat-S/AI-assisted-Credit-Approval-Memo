"""Render existing saved artifacts; never creates or reruns an analysis."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,os.getcwd())
from app.services.bo.reporting import render_consolidated_html
root=Path(__file__).parent
for name in ('newly-completed','historical'):
    data=json.loads(Path('examples/bo_corrective',name+'.json').read_text())
    for expanded in (False,True):
        suffix='-expanded' if expanded else ''
        (root/(name+suffix+'.html')).write_text(render_consolidated_html(data,expand_evidence=expanded))
