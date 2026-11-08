"""Deterministic headings and exact copies of governed specialist explanations."""
from copy import deepcopy
import pytest

from app.prompts import source_selection as contract
from app.services.bo.source_selection import project
from app.services.bo.competitive_presentation import grouped_findings, REVENUE, COST, INTERACTIONS
from app.services.bo.synthesis import iter_claims
from app.services.pipeline.artifacts import ArtifactIntegrityError
from tests.unit.test_bo_competitive_positioning import editorial, packet


def data(records):
    source=packet(records)
    selected=['M1S1-H001','M1S4-H001','M1A6-H001']
    plan=dict(schema_version=contract.OUTPUT_VERSION,policy_version=contract.POLICY_VERSION,
              selections=[dict(hypothesis_id=hid,placement='lead' if i==0 else 'risk',reason='Relevant source finding.') for i,hid in enumerate(selected)],
              omissions=[dict(hypothesis_id=h['hypothesis_id'],reason='Not selected.') for h in source['hypotheses'] if h['hypothesis_id'] not in selected])
    output=project(plan,source)
    entries=[dict(claim=c,evidence={'id':c['claim_id'],'title':'Generic'}) for _,c in iter_claims(output)]
    audit=dict(run={'analysis_run_id':'run'},hypotheses={'records':source['hypotheses']})
    provenance=dict(producer_records=[dict(agent_id=h.agent_id,agent_run_id=h.agent_run_id,validation_status='valid') for h in records])
    return entries,audit,provenance


def test_exact_explanation_copy_grouping_no_duplication_and_no_mutation(editorial):
    records,_=editorial
    cost=next(h for h in records if h.hypothesis_id=='M1S4-H001')
    cost.credit_mechanism='The source credit mechanism.'
    cost.interpretation={'implication':'The source implication.','trend':'Improving.','watch_trigger':'The source trigger.'}
    cost.transmission_mechanism='The source transmission mechanism.'
    entries,audit,provenance=data(records);before=deepcopy((entries,audit,provenance))
    groups=grouped_findings(entries,audit,provenance)
    assert [g['title'] for g in groups]==[REVENUE,COST,INTERACTIONS]
    by_id={e['source_hypothesis_id']:e for g in groups for e in g['entries']}
    assert len(by_id)==3
    assert groups[0]['entries'][0]['source_hypothesis_id']=='M1S1-H001'
    entry=groups[1]['entries'][0]
    assert entry['source_hypothesis_id']==cost.hypothesis_id
    assert [d['text'] for d in entry['details']]==[cost.credit_mechanism,cost.interpretation['implication'],
        cost.interpretation['trend'],cost.interpretation['watch_trigger'],cost.transmission_mechanism]
    assert all(d['source_path'].startswith('/hypotheses/records/') for d in entry['details'])
    assert entry['evidence']['title']=='Operating costs'
    assert [p['label'] for p in entry['pointers']]==['Finding','Credit Implication','Watch Triggers']
    finding,implication,watch=entry['pointers']
    assert [p['text'] for p in finding['parts']]==[cost.claim]
    assert any(d['text'] == cost.interpretation['trend'] for d in entry['details'])
    assert [p['text'] for p in implication['parts']]==[cost.credit_mechanism,cost.interpretation['implication'],cost.transmission_mechanism]
    assert [p['text'] for p in watch['parts']]==[cost.interpretation['watch_trigger']]
    assert grouped_findings(list(reversed(entries)),audit,provenance)==groups
    assert (entries,audit,provenance)==before


@pytest.mark.parametrize('claim_type,label',[('fact','Fact'),('inference','Inference'),('assumption','Assumption'),
                                            ('management_claim','Management statement'),('calculated_fact','Calculated fact')])
def test_governed_claim_type_preserved(editorial,claim_type,label):
    records,_=editorial
    records[0].claim_type=type(records[0].claim_type)(claim_type)
    entries,audit,provenance=data(records)
    groups=grouped_findings(entries,audit,provenance)
    entry=next(e for g in groups for e in g['entries'] if e['source_hypothesis_id']==records[0].hypothesis_id)
    assert entry['claim_type_label']==label


@pytest.mark.parametrize('defect',['text','type','producer','foreign_run','superseded','duplicate'])
def test_invalid_source_not_used_for_enrichment(editorial,defect):
    records,_=editorial;entries,audit,provenance=data(records)
    source=audit['hypotheses']['records'][0]
    if defect=='text':source['claim']='Different source text'
    elif defect=='type':source['claim_type']='assumption'
    elif defect=='producer':source['agent_run_id']='foreign-producer'
    elif defect=='foreign_run':source['analysis_run_id']='another-run'
    elif defect=='superseded':source['acceptance_state']='superseded'
    else:audit['hypotheses']['records'].append(deepcopy(source))
    with pytest.raises(ArtifactIntegrityError):grouped_findings(entries,audit,provenance)


def test_watch_trigger_preserves_source_metrics_without_inventing_thresholds(editorial):
    records,_=editorial
    cost=next(h for h in records if h.hypothesis_id=='M1S4-H001')
    trigger='Wage growth above revenue growth per admission; monitor contract labour hours.'
    cost.interpretation={'watch_trigger':trigger}
    # An identical explanation must not suppress the actual watch-trigger field.
    cost.credit_mechanism=trigger
    groups=grouped_findings(*data(records))
    entry=next(e for g in groups for e in g['entries'] if e['source_hypothesis_id']==cost.hypothesis_id)
    watch=entry['pointers'][2]
    assert len(watch['parts'])==1 and watch['parts'][0]['text']==trigger
    assert watch['parts'][0]['source_path'].endswith('/interpretation/watch_trigger')
    cost.interpretation={}
    groups=grouped_findings(*data(records))
    entry=next(e for g in groups for e in g['entries'] if e['source_hypothesis_id']==cost.hypothesis_id)
    assert entry['pointers'][2]['parts']==[]


@pytest.mark.parametrize('components', [
    ['M1S1-H001', 'M1S3-H001'],  # revenue-only interactions still follow costs
    ['M1S4-H001'],
    ['M1S1-H001', 'M1S4-H001'],
])
def test_all_agent6_insights_follow_both_primary_groups(editorial, components):
    records, _ = editorial
    interaction = next(h for h in records if h.agent_id == 'm1_resilience_integration')
    interaction.component_hypothesis_ids = components
    groups = grouped_findings(*data(records))
    assert [g['title'] for g in groups] == [REVENUE, COST, INTERACTIONS]
    assert [e['source_hypothesis_id'] for e in groups[-1]['entries']] == [interaction.hypothesis_id]
    assert all(e['source_agent_id'] != interaction.agent_id for g in groups[:-1] for e in g['entries'])


def test_agent6_lineage_uses_only_explicit_current_specialist_references(editorial):
    from app.services.bo.competitive_presentation import insight_formation
    entries, audit, provenance = data(editorial[0])
    source = next(h for h in audit['hypotheses']['records'] if h['hypothesis_id'] == 'M1A6-H001')
    source['component_hypothesis_ids'] = ['M1S1-H001', 'M1S4-H001', 'M1S1-H001']
    before = deepcopy((audit, provenance))
    lineage = insight_formation(source, audit, provenance)
    assert [(c['agent_number'], c['agent_name']) for c in lineage['contributors']] == [('1', 'Pricing Power'), ('4', 'Cost Resilience')]
    assert lineage['unavailable_count'] == 0
    assert lineage['contributors'][0]['findings'][0]['text'] == audit['hypotheses']['records'][0]['claim']
    assert lineage['text'] == source['claim']
    assert (audit, provenance) == before


@pytest.mark.parametrize('defect', ['missing', 'foreign_run', 'producer', 'duplicate', 'withheld'])
def test_agent6_lineage_does_not_substitute_unusable_components(editorial, defect):
    from app.services.bo.competitive_presentation import insight_formation
    _, audit, provenance = data(editorial[0])
    source = next(h for h in audit['hypotheses']['records'] if h['hypothesis_id'] == 'M1A6-H001')
    source['component_hypothesis_ids'] = ['M1S1-H001']
    component = next(h for h in audit['hypotheses']['records'] if h['hypothesis_id'] == 'M1S1-H001')
    if defect == 'missing': audit['hypotheses']['records'].remove(component)
    if defect == 'foreign_run': component['analysis_run_id'] = 'other-run'
    if defect == 'producer': component['agent_run_id'] = 'superseded-producer'
    if defect == 'duplicate': audit['hypotheses']['records'].append(deepcopy(component))
    if defect == 'withheld': component['acceptance_state'] = 'rejected'
    lineage = insight_formation(source, audit, provenance)
    assert lineage['contributors'] == []
    assert lineage['unavailable_count'] == 1


def test_lineage_and_filing_quotes_are_inside_one_evidence_disclosure():
    from app.services.bo.four_section_view import _env
    from lxml import html
    item = {'title': 'Cross-dimensional insight', 'id': 'test-insight',
        'insight_formation': {'contributors': [{'agent_number': '2', 'agent_name': 'Demand Defensiveness',
            'findings': [{'text': 'Capacity is constrained by staffing.'}]}], 'unavailable_count': 0,
            'text': 'A combined inference.', 'credit_implication': 'Admission growth can be restricted.', 'direction_label': 'Negative'},
        'quotations': [{'quote': 'An exact filing quotation.', 'filename': 'hca-20251231.htm', 'section': '10-K'}]}
    t = _env.from_string("{% from 'bo_evidence.html.j2' import evidence with context %}{{ evidence(item) }}")
    p = html.fromstring(t.render(item=item, pdf=False, bo4={'memo': {'identity': {'analysis_run_id': 'saved', 'evidence_snapshot_version': 1}}}))
    panel = p.xpath('//details[@class="bo-evidence"]')[0]
    assert panel.get('open') is None
    assert panel.xpath('./div/section[@class="bo-insight-formation"]')
    assert panel.xpath('./div/article/blockquote[text()="An exact filing quotation."]')
    assert not panel.xpath('.//section[@class="bo-insight-formation"]//details')
    assert not panel.xpath('.//details[summary[text()="Supporting 10-K evidence"]]')
    assert 'Agent 2' in panel.text_content() and 'How this insight was formed' in panel.text_content()
