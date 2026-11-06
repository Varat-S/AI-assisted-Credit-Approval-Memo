"""Native M2 output becomes categorized cards with finding-specific evidence."""
from copy import deepcopy

from lxml import html

from app.services.bo.four_section_view import load_view, render_page
from tests import competitive_positioning_helpers as cp
from tests.integration.test_bo_four_section_renderer import run


def test_native_industry_groups_and_exposures_render_without_rewriting_saved_findings(db_session, tmp_path, monkeypatch):
    answers = cp.script()
    finding = answers['m2_industry']['hypotheses'][0]
    finding['industry'] = {'kind': 'development', 'category': 'headwind', 'title': 'Reimbursement changes',
                           'state': 'structural', 'linked_development_ids': []}
    finding['interpretation'] = {'implication': 'Payment rules affect hospital revenue.',
                                 'company_response': None, 'watch_trigger': 'Legislative payment changes.'}
    exposure = deepcopy(finding)
    exposure.update(hypothesis_id='M2-H002', claim='We are subject to extensive regulation', direction='neutral',
                    industry={'kind': 'exposure', 'category': 'company_exposure', 'title': 'Regulatory exposure',
                              'state': 'structural', 'linked_development_ids': ['M2-H001']})
    answers['m2_industry']['hypotheses'].append(exposure)
    monkeypatch.setattr(cp, 'script', lambda: deepcopy(answers))
    result, _ = run(db_session, tmp_path)
    view = load_view(db_session, result.analysis_run_id)
    before = deepcopy(view['memo']['sections'][3]['content'])
    for pdf in [False, True]:
        root = html.fromstring(render_page(view, pdf=pdf))
        industry = root.xpath('//*[@data-memo-section="industry"]')[0]
        assert industry.xpath('.//*[@data-industry-category="tailwind"]//p[@class="memo-empty"]')
        assert len(industry.xpath('.//*[@data-industry-category="headwind"]//article[@data-industry-finding]')) == 1
        assert len(industry.xpath('.//*[@data-industry-category="company_exposure"]//article[@data-industry-finding]')) == 1
        assert industry.xpath('.//a[@href="#industry-M2-H001"]')
        assert 'Industry development' in industry.text_content()
        assert 'Effect on the company' in industry.text_content() and 'What to watch' in industry.text_content()
        assert 'Company response or offset' not in industry.text_content()
        if not pdf:
            panels = industry.xpath('.//article/details[@class="bo-evidence" and not(@open)]')
            assert len(panels) == 2
            assert all(p.xpath('.//blockquote') for p in panels)
        else:
            assert not industry.xpath('.//details')
    assert view['memo']['sections'][3]['content'] == before
