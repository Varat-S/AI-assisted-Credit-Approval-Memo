"""Conservative display labels from frozen classifications and review flags.

This is a versioned presentation policy, not a new specialist or validation
result. Canonical types, findings, validation decisions and governance stay intact.
"""
from copy import deepcopy

POLICY = 'bo-finding-display-1.0.0'


def assessment(source, pointers, uncertainty=None):
    kind = source['claim_type']
    flags = {f.get('rule_id') for f in source.get('review_flags', [])}
    attribution = kind == 'management_claim' or source.get('admissibility') == 'attributed'
    uncovered = 'quote_does_not_cover_claim' in flags
    hypothetical = 'generic_risk_disclosure_only' in flags
    if uncovered:
        label = 'Assumption'
        why = ('The quotation is verified, but the saved validator assessment says it does not establish '
               'the claim. The finding is shown as an Assumption rather than a verified Fact. '
               'This conservative display label does not change the saved validation record.')
    elif hypothetical:
        label = 'Assumption'
        why = ('The saved review identifies hypothetical risk-factor language, not evidence that the '
               'event occurred. The scenario is therefore shown as an Assumption.')
    elif attribution:
        label = 'Assumption'
        why = ('The finding is management-attributed. The underlying outcome is not independently '
               'established by that attribution, so it is shown as an Assumption.')
    elif kind == 'assumption':
        label = 'Assumption'
        why = 'The specialist recorded this finding as an Assumption, rather than an established disclosure or derived conclusion.'
    elif kind == 'inference':
        label = 'Inference'
        why = ('The specialist recorded this finding as an Inference: an analytical conclusion from '
               'the cited findings, rather than a directly disclosed fact. The saved validation disposition is '
               + source['disposition'].replace('_', ' ') + '.')
    elif kind == 'calculated_fact':
        label = 'Fact'
        why = ('The saved finding is a calculated fact with bound source inputs. It is grouped under '
               'Fact for display; its calculation and original classification remain in Technical Details.')
    else:
        label = 'Fact'
        why = ('The saved specialist record classifies the finding as Fact, with a '
               + source['disposition'].replace('_', ' ') + ' validation disposition and no recorded '
               'quote-coverage override. This label applies to the finding, not automatically to its credit implications.')
    finding = dict(label=label, kind=label.lower(), reason=why)
    implication_parts = pointers[1]['parts']
    implication = None
    if implication_parts:
        if label == 'Assumption':
            implication = dict(label='Assumption', kind='assumption', reason=(
                'The credit implication depends on a finding whose evidential basis is not established '
                'as Fact under the assessment above. No separately validated field-level classification '
                'is recorded for these credit effects, so they are conservatively shown as Assumptions.'))
        else:
            implication = dict(label='Inference', kind='inference', reason=(
                'This is the specialist\'s analytical interpretation of how the source finding affects '
                'credit quality, rather than a directly disclosed fact. No separate field-level validation '
                'classification was recorded; Inference describes its analytical role, not proof of the outcome.'))
    interpretation = source.get('interpretation') or {}
    specialist = list(dict.fromkeys(t for t in [source.get('credit_mechanism'), interpretation.get('implication')]
                                   if isinstance(t, str) and t.strip()))
    descriptions = [f.get('description') for f in source.get('review_flags', [])]
    notes = [t for t in source.get('validation_notes', [])
             if t not in descriptions and t.partition(': ')[2] not in descriptions]
    qualification = uncertainty or ''
    for boilerplate in ['Qualified source finding.', 'Management-attributed source finding.']:
        qualification = qualification.replace(boilerplate, '').strip()
    gaps = list(dict.fromkeys(t for t in [*source.get('missing_information', []),
        *descriptions, *notes, qualification]
        if isinstance(t, str) and t.strip()))
    return dict(policy_version=POLICY, finding=finding, implication=implication,
                specialist_interpretation=specialist, gaps=gaps,
                original_claim_type=kind, original_disposition=source['disposition'],
                source_hypothesis_id=source['hypothesis_id'], source_agent_id=source['agent_id'],
                scope_note=('These labels are a deterministic presentation of the saved finding and review. '
                            'Separate validation of every displayed magnitude, trend and credit-implication sentence '
                            'was not recorded. No new specialist assessment has been generated.'),
                original_review_flags=deepcopy(source.get('review_flags', [])))
