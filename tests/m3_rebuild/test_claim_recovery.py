"""Backend recovery retains supported assertions without relaxing source integrity."""
from copy import deepcopy

from app.services.bo.m3_rebuild.claims import assess_claims
from app.services.bo.m3_rebuild.claim_support import appointment_clause, judgment_scope
from app.services.bo.m3_rebuild.contracts import validate_management
from .test_management import synthetic
from .review_fixtures import FixtureReviewer


def test_pronoun_appointment_is_bound_to_current_role_not_previous_job():
    text = ('Alex Sample serves as our Chief Executive Officer. He is responsible for operations. '
            'He has served in this role since December 2025, after serving as our interim CEO from October 2025 to December 2025.')
    clause = appointment_clause(text, 'Chief Executive Officer')
    assert clause and 'December 2025' in clause and 'October' not in clause
    assert appointment_clause(text, 'Chief Financial Officer') is None


def test_supported_undated_internal_role_is_retained():
    payload, sources = synthetic()
    role = payload['executives'][0]['prior_internal_roles'][0]
    role['start_date'] = role['end_date'] = ''
    result = assess_claims(payload, sources, reviewer=FixtureReviewer())
    validate_management(result)
    claim = next(c for c in result['validation']['claim_results'] if c['claim_id']=='executive:1:role:1')
    assert claim['outcome']!='unsupported'
    retained = result['profiles'][0]['prior_internal_roles'][0]
    assert retained['position']==role['position'] and retained['start_date']==retained['end_date']==''


def test_wrong_date_is_withheld_while_supported_role_survives():
    payload, sources = synthetic()
    payload['executives'][0]['prior_internal_roles'][0]['end_date']='2099'
    result=assess_claims(payload,sources,reviewer=FixtureReviewer())
    claim=next(c for c in result['validation']['claim_results'] if c['claim_id']=='executive:1:role:1')
    assert claim['outcome']=='qualified' and 'end_date' in claim['withheld_assertions']
    assert '2099' not in claim['statement'] and '2099' in claim['original_statement']
    assert result['profiles'][0]['prior_internal_roles'][0]['end_date']==''


class EntailmentReviewer(FixtureReviewer):
    def __init__(self, mutate=None): self.mutate=mutate; self.calls=0
    def review_claims(self,candidates,sources):
        self.calls+=1
        answers=[]
        for candidate in candidates:
            answer={'claim_id':candidate['claim_id'],'outcome':'supported',
                    'retained_statement':candidate['statement'],'reason':'A faithful paraphrase of the cited appointment.',
                    'supporting_citations':candidate['quotations']}
            if self.mutate:self.mutate(answer)
            answers.append(answer)
        return answers


def paraphrase_case():
    payload,sources=synthetic()
    payload['facts'][0]['statement']='Alex Sample became Chief Executive Officer effective May 1, 2024.'
    return payload,sources


def test_faithful_fact_paraphrase_is_audited_and_retained():
    payload,sources=paraphrase_case();reviewer=EntailmentReviewer()
    original=deepcopy(payload)
    result=assess_claims(payload,sources,reviewer=reviewer);validate_management(result)
    fact=next(c for c in result['validation']['claim_results'] if c['claim_id']=='fact:1')
    assert reviewer.calls==1 and fact['outcome']=='qualified'
    assert fact['entailment_review']['outcome']=='supported' and fact['original_outcome']=='unsupported'
    assert result['facts'][0]['statement']==payload['facts'][0]['statement']
    assert payload==original


def test_entailment_recovery_cannot_invent_a_number_or_quote():
    for mutate in [lambda a:a.update(retained_statement='Alex Sample became CEO in 2099.'),
                   lambda a:a['supporting_citations'][0].update(quote='Fabricated appointment in 2024.')]:
        payload,sources=paraphrase_case();reviewer=EntailmentReviewer(mutate)
        result=assess_claims(payload,sources,reviewer=reviewer)
        assert next(c for c in result['validation']['claim_results'] if c['claim_id']=='fact:1')['outcome']=='unsupported'


def test_joint_scope_requires_explicit_people_not_merely_foreign_citations():
    judgment={'executive':'Alex Sample','explanation':'Alex Sample and Riley Test provide executive coverage.'}
    assert judgment_scope(judgment,['Alex Sample','Riley Test'])==('team',True)
    judgment['explanation']='Alex Sample has long experience.'
    assert judgment_scope(judgment,['Alex Sample','Riley Test'])==('individual',False)


def test_summary_drops_invalid_references_without_losing_surviving_findings():
    payload,sources=synthetic()
    payload['overall_assessment']['supporting_judgment_ids'].append('rejected-judgment')
    result=assess_claims(payload,sources,reviewer=FixtureReviewer());validate_management(result)
    assert result['observations'] and result['validation']['overall_references_valid']
    recovery=result['validation']['overall_recovery']
    assert recovery['method']=='surviving_reviewed_text_only'
    assert 'rejected-judgment' not in recovery['corrected_overall']['judgment_ids']
    assert recovery['corrected_overall']['text']==' '.join(o['text'] for o in result['observations'])


def test_entailment_and_surviving_summary_use_normal_audited_runtime(db_session, tmp_path):
    import json
    from sqlalchemy import select
    from app.models.orm import ModelRun
    from app.services.llm.client import LLMBackend, LLMRawResult
    from .test_validator7_claims import ResponseBackend, run
    from .review_fixtures import response

    class Reviewer(LLMBackend):
        def generate(self, request):
            if request.prompt.name=='m3_fact_entailment':
                value={'claims':[{'claim_id':c['claim_id'],'outcome':'supported',
                                  'retained_statement':c['statement'],'reason':'Supported appointment paraphrase.',
                                  'supporting_citations':c['quotations']} for c in request.inputs['claims']]}
            elif request.prompt.name=='m3_surviving_summary':
                observations=request.inputs['surviving_judgments']
                value={'signal':'neutral','text':observations[0]['text'],
                       'judgment_ids':[observations[0]['observation_id']],'limitations':[]}
            else:
                assert request.prompt.name=='m3_validator_7'
                inputs=request.inputs
                value=response({'judgments':inputs['original_judgments'],
                                'overall_assessment':inputs['original_overall_assessment']},inputs['claim_validation'])
                value['overall']['judgment_ids']=['not-surviving']
            return LLMRawResult(json.dumps(value),'offline-bounded-review',{'backend':'fake'})

    def mutate(payload, packet):
        payload['facts'][0]['statement']='Alex Sample became Chief Executive Officer effective May 1, 2024.'
    _,block,artifact=run(db_session,tmp_path,ResponseBackend(mutate),Reviewer())
    validate_management(artifact)
    claims={c['claim_id']:c for c in artifact['validation']['claim_results']}
    assert claims['fact:1']['outcome']=='qualified'
    assert artifact['validation']['overall_recovery']['method']=='bounded_surviving_judgments'
    prompts=set(db_session.scalars(select(ModelRun.prompt_name)))
    assert {'m3_fact_entailment','m3_surviving_summary','m3_validator_7'} <= prompts
    from pathlib import Path
    folder=Path(block['source_manifest']).parent
    assert (folder/'m3_fact_entailment_request.json').is_file()
    assert (folder/'m3_surviving_summary_response.txt').is_file()


def test_director_boundary_includes_credentials_and_committee_lines():
    from app.services.bo.m3_rebuild.sources import proxy_boundaries
    text=('Alex Sample\nDirector since 2025\nMr. Sample serves as CEO.\n'
          'Jordan Board, D.M.D.\nDirector since 2021\nCompensation Committee Member\nDr. Board worked at OtherCo.')
    assert text.index('Jordan Board') in proxy_boundaries(text)


def test_partial_appointment_does_not_assign_one_office_date_to_other_titles():
    from app.services.bo.m3_rebuild.claim_support import scoped_appointment
    quote='Mr. Sample was named Chief Accounting Officer in January 2026.'
    assert scoped_appointment(quote,'Senior Vice President and Chief Accounting Officer','2026-01')=='Chief Accounting Officer'
    assert scoped_appointment(quote,'Chief Executive Officer','2026-01') is None
    assert scoped_appointment(quote,'Chief Accounting Officer','2025-01') is None
    assert scoped_appointment(quote,'Chief Accounting Officer','2026') is None


def test_geographic_scope_and_previous_private_practice_are_not_role_employers():
    from app.services.bo.m3_rebuild.employers import internal_employer
    bio=('Alex Sample serves as our Chief Executive Officer. Mr. Sample joined us in 2009 as Litigation Counsel '
         'after several years of private practice as a litigator. In 2015, he was promoted to market chief executive for Arizona. '
         'Prior to joining us, he served OtherCo as counsel.')
    for role in [dict(position='Litigation Counsel',start_date='2009',end_date='',quote=bio.split(' In 2015')[0]),
                 dict(position='market chief executive for Arizona',start_date='2015',end_date='',quote='In 2015, he was promoted to market chief executive for Arizona.')]:
        assert internal_employer(role,{'quote':bio,'prior_internal_roles':[]},'Example Corp')
    import pytest
    with pytest.raises(ValueError):
        internal_employer(dict(position='CFO of OtherCo',start_date='2015',end_date='',
            quote='He served as CFO of OtherCo from 2015 through 2020.'),{'quote':bio,'prior_internal_roles':[]},'Example Corp')


def test_boundary_recovery_preserves_real_fragment_ids_and_offsets():
    from app.services.bo.m3_rebuild.claims import ClaimValidator
    from app.services.bo.m3_rebuild.sources import FilingSources
    text='Alex Sample serves as our Chief Executive Officer since May 2024.'
    split=text.index('Officer')+1
    sources=FilingSources(company='Example Corp',filing_period='2024-12-31',source_path='fixture',sha256='fixture',
        pages={'a':text[:split],'b':text[split:]},section_ids=['a','b'],
        expected_roster=[{'name':'Alex Sample','position':'Chief Executive Officer','source_id':'a'}],
        coverage_verifiable=True,limitations=[],physical_pages={'a':1,'b':1},
        passage_offsets={'a':0,'b':split},document_kind='DEF 14A')
    validator=ClaimValidator(sources)
    quotes=validator.citations([{'source_id':'b','quote':'Chief Executive Officer since May 2024.'}],'Alex Sample')
    retained=[q for q in quotes if q['outcome']=='accepted']
    assert {q['source_id'] for q in retained}=={'a','b'}
    assert all(sources.pages[q['source_id']][q['span_start']:q['span_end']]==q['original_source_text'] for q in retained)
    assert all(q['page_char_start']==sources.passage_offsets[q['source_id']]+q['span_start'] for q in retained)
    assert not validator.boundary_citations('b','Chief Executive Officer since May 2099.','Alex Sample')
    # Regression: fragment recovery used to pass admission but fail final artifact
    # serialization, discarding the whole management section on both attempts.
    from .responses import with_credit_response
    payload = with_credit_response({
        'roster_date': '', 'roster_source_id': '', 'roster_quote': '',
        'executives': [{'name': 'Alex Sample', 'position': 'Chief Executive Officer',
            'appointment_date': '2024-05', 'source_id': 'b',
            'quote': 'Chief Executive Officer since May 2024.', 'prior_internal_roles': [],
            'external_recruitment_quote': '', 'external_source_id': ''}],
    })
    artifact = assess_claims(payload, sources, reviewer=FixtureReviewer())
    assert any(c['matching_method'] == 'canonical_boundary_fragments' for c in artifact['citations'])
    assert validate_management(artifact) == artifact


def test_management_matching_method_contract_is_closed_and_shared():
    import pytest
    import jsonschema
    from app.services.bo.m3_rebuild.matching import MATCHING_METHODS
    payload, sources = synthetic()
    artifact = assess_claims(payload, sources, reviewer=FixtureReviewer())
    assert artifact['citations']
    for method in MATCHING_METHODS:
        candidate = deepcopy(artifact)
        candidate['citations'][0]['matching_method'] = method
        validate_management(candidate)
    candidate = deepcopy(artifact)
    candidate['citations'][0]['matching_method'] = 'unknown_matching_method'
    with pytest.raises(jsonschema.ValidationError):
        validate_management(candidate)
