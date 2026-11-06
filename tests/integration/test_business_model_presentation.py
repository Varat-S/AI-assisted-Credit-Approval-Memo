"""Saved-run display with source popups; informational output never changes credit artifacts."""
from copy import deepcopy

from lxml import html

from app.models.orm import ModelRun, StageArtifact
from app.services.bo.business_model import run_description
from app.services.bo.four_section_view import load_view, render_page
from app.services.bo.workbench import bo_artifact
from app.services.llm.client import FakeLLMBackend
from app.prompts.business_model import NAME
from tests import four_section_helpers as f
from tests.integration.test_bo_four_section_renderer import run
from tests.unit.test_business_model import TEXT, answer


def test_saved_description_precedes_structure_with_exact_quotes_and_no_new_read_calls(db_session, tmp_path, monkeypatch):
    source = f.evidence()
    documents = deepcopy(source.documents)
    documents[0]['report_date'] = str(source.as_of_date)
    passage = deepcopy(source.narrative_evidence[0])
    passage.update(evidence_id='E1', text=TEXT, section='Item 1')
    source = source.model_copy(update={'documents': documents,
                                      'narrative_evidence': [*source.narrative_evidence, passage]})
    monkeypatch.setattr(f, 'evidence', lambda: source)
    result, _ = run(db_session, tmp_path)
    frozen = deepcopy(bo_artifact(db_session, result.analysis_run_id, 'four_section'))
    handoff = deepcopy(result.handoff)
    old_rows = [(r.name, r.sha256, r.payload_json) for r in db_session.query(StageArtifact)]
    backend = FakeLLMBackend();backend.register('analyze', answer(), key=NAME)
    description = run_description(db_session, result.analysis_run_id, backend)
    assert description['status'] == 'complete'
    now = {r.name: (r.sha256, r.payload_json) for r in db_session.query(StageArtifact)}
    assert all(now[name] == (digest, payload) for name, digest, payload in old_rows)
    assert bo_artifact(db_session, result.analysis_run_id, 'four_section') == frozen
    assert result.handoff == handoff
    count = db_session.query(ModelRun).count()
    monkeypatch.setattr(backend, 'generate', lambda *a: (_ for _ in ()).throw(AssertionError('No calls on reads')))
    view = load_view(db_session, result.analysis_run_id)
    for pdf in [False, True]:
        root = html.fromstring(render_page(view, pdf=pdf))
        sections = root.xpath('//*[@data-memo-section]')
        assert [s.get('data-memo-section') for s in sections][:2] == ['business_model', 'corporate_structure_debt_obligations']
        assert sections[0].xpath('.//h2')[0].text_content().strip() == '01 Business Model'
        assert sections[1].xpath('.//h2')[0].text_content().strip().startswith('02')
        assert answer()['paragraphs'][0]['sentences'][0]['text'] in sections[0].text_content()
        if not pdf:
            assert sections[0].xpath('.//details[@class="bo-evidence" and not(@open)]')
            assert TEXT in sections[0].xpath('.//blockquote')[0].text_content()
        else:
            assert not sections[0].xpath('.//details')
    assert db_session.query(ModelRun).count() == count
