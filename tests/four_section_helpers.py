"""All-four populated, fictional exact-run fixtures. Never used by production."""
import json
from hashlib import sha256

from app.services.bo.runner import BusinessOverviewRunner
from app.services.bo.offline import ScriptedBoBackend
from app.prompts.competitive_positioning import OUTPUT_VERSION
from app.schemas.snapshots import StructuredEvidenceRecord
from tests import competitive_positioning_helpers as cp, bo_helpers as h
from tests.integration.test_bo_m4_dual_specialist import _debt_evidence
from tests.fixtures.hca_module4 import hca_module4_output
from tests.m3_rebuild.responses import with_credit_response
from tests.m3_rebuild.review_fixtures import FixtureReviewerBackend

COMPANY = 'Northfield Health Systems'
APPOINTMENT = 'Alex Sample was appointed Chief Executive Officer effective May 1, 2025.'
PRIOR = 'Alex Sample previously served as President of the Company from January 2020 through April 2025.'
ROSTER = 'As of January 10, 2026, our executive officers were as follows:'


class ManagementExtractor:
    extraction_mode = 'offline_fixture'

    def extract(self, sources, diagnostics):
        sid = sources.section_ids[0]
        return json.dumps(with_credit_response({
            'roster_date': '2026-01-10', 'roster_source_id': sid, 'roster_quote': ROSTER,
            'executives': [{'name': 'Alex Sample', 'position': 'Chief Executive Officer',
                            'appointment_date': '2025-05-01', 'source_id': sid, 'quote': APPOINTMENT,
                            'prior_internal_roles': [{'position': 'President of the Company', 'start_date': '2020-01',
                                                      'end_date': '2025-04', 'source_id': sid, 'quote': PRIOR}],
                            'external_recruitment_quote': '', 'external_source_id': ''}],
        }, recent_names=['Alex Sample']))


def evidence():
    base = _debt_evidence()
    corporate = {'schema_version': '1.0', 'document_type': 'corporate_structure_onboarding',
                 'company_name': COMPANY, 'data_status': 'simulated_educational_example',
                 'corporate_tree': {'id': 'NFH', 'name': COMPANY, 'role': 'Borrower', 'is_guarantor': False,
                                    'children': [{'id': 'OPCO', 'name': 'Northfield Operating Company',
                                                  'role': 'OpCo', 'is_guarantor': True,
                                                  'ownership_percent_from_parent': 100.0, 'children': []}]}}
    corporate_hash = sha256(json.dumps(corporate).encode()).hexdigest()
    pages = [f'Form 10-K\n{COMPANY}\nFor the fiscal year ended December 31, 2025',
             f'Executive Officers\n{ROSTER}\nAlex Sample........ 50 Chief Executive Officer\n{APPOINTMENT}\n{PRIOR}\nItem 2.']
    management_hash = sha256('\n'.join(pages).encode()).hexdigest()
    docs = [*base.documents,
            {'document_id': 'corp-doc', 'filename': 'corporate.json', 'sha256': corporate_hash, 'parser': 'structured_json'},
            {'document_id': 'mgmt-doc', 'filename': 'management.pdf', 'sha256': management_hash, 'parser': 'pdf_text'}]
    structured = [StructuredEvidenceRecord.model_validate({'evidence_id': 'corp-evidence', 'evidence_type': 'corporate_structure_onboarding',
                   'document_id': 'corp-doc', 'document_sha256': corporate_hash, 'payload': corporate,
                   'filename': 'corporate.json', 'entity_id': 'NFH', 'available_at': '2026-01-10T00:00:00Z', 'schema_version': '1.0',
                   'reporting_company': COMPANY, 'declared_status': 'simulated_educational_example',
                   'assumption_status': 'simulated', 'validation_status': 'contract_validated'})]
    passages = [*base.narrative_evidence,
                {'evidence_id': 'ev_debt_adjustment', 'document_id': 'doc_10k', 'section': 'Item 8',
                 'location': 80000, 'text': 'Debt issuance costs and discounts (436). The additional receivables credit facility is undrawn. '
                 # Fictional source schedule for the existing amount-verification check.
                 'Amounts in millions: 5.000% notes $700 million; 5.250% notes $750 million; '
                 '5.750% notes $1,500 million; 6.200% notes $1,250 million; other senior notes $39,050 million; '
                 'debentures $450 million; commercial paper drawn $2,207 million; other secured debt $1,021 million. '
                 'Undrawn availability: commercial paper $4,000 million; revolving facility $8,000 million; '
                 'receivables facility $1,000 million.'}, *[
        {'evidence_id': f'mgmt-page-{i}', 'document_id': 'mgmt-doc', 'page': i,
         'location': (i - 1) * 1000, 'text': text, 'section': 'Item 10', 'heading': 'Executive Officers'}
        for i, text in enumerate(pages, 1)]]
    return base.model_copy(update={'documents': docs, 'structured_evidence': structured, 'narrative_evidence': passages})


def debt_output():
    # Reuse the exact established debt-contract fixture shapes, explicitly
    # authoring fictional company labels for this isolated scripted record.
    # Production code NEVER loads or substitutes this fixture.
    def convert(value):
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, str):
            return value.replace('HCA Healthcare, Inc.', COMPANY).replace('HCA Healthcare', COMPANY).replace('HCA Inc.', 'Northfield Operating Company')
        return value
    output = convert(hca_module4_output())
    d1 = output['deliverable_1']
    d1['non_note_obligations_schedule'][-1] = {
        'obligation_facility': 'Additional receivables credit facility', 'legal_borrower': 'Northfield Operating Company',
        'principal_drawn_m': 0.0, 'available_facility_limit_m': 1000.0, 'interest_rate_terms': 'SOFR + 1.25%',
        'maturity': '2030', 'collateral_security_status': 'unsecured', 'guarantors_credit_support': COMPANY + ' guarantee',
        'priority_ranking_tier': 'tier_2_senior_unsecured_guaranteed',
    }
    d1['reconciling_items'] = [{'kind': 'debt_issuance_costs_and_discounts', 'label': 'Debt issuance costs and discounts',
                              'amount_m': -436.0, 'quote': 'Debt issuance costs and discounts (436)',
                              'evidence_id': 'ev_debt_adjustment'}]
    return output


def run(session, path, *, populated=True, answers=None):
    script = answers or cp.script()
    if populated:
        script['m4_debt'] = debt_output()
    backend = ScriptedBoBackend(script)
    runner = BusinessOverviewRunner(
        session, backend=backend, bo_roster='v3', sector=None, business_orchestrator_contract=OUTPUT_VERSION,
        data_root=path / 'data', output_root=path / 'out', enable_m4_debt_specialist=populated,
        m3_extractor=ManagementExtractor() if populated else None,
        m3_reviewer_backend=FixtureReviewerBackend() if populated else None)
    if populated:
        runner.m3_config = {'corporate_source': 'corporate.json', 'management_source': 'management.pdf',
                            'company': COMPANY, 'filing_period': h.PERIOD, 'extraction': None}
    result = runner.run_prepared(h.CASE, evidence() if populated else h.evidence_snapshot(), h.metrics(), write_outputs=True)
    return result, backend
