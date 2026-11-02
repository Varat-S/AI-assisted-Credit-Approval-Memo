"""Review reuses existing recorded Financial Overview; scripted fixture only."""
import copy
from fastapi.testclient import TestClient
from app.main import create_app
from app.api.deps import get_session
from app.services import bo_fo
from app.services.fo.memo import build_memo
from app.services.fo.review import run_header
from app.models.orm import FinancialOverviewRunRow
from tests.integration.test_analysis_review_workspace import seed_run
from tests.integration.test_fo_runner_api import filings_root, use_filings_root, nvda_as_hospital, runner, FOLDER


def test_review_financial_payload_and_exact_run_integrity(db_session,nvda_as_hospital,monkeypatch):
    job=seed_run(db_session,'combined',1)
    result=runner(db_session).run_filing(FOLDER,'HCA_2024')
    row=db_session.get(FinancialOverviewRunRow,result.run_id)
    expected=build_memo(row.payload,run=run_header(row))
    job['bo_only']=False;job['result']['fo']={'status':'completed','summary':{'run_id':result.run_id}}
    class Records:
        def get(self,ident):return copy.deepcopy(job) if ident=='combined' else None
    monkeypatch.setattr(bo_fo,'jobs',Records())
    app=create_app();app.dependency_overrides[get_session]=lambda:db_session
    with TestClient(app) as client:
        response=client.get('/analysis/combined/review')
        assert response.status_code==200,response.text
        from lxml import html
        text=html.fromstring(response.text).text_content()
        assert expected['executive']['headline'] in text
        assert 'Financial Overview' in text and 'Debt service coverage ratio (DSCR)' in text
        assert f'/fo/runs/{result.run_id}/memo.html' in response.text
        tiles=[(t.findtext('span'),t.findtext('strong')) for t in html.fromstring(response.text).xpath('//div[@class="memo-scores"]/div')]
        composite=expected['executive']['composite']
        assert tiles==[('Composite risk score',f"{composite['text']} / 10"),('Indicative rating',composite['rating']),
                       ('Risk level',composite['label'].capitalize())]
        assert 'not an agency rating' in text
        # A combined analysis shows RMS; none is assessed for these runs yet.
        assert "No Risk Mitigation & Structuring assessment of this analysis's runs is recorded" in text
        assert 'href="/analysis/combined/rms"' in response.text
        row.case_id='OTHER';db_session.flush()
        assert client.get('/analysis/combined/review').status_code==409
        row.case_id='HCA_2024';row.payload={**row.payload,'unexpected':'tamper'};db_session.flush()
        assert client.get('/analysis/combined/review').status_code==409
