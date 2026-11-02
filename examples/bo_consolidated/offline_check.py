import sys, types, socket, os
sys.path.insert(0,os.getcwd())
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
# The shared environment's optional PDF dependency stalls loading an on-demand
# file. This test slice does not extract PDFs. Fail explicitly if it tries.
pdf=types.ModuleType('pdfplumber')
def denied(*a,**kw):
    raise AssertionError('External network/PDF extraction is disabled for this offline BO slice')
pdf.open=denied
sys.modules['pdfplumber']=pdf
socket.socket.connect=denied
socket.create_connection=denied
import faulthandler
faulthandler.dump_traceback_later(20)
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
