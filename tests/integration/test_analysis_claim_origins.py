"""M4A-02: classify only recorded coverage insertions, never claim naming."""
import copy
from contextlib import contextmanager
import pytest
from lxml import html
from app.models.orm import TopicConclusionRow
from app.services.analysis_workspace import load_review
from app.services.analysis_claims import COVERAGE_INSERTION_NOTE, ORIGIN_NOTICE
from tests.integration.test_bo_archive_identity import archive_workspace, stored_records

CATEGORIES = ['overall_assessment', 'strengths', 'weaknesses', 'key_drivers', 'material_risks']


def set_claim(audit, category, claim_id, text):
    payload = audit['conclusions'][0]['payload']
    claim = copy.deepcopy(payload['overall_assessment'])
    claim.update(claim_id=claim_id, text=text)
    if category == 'overall_assessment':
        payload[category] = claim
    else:
        payload[category] = [claim, *(payload.get(category) or [])]
    return claim


@pytest.fixture
def claims_workspace(archive_workspace, db_session):
    @contextmanager
    def factory(change=None, memo_change=None):
        def mutate(kind, payload):
            if kind == 'memo' and memo_change:
                memo_change(payload)
            if kind == 'audit':
                if change:
                    change(payload)
                final = next((c for c in payload.get('conclusions', [])
                              if c['conclusion_id'] == 'conclusion-selected'), None)
                if final:
                    row = db_session.get(TopicConclusionRow, 'conclusion-selected')
                    row.payload = copy.deepcopy(final['payload'])
                    row.acceptance_state = final['acceptance_state']
        with archive_workspace(change=mutate) as value:
            yield value
    return factory


def claim_record(document, claim_id):
    return document.xpath('//div[@class="audit-record"][strong/text()="' + claim_id + '"]')


@pytest.mark.parametrize('category', CATEGORIES)
@pytest.mark.parametrize('prefix', ['COV-', 'MODEL-'])
def test_valid_final_claims_preserved_in_every_category(claims_workspace, category, prefix):
    ident = prefix + 'MODEL-AUTHORED'
    text = 'Valid final assessment ' + category
    with claims_workspace(lambda a:set_claim(a, category, ident, text)) as (client, jobs, session):
        before = stored_records(session)
        review = client.get('/analysis/selected/review')
        audit = client.get('/analysis/selected/audit')
        assert review.status_code == audit.status_code == 200
        assert text in review.text and 'No validated Business Credit Assessment' not in review.text
        assert 'COPIED SPECIALIST selected' not in review.text
        assert 'AUDIT ONLY SPECIALIST selected' not in review.text
        view = load_review(session, jobs[-1])
        assert view['synthesis'] and view['reason'] is None
        assert view['governance'] == 'Human review required'
        assert ident not in view['excluded_claim_ids']
        assert ORIGIN_NOTICE in view['synthesis']['origin_notice']
        record = claim_record(html.fromstring(audit.text), ident)[0]
        assert 'Automatic specialist coverage copy' not in record.text_content()
        assert 'not separately classified' in record.text_content()
        document = html.fromstring(review.text)
        for href in document.xpath('//a[@class="source-cite"]/@href'):
            assert document.xpath('//*[@id="' + href[1:] + '"]')
        assert document.xpath('//a[text()="Audit & Review"]/@href') == ['/analysis/selected/audit']
        assert 'Synthesized assessment other' not in review.text
        assert stored_records(session) == before


@pytest.mark.parametrize('category', CATEGORIES)
@pytest.mark.parametrize('prefix', ['COV-', 'INSERTED-'])
def test_documented_insertions_excluded_by_provenance_in_every_category(claims_workspace, category, prefix):
    ident = prefix + 'INSERTED-COPY'
    text = 'Documented automatic copy ' + category
    def change(audit):
        set_claim(audit, category, ident, text)
        audit['agents'][0]['validator_adjustments'].append({'claim_id':ident,'note':COVERAGE_INSERTION_NOTE})
    with claims_workspace(change) as (client, jobs, session):
        before = stored_records(session)
        review = client.get('/analysis/selected/review')
        audit = client.get('/analysis/selected/audit')
        assert text not in review.text and text in audit.text
        view = load_review(session, jobs[-1])
        assert ident in view['excluded_claim_ids']
        record = claim_record(html.fromstring(audit.text), ident)[0]
        assert 'Automatic specialist coverage copy' in record.text_content()
        if category == 'overall_assessment':
            assert view['synthesis'] is None
            assert view['reason'] == 'The recorded overall assessment is an automatic specialist coverage copy.'
            assert view['governance'] == 'Unavailable or incomplete'
        else:
            assert view['synthesis'] and view['reason'] is None
        assert stored_records(session) == before


def test_mixed_claims_and_copy_only_citations_remain_in_audit(claims_workspace):
    def memo_change(memo):
        memo['sources'].append({'n':2,'evidence_id':'copy-only-evidence','filename':'copy-only-source.txt'})
    def change(audit):
        set_claim(audit,'overall_assessment','COV-MODEL-AUTHORED','Valid model assessment')
        copy_claim = set_claim(audit,'material_risks','NO-PREFIX-COPY','COPY ONLY NARRATIVE')
        copy_claim['evidence_ids'] = ['copy-only-evidence']
        audit['agents'][0]['validator_adjustments'].append({'claim_id':'NO-PREFIX-COPY','note':COVERAGE_INSERTION_NOTE})
    with claims_workspace(change,memo_change) as (client, _, session):
        before = stored_records(session)
        review = client.get('/analysis/selected/review');audit = client.get('/analysis/selected/audit')
        assert 'Valid model assessment' in review.text
        assert 'COPY ONLY NARRATIVE' not in review.text and 'COPY ONLY NARRATIVE' in audit.text
        assert 'copy-only-source.txt' not in review.text and 'copy-only-source.txt' in audit.text
        assert 'REJECTED SPECIALIST selected' not in review.text and 'REJECTED SPECIALIST selected' in audit.text
        assert stored_records(session) == before


@pytest.mark.parametrize('missing', ['adjustments','marker','history','producer','agent','agent_status',
                                     'last_rejected','run_reference','duplicate_agent','unrelated_note'])
def test_missing_or_ambiguous_provenance_is_retained_with_explicit_uncertainty(claims_workspace, missing):
    def change(audit):
        set_claim(audit,'overall_assessment','COV-MODEL-AUTHORED','Valid assessment with origin not classified')
        agent = audit['agents'][0]
        if missing == 'adjustments':agent.pop('validator_adjustments')
        elif missing == 'marker':agent['validator_adjustments'] = []
        elif missing == 'history':audit['orchestrator']['history'] = 'not_recorded'
        elif missing == 'producer':audit['orchestrator']['history'][-1]['agent_run_id'] = 'earlier-attempt'
        elif missing == 'agent':agent['agent_id'] = 'unrelated-specialist'
        elif missing == 'agent_status':agent['status'] = 'rejected'
        elif missing == 'last_rejected':audit['orchestrator']['history'][-1]['status'] = 'rejected'
        elif missing == 'run_reference':agent['runs'] = [{'agent_run_id':'earlier-attempt'}]
        elif missing == 'duplicate_agent':audit['agents'].append(copy.deepcopy(agent))
        elif missing == 'unrelated_note':agent['validator_adjustments'][0]['note'] = 'Some other validation adjustment.'
    with claims_workspace(change) as (client, jobs, session):
        view = load_review(session,jobs[-1])
        review = client.get('/analysis/selected/review');audit = client.get('/analysis/selected/audit')
        assert view['synthesis'] and view['reason'] is None and not view['excluded_claim_ids']
        assert 'Valid assessment with origin not classified' in review.text
        assert 'Individual claim origin is not separately classified' in review.text
        # This is already in the accepted conclusion, not appended from raw findings.
        assert 'COPIED SPECIALIST selected' in review.text
        assert 'AUDIT ONLY SPECIALIST selected' not in review.text
        assert 'Automatic specialist coverage copy' not in audit.text


@pytest.mark.parametrize('gate', ['missing_synthesis','rejected_synthesis','missing_challenge',
                                  'rejected_challenge','wrong_conclusion_challenge','exploratory'])
def test_required_governance_gates_still_apply_to_cov_claims(claims_workspace, gate):
    def change(audit):
        set_claim(audit,'overall_assessment','COV-MODEL-AUTHORED','DO NOT PRESENT WITHOUT GOVERNANCE')
        if gate == 'missing_synthesis':audit['conclusions'] = []
        elif gate == 'rejected_synthesis':audit['conclusions'][0]['acceptance_state'] = 'rejected'
        elif gate == 'missing_challenge':audit['challenger']['rounds'] = []
        elif gate == 'rejected_challenge':audit['challenger']['rounds'][0]['status'] = 'rejected'
        elif gate == 'wrong_conclusion_challenge':audit['challenger']['rounds'][0]['conclusion_id'] = 'another-conclusion'
    with claims_workspace(change) as (client,jobs,session):
        if gate == 'exploratory':jobs[-1]['bo_validators'] = False
        response = client.get('/analysis/selected/review')
        view = load_review(session,jobs[-1])
        assert response.status_code == 200 and view['synthesis'] is None and view['reason']
        assert 'No validated Business Credit Assessment is available for this run.' in response.text
        assert 'DO NOT PRESENT WITHOUT GOVERNANCE' not in response.text
        assert 'Final approval is prohibited' in response.text if gate == 'exploratory' else True


@pytest.mark.parametrize('prefix', ['COV-', 'ORDINARY-'])
def test_rejected_earlier_conclusion_is_not_promoted(claims_workspace, prefix):
    def change(audit):
        previous = copy.deepcopy(audit['conclusions'][0])
        previous.update(conclusion_id='rejected-conclusion',acceptance_state='rejected',orchestrator_run_id='old-producer')
        previous['payload']['orchestrator_run_id'] = 'old-producer'
        previous['payload']['overall_assessment'].update(claim_id=prefix+'REJECTED',text='REJECTED EARLIER CONCLUSION')
        audit['conclusions'].insert(0, previous)
    with claims_workspace(change) as (client,_,_):
        review = client.get('/analysis/selected/review');audit = client.get('/analysis/selected/audit')
        assert 'REJECTED EARLIER CONCLUSION' not in review.text and 'REJECTED EARLIER CONCLUSION' in audit.text
        assert 'Synthesized assessment selected' in review.text


def test_same_claim_id_on_old_producer_not_mislabelled_as_current_copy(claims_workspace):
    def change(audit):
        previous = copy.deepcopy(audit['conclusions'][0])
        previous.update(conclusion_id='old-conclusion',orchestrator_run_id='old-producer')
        previous['payload']['orchestrator_run_id'] = 'old-producer'
        audit['conclusions'].insert(0, previous)
    with claims_workspace(change) as (client,_,_):
        page = html.fromstring(client.get('/analysis/selected/audit').text)
        records = claim_record(page,'COV-hyp-selected')
        assert len(records) == 2
        assert 'Automatic specialist coverage copy' not in records[0].text_content()
        assert 'Automatic specialist coverage copy' in records[1].text_content()


def test_cov_identifier_collision_is_not_provenance(claims_workspace):
    def change(audit):
        set_claim(audit,'overall_assessment','COV-hyp-selected','Genuine assessment using coverage-like ID')
        copied = audit['conclusions'][0]['payload']['key_drivers'][1]
        copied['claim_id'] = 'COV-hyp-selected-2'
        audit['agents'][0]['validator_adjustments'][0]['claim_id'] = 'COV-hyp-selected-2'
    with claims_workspace(change) as (client,jobs,session):
        view = load_review(session,jobs[-1])
        assert view['synthesis']['assessment']['claim_id'] == 'COV-hyp-selected'
        assert view['excluded_claim_ids'] == ['COV-hyp-selected-2']
        response = client.get('/analysis/selected/review')
        assert 'Genuine assessment using coverage-like ID' in response.text
        assert 'COPIED SPECIALIST selected' not in response.text
