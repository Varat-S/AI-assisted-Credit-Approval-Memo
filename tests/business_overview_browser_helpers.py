"""Fictional local Inline-XBRL source + scripted models; actual browser worker."""
from collections import defaultdict
from datetime import date
import json
from pathlib import Path

from app.services.acquisition.sec_edgar import write_bundle
from app.services.extraction.sec.bundle import SecFilingBundle
from app.services.bo.offline import ScriptedBoBackend
from app.services.llm.client import LLMBackend, LLMRawResult
from tests import bo_helpers as h, four_section_helpers as f, competitive_positioning_helpers as cp
from tests.sec_helpers import inline_document, filing_file
from tests.m3_rebuild.responses import with_credit_response
from tests.m3_rebuild.review_fixtures import FixtureReviewerBackend

FOLDER = 'NFH 10-K FY2025'


def source_folder(root):
    folder = Path(root) / FOLDER
    sections = defaultdict(list)
    for section, text in h.PASSAGES.values():
        sections[section].append(text)
    sections['Item 8'].extend([
        'Our long-term debt consists of senior unsecured notes with principal of $43,700 million issued by the operating company and guaranteed by the parent. Total indebtedness was $46,492 million at year end.',
        'The senior notes have staggered maturities; the revolving credit facility is undrawn. Refinancing of maturing tranches occurred during the year.',
        'Debt issuance costs and discounts (436). The additional receivables credit facility is undrawn.'])
    sections['Item 10'] = [f.ROSTER, 'Alex Sample........ 50 Chief Executive Officer', f.APPOINTMENT, f.PRIOR]
    extra = '<h1>Northfield Health Systems</h1><p>Form 10-K for the fiscal year ended December 31, 2025</p>'
    for section in ['Item 1','Item 1A','Item 7','Item 8','Item 10']:
        heading = section + ('. Executive Officers' if section == 'Item 10' else '. Business' if section == 'Item 1' else '. Risk Factors' if section == 'Item 1A' else '. Financial Statements')
        extra += '<h2>' + heading + '</h2>' + ('<h3>Executive Officers</h3>' if section == 'Item 10' else '') + ''.join('<p>' + text + '</p>' for text in sections[section])
    content = inline_document(extra=extra).replace(b'2024', b'2025')
    primary = filing_file(filename='nfh-20251231.htm', content=content, filing_date=date(2026,2,20),
                          accession='0000000001-26-000001').model_copy(update={'report_date':date(2025,12,31)})
    schema = filing_file(filename='nfh-20251231.xsd', role='schema', content=b'<schema/>',
                         filing_date=date(2026,2,20), accession=primary.accession).model_copy(update={'report_date':date(2025,12,31)})
    bundle = SecFilingBundle(cik='1', ticker='NFH', accession=primary.accession, form='10-K',
                            report_date=date(2025,12,31), filing_date=primary.filing_date,
                            primary_document=primary.filename, files=[primary,schema])
    write_bundle(bundle, folder)
    manifest = json.loads((folder/'bundle.json').read_text())
    for entry in manifest['files']:
        (folder/entry['path']).rename(folder/entry['filename'])
        entry['path'] = entry['filename']
    (folder/'bundle.json').write_text(json.dumps(manifest))
    (folder/'company.json').write_text(json.dumps({'cik':1,'ticker':'NFH','name':f.COMPANY}))
    corporate = f.evidence().model_dump(mode='json')['structured_evidence'][0]['payload']
    (folder/'m3_corporate_structure.json').write_text(json.dumps(corporate))
    return folder


def business_backend(*, industry=False):
    answers = cp.script()
    from app.prompts.source_selection import OUTPUT_VERSION, POLICY_VERSION
    answers['orchestrate'] = dict(schema_version=OUTPUT_VERSION, policy_version=POLICY_VERSION,
        selections=[dict(hypothesis_id='M1S1-H001', placement='lead', reason='Negotiated terms anchor the discussion.'),
                    dict(hypothesis_id='M1S1-H002', placement='driver', reason='Multi-year duration is relevant.'),
                    dict(hypothesis_id='M1A6-H001', placement='risk', reason='Supported workforce interaction.')],
        omissions=[dict(hypothesis_id=hid, reason='Component lineage or lower relevance than selected findings.')
                   for hid in ['M1S2-H001','M1S3-H001','M1S4-H001','M1S5-H001']])
    review = answers['challenge']['editorial_review']
    review.update(policy_version=POLICY_VERSION,
                  reviewed_hypothesis_ids=[d['hypothesis_id'] for d in answers['orchestrate']['selections'] + answers['orchestrate']['omissions']],
                  reviewed_omitted_hypothesis_ids=[d['hypothesis_id'] for d in answers['orchestrate']['omissions']],
                  reviewed_interaction_claim_ids=['selected:M1A6-H001'])
    answers.pop('challenge')  # A new browser run must work without any challenger response.
    answers['m4_debt'] = f.debt_output()
    answers['m4_debt']['deliverable_1']['reconciling_items'][0]['evidence_id'] = {'$evidence':'Debt issuance costs and discounts (436)'}
    if not industry:
        answers['m2_industry'] = {'parameters':[], 'hypotheses':[], 'missing_information':['Industry is intentionally unavailable in this offline acceptance run.']}
    return ScriptedBoBackend(answers)


class ManagementBackend(LLMBackend):
    """Script extraction and independent review through the real shared runtime."""
    def __init__(self):
        self.calls = []
        self.reviewer = FixtureReviewerBackend()

    def generate(self, request):
        self.calls.append(request.prompt.name)
        if request.prompt.name == 'm3_validator_7':
            return self.reviewer.generate(request)
        assert request.prompt.name == 'm3_management_assessment'
        passages = request.inputs['narrative_evidence']
        def citation(text):
            return next(p['evidence_id'] for p in passages if text in p['text'])
        payload = with_credit_response({'roster_date':'2026-01-10','roster_source_id':citation(f.ROSTER),
            'roster_quote':f.ROSTER, 'executives':[{'name':'Alex Sample','position':'Chief Executive Officer',
                'appointment_date':'2025-05-01','source_id':citation(f.APPOINTMENT),'quote':f.APPOINTMENT,
                'prior_internal_roles':[{'position':'President of the Company','start_date':'2020-01','end_date':'2025-04',
                                         'source_id':citation(f.PRIOR),'quote':f.PRIOR}],
                'external_recruitment_quote':'','external_source_id':''}]}, recent_names=['Alex Sample'])
        return LLMRawResult(json.dumps(payload),'offline-browser-management-fixture',{'backend':'fake'})
