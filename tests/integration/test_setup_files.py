"""SEC acquisition wiring and corporate uploads, with no network or paid AI calls."""
import json
import shutil
from types import SimpleNamespace

import pytest
from app.api import analysis
from app.services import setup_files
from app.services.acquisition.sec_edgar import EdgarError
from tests.integration.test_analysis_workspace import evidence, workspace

HEADERS={'X-Requested-With':'setup-files'}


def structure(company='HCA Healthcare', status='simulated_educational_example'):
    return {'schema_version':'1.0','document_type':'corporate_structure_onboarding',
            'company_name':company,'data_status':status,
            'corporate_tree':{'id':'root','name':company,'role':'Borrower','is_guarantor':False}}


def test_existing_download_is_verified_without_contact_or_network(workspace, monkeypatch):
    monkeypatch.setattr(analysis,'_edgar_client',lambda *a:pytest.fail('No SEC request for an existing filing'))
    response=workspace.post('/analysis/new/download-files',headers=HEADERS)
    assert response.status_code==200
    assert response.json()['results'][0]['status']=='Already available'
    assert 'download_url' not in response.json()


def test_download_missing_contact_then_fetches_sec(workspace,evidence,monkeypatch,tmp_path):
    saved=tmp_path/'saved'
    shutil.move(evidence,saved)
    monkeypatch.setattr(analysis,'_contact',lambda text:text)
    response=workspace.post('/analysis/new/download-files',headers=HEADERS)
    assert response.status_code==422 and response.json()['needs_contact']
    client=object()
    monkeypatch.setattr(analysis,'_edgar_client',lambda session,contact:client)
    def select(actual,ticker,**kwargs):
        assert actual is client and ticker=='HCA' and kwargs=={'fy':2024}
        from datetime import date
        return {},[],SimpleNamespace(cik='860730',report_date=date(2024,12,31),accession='0000000001-25-000001')
    def fetch(actual,ticker,**kwargs):
        assert actual is client and kwargs['with_proxy'] is True
        assert kwargs['accession']=='0000000001-25-000001'
        shutil.copytree(saved,evidence)
        return SimpleNamespace(name=evidence.name)
    monkeypatch.setattr(setup_files.shared_filing,'select_annual_filing',select)
    monkeypatch.setattr(setup_files.shared_filing,'fetch_filing',fetch)
    response=workspace.post('/analysis/new/download-files',data={'user_agent':'analyst@example.com'},headers=HEADERS)
    assert response.status_code==200
    assert response.json()['results'][0]['status']=='Downloaded from SEC'
    assert evidence.is_dir()


def test_sec_failure_does_not_report_success(workspace,evidence,monkeypatch,tmp_path):
    shutil.move(evidence,tmp_path/'saved')
    monkeypatch.setattr(analysis,'_edgar_client',lambda *a:object())
    def unavailable(*a,**kw): raise EdgarError('SEC temporarily unavailable')
    monkeypatch.setattr(setup_files.shared_filing,'select_annual_filing',unavailable)
    response=workspace.post('/analysis/new/download-files',data={'user_agent':'analyst@example.com'},headers=HEADERS)
    assert response.json()['results'][0]['status']=='Failed'
    assert not evidence.exists()


def test_structure_upload_is_associated_and_used_by_module3(workspace,evidence):
    doc=structure()
    response=workspace.post('/analysis/new/corporate-structure',data={'company':'hca'},
        files={'file':('structure.json',json.dumps(doc),'application/json')},headers=HEADERS)
    assert response.status_code==200 and response.json()['simulated']
    from app.services.acquisition.shared_filing import m3_structure_path,load_bundle
    from app.services import bo_fo
    assert json.loads(m3_structure_path(evidence.name).read_bytes())==doc
    bundle=load_bundle(evidence.name)
    # The same association helper called by BO execution admits this saved input.
    from app.services.pipeline.package import SourcePackage
    package=SourcePackage.load(evidence/'package.json')
    result=bo_fo.m3_package(package,evidence.name,bundle)
    assert result.module3.corporate_source=='m3_corporate_structure.json'


@pytest.mark.parametrize('data', [b'not json', json.dumps(structure('Other Company')).encode(),
    json.dumps({'schema_version':'1.0'}).encode(), b'x'*(1024*1024+1)])
def test_invalid_upload_preserves_existing_file(workspace,evidence,data):
    target=evidence/'m3_corporate_structure.json'
    original=json.dumps(structure()).encode();target.write_bytes(original)
    response=workspace.post('/analysis/new/corporate-structure',data={'company':'hca'},
        files={'file':('structure.json',data,'application/json')},headers=HEADERS)
    assert response.status_code==400 and target.read_bytes()==original


def test_upload_replacement_keeps_history(workspace,evidence,monkeypatch,tmp_path):
    from app.core import config
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(data_dir=tmp_path/'data'))
    old=json.dumps(structure()).encode();(evidence/'m3_corporate_structure.json').write_bytes(old)
    new=structure(status='user_supplied_unverified')
    response=workspace.post('/analysis/new/corporate-structure',data={'company':'hca'},
        files={'file':('structure.json',json.dumps(new),'application/json')},headers=HEADERS)
    assert response.status_code==200
    backups=list((tmp_path/'data'/'corporate_structure_history').rglob('*.json'))
    assert len(backups)==1 and backups[0].read_bytes()==old


def test_file_operations_require_app_header(workspace):
    assert workspace.post('/analysis/new/download-files').status_code==403
