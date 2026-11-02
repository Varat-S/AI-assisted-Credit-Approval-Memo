"""Native styling keeps existing theme controls, layout and frozen content."""
from copy import deepcopy
from pathlib import Path
import re
import pytest
from lxml import html
from app.core.hashing import content_hash
from app.schemas.bo_consolidated import TITLES
from app.services.bo.reporting import render_consolidated_html
from app.services.bo.consolidated import load
from tests.fixtures.bo_editorial import build_run

@pytest.mark.parametrize('name',[
    'app/services/reporting/templates/bo_consolidated_style.html.j2',
    'app/services/reporting/templates/bo_consolidated.html.j2',
    'app/api/templates/analysis_review.html.j2'])
def test_no_independent_report_theme(name):
    source=Path(name).read_text()
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b',source)
    assert 'font-family' not in source
    assert 'Georgia' not in source
    assert 'consolidated-page' not in source


def test_native_export_preserves_layout_and_complete_analysis(db_session,tmp_path):
    result,job,_=build_run(db_session,tmp_path)
    artifact=load(db_session,result.case_id,result.analysis_run_id,result.snapshot_version)
    original=deepcopy(artifact)
    page=html.fromstring(render_consolidated_html(artifact))
    assert content_hash(artifact)==content_hash(original)
    assert page.xpath('//h2/text()')==list(TITLES)
    assert page.xpath('//article[@class="memo-paper"]')
    assert page.xpath('//table[contains(@class,"memo-table")]')
    assert len(page.xpath('//li[@class="bo-event"]'))==4
    assert '--c-315e62' in page.text_content()
    assert "localStorage.getItem('theme')" in page.text_content()
    for point in artifact['sections'][2]['synthesis']['key_drivers']:
        assert all(text in page.text_content() for text in point['analysis'].values())
    assert artifact['governance']['human_review_status']=='pending'
