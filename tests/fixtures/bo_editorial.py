"""Authored synthetic example: real offline validators, never live company analysis."""
from copy import deepcopy
from unittest.mock import patch
from app.services.bo.m3_rebuild.structure import convert_structure
from app.services.bo.m3_rebuild.sources import sources_from_pages
from app.services.bo.m3_rebuild.management import assess_management
from app.services.bo.offline import ScriptedBoBackend
from app.services.bo.runner import BusinessOverviewRunner, _BoRun
from tests.integration.test_bo_consolidated import script
from tests.integration.test_bo_m4_dual_specialist import _debt_evidence
from tests.fixtures.hca_module4 import hca_module4_output
from tests.m3_rebuild.test_management import synthetic
from tests.m3_rebuild.review_fixtures import FixtureReviewer
from tests import bo_helpers as h


def structure_fixture():
    return convert_structure({
        'schema_version':'1.0','document_type':'corporate_structure_onboarding',
        'company_name':'Northfield Health Systems','data_status':'simulated_educational_example',
        'corporate_tree':{'id':'parent','name':'Northfield Health Systems','role':'Parent Co',
            'is_guarantor':True,'children':[
                {'id':'opco','name':'Northfield Operating Company','role':'Borrower','is_guarantor':False,
                 'ownership_percent_from_parent':100,'children':[
                     {'id':'hospital','name':'Northfield Hospital Subsidiary','role':'OpCo',
                      'is_guarantor':True,'ownership_percent_from_parent':100,'children':[]}]}]}})


def management_fixture():
    payload,old=synthetic()
    pages=[p.replace('Example Corp','Northfield Health Systems').replace('December 31, 2024','December 31, 2025')
           for p in old.pages.values()]
    sources=sources_from_pages(pages,'Northfield Health Systems','2025-12-31')
    return assess_management(payload,sources,reviewer=FixtureReviewer())


def build_run(session, root, *, tag='current'):
    answers=script()
    answers['m4_debt']=hca_module4_output()
    # The existing reduced debt fixture is replayed unchanged. It is HCA-shaped
    # example data and is explicitly described as illustrative in every demo job.
    structure,management=structure_fixture(),management_fixture()
    original=_BoRun._build_module_conclusions
    def modules(run):
        out=original(run)
        out['M3']['m3_rebuild']={
            'structure':{'artifact':deepcopy(structure),'status':'complete','validation_status':'passed'},
            'management':{'artifact':deepcopy(management),'status':'complete','validation_status':'passed'}}
        out['M3']['status']='incomplete'
        out['M3']['missing_information']=['Illustrative saved Module 3 fixtures; production Module 3 acquisition was not executed in this replay.']
        return out
    backend=ScriptedBoBackend(answers)
    with patch.object(_BoRun,'_build_module_conclusions',modules):
        result=BusinessOverviewRunner(session,backend=backend,bo_roster='v3',consolidated=True,
            sector=None,enable_m4_debt_specialist=True,data_root=root/'data',output_root=root/'out').run_prepared(
                h.CASE,_debt_evidence(),h.metrics())
    job=dict(job_id='editorial-'+tag,case_id=h.CASE,status='finished',execution_status='completed',
        bo_only=True,fo_only=False,bo_validators=True,created_at='2026-11-02T00:00:00Z',finished_at='2026-11-02T00:01:00Z',
        folder='Illustrative fixture',metadata={'company':'Northfield Health Systems · '+tag,
        'test_state':'ILLUSTRATIVE SYNTHETIC REPLAY — fictional Module 1/3 evidence and a reduced HCA-shaped Module 4 test fixture; no live company verification.',
        'reporting_period':'2025-12-31'},run_ids={'bo':result.analysis_run_id},
        result={'bo':{'status':'completed','summary':{'analysis_run_id':result.analysis_run_id}},'fo':{'status':'skipped'}})
    return result,job,backend
