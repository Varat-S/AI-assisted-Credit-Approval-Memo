"""Four-section BO artifact schema. Source objects are opaque, lossless JSON."""
from copy import deepcopy

DOCUMENT = 'business_overview_four_section_memo'
SCHEMA_VERSION = 'bo-four-section-memo-1.0.0'
ASSEMBLER_VERSION = 'bo-four-section-assembler-1.0.0'
FILENAME = 'business_overview_four_section.v1.json'
PROVENANCE_VERSION = 'bo-four-section-provenance-1.0.0'
SECTION_TITLES = [
    ('corporate_structure_debt_obligations', 'Corporate Structure & Debt Obligations'),
    ('management', 'Management'), ('competitive_positioning', 'Competitive Positioning'),
    ('industry', 'Industry'),
]


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required,
            'additionalProperties': False}


STATUS = {'enum': ['complete', 'partial', 'unavailable']}
STRINGS = {'type': 'array', 'items': {'type': 'string'}}
REF = {'type': ['string', 'null']}
CONTENT = {'type': ['object', 'null']}
BLOCK = obj({'status': STATUS, 'recorded_status': REF, 'validation_status': REF,
             'source_ref': REF, 'content': CONTENT, 'visible_warnings': STRINGS})
sections = []
for index, (sid, title) in enumerate(SECTION_TITLES):
    props = {'id': {'const': sid}, 'title': {'const': title}, 'status': STATUS,
             'visible_warnings': STRINGS}
    if index == 0:
        props.update(layout={'const': 'structure_left_debt_right'},
                     structure=deepcopy(BLOCK), debt_obligations=deepcopy(BLOCK))
    else:
        props.update(recorded_status=REF, validation_status=REF, source_ref=REF, content=CONTENT)
        if index == 2:
            props.update(editorial_selection=CONTENT, selection_source_ref=REF, challenge_source_ref=REF)
    sections.append(obj(props))

FOUR_SECTION_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    **obj({
        'document': {'const': DOCUMENT}, 'schema_version': {'const': SCHEMA_VERSION},
        'design_basis': obj({'assembler_version': {'const': ASSEMBLER_VERSION},
                             'selection_policy_version': {'type': 'string'}}),
        'example_only': {'type': 'boolean'},
        'identity': obj({'case_id': {'type': 'string', 'minLength': 1},
                         'analysis_run_id': {'type': 'string', 'minLength': 1},
                         'evidence_snapshot_version': {'type': 'integer', 'minimum': 1},
                         'evidence_snapshot_hash': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
                         'reporting_company': REF, 'as_of_date': REF, 'evidence_cutoff_timestamp': REF,
                         'conclusion_id': REF, 'orchestrator_run_id': REF}),
        'governance': obj({'memo_completeness': {'enum': ['complete', 'incomplete']},
                           'conclusion_status': {'type': 'string'}, 'validators_enforced': {'type': 'boolean'},
                           'independent_challenge_status': {'type': 'string'},
                           'human_review_status': {'const': 'pending'},
                           'execution_mode': {'type': 'string'}, 'visible_warnings': STRINGS}),
        'sources': {'type': 'array', 'items': obj({
            'artifact_id': {'type': 'string'}, 'stage_name': {'type': 'string'},
            'source_path': {'type': 'string'}, 'sha256': {'type': 'string'},
            'content_hash': {'type': 'string'}, 'hash_kind': {'const': 'canonical_stage'},
            'binding': {'const': 'same_run_verified'},
        })},
        'sections': {'type': 'array', 'prefixItems': sections, 'items': False, 'minItems': 4, 'maxItems': 4},
        'evidence_ui': obj({'pattern': {'const': 'native_details'}, 'initially_expanded': {'const': False},
                            'hide_inline_source_citations': {'const': True}, 'detail_fields': STRINGS,
                            'always_visible': STRINGS, 'static_pdf_evidence': {'const': 'appendix'}}),
        'content_hash': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
    }),
}
