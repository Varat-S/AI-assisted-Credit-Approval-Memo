"""Conservative display labels from frozen classifications and review flags.

This is a versioned presentation policy, not a new specialist or validation
result. Canonical types, findings, validation decisions and governance stay intact.
"""
from copy import deepcopy

POLICY = 'bo-finding-display-2.0.0'


def assessment(source, pointers, uncertainty=None, verified_quotes=None):
    from app.services.bo.hypotheses import normalise
    kind = source['claim_type']
    flags = {f.get('rule_id') for f in source.get('review_flags', [])}
    attributed = kind == 'management_claim' or source.get('admissibility') == 'attributed'
    uncovered = 'quote_does_not_cover_claim' in flags
    hypothetical = 'generic_risk_disclosure_only' in flags
    quotes = [normalise(q['quote']) for q in verified_quotes or []]
    def directly_quoted(text):
        return bool(normalise(text)) and any(normalise(text) in q for q in quotes)
    direct_finding = directly_quoted(source.get('claim', ''))
    if kind == 'assumption':
        label = 'Assumption'
        why = 'The specialist explicitly recorded this statement as an adopted premise, not a verified fact or an analytical conclusion.'
    elif uncovered and not direct_finding:
        label = 'Inference'
        why = ('The saved validator says the quotation does not state the claim and treats it as the '
               "specialist's inference. An inadequately supported conclusion remains an Inference; "
               'it is not an explicitly adopted Assumption.')
    elif kind == 'inference':
        label = 'Inference'
        why = 'The specialist recorded an analytical conclusion drawn from source findings, rather than a directly disclosed fact.'
    elif kind == 'calculated_fact':
        label = 'Fact'
        why = 'This is a recorded calculated fact using bound inputs. Its calculation and original classification remain in Technical Details.'
    elif kind == 'management_claim':
        label = 'Fact'
        why = ('Fact identifies the recorded management statement, not independent proof of its underlying '
               'outcome. Management attribution is addressed separately in the support assessment.')
    else:
        label = 'Fact'
        why = ('The saved specialist record identifies a factual disclosure. A qualification, '
               'management attribution or hypothetical context does not itself turn a disclosure into an Assumption.')
    if source['disposition'] in {'rejected', 'unverified'} or (uncovered and not direct_finding):
        support = 'Unsupported'
        support_why = ('The cited record does not establish this claim as stated. The saved quote-coverage '
                       'flag is a heuristic, not a fresh semantic review; the original validator disposition '
                       'is preserved as ' + source['disposition'].replace('_', ' ') + '.' if uncovered else
                       'The saved validator disposition is ' + source['disposition'].replace('_', ' ') +
                       '; support is not established. This does not change the statement type.')
    elif (kind == 'assumption' or attributed or hypothetical or uncovered or source['disposition'] == 'qualified'
          or any(f.get('effect') == 'qualify' for f in source.get('review_flags', []))):
        support = 'Qualified'
        if kind == 'assumption':
            support_why = 'This premise was explicitly adopted without verification. Acceptance of a scenario premise is not evidence that it is true.'
        elif attributed:
            support_why = 'The statement is management-attributed; independent verification of the underlying outcome is not recorded.'
        elif hypothetical:
            support_why = 'The source discloses a possible risk or scenario, not evidence that the event occurred. It must be read in that context.'
        elif direct_finding and uncovered:
            support_why = 'The finding matches a verified quotation, but a saved quote-coverage flag remains unresolved and requires review.'
        else:
            support_why = 'The saved validation record qualifies this finding. The recorded limitations are retained in Assumptions / Gaps.'
    else:
        support = 'Supported'
        support_why = 'The saved validation record supports this finding within its recorded evidence scope; this is not a new validation result.'
    finding = dict(label=label, kind=label.lower(), reason=why, support=support, support_reason=support_why)
    parts = pointers[1]['parts']
    implication = None
    if parts:
        if all(part['text'].strip().lower().startswith('assumption:') for part in parts):
            implication = dict(label='Assumption', kind='assumption',
                reason='The credit-implication text explicitly identifies itself as an Assumption: an adopted premise.',
                support='Qualified', support_reason='This premise is explicitly adopted, not verified by its adoption.')
        elif all(directly_quoted(part['text']) for part in parts):
            implication = dict(label='Fact', kind='fact',
                reason='Every displayed credit-implication statement is directly contained in a verified source quotation.',
                support='Supported', support_reason='The wording is directly supported as a disclosure; that does not independently prove a reported future outcome.')
        else:
            implication = dict(label='Inference', kind='inference',
                reason=("This is the specialist's analytical conclusion about credit effects. "
                        'Its type is independent of the Finding label; reasoning from an assumption is still an Inference.'),
                support='Unsupported' if support == 'Unsupported' else 'Qualified',
                support_reason=('The underlying finding is not established by the cited record, and no separate '
                                'field-level support for these credit effects is recorded.' if support == 'Unsupported' else
                                'Separate field-level validation of these credit effects was not recorded. '
                                'The conclusion remains conditional on its cited facts, premises and limitations.'))
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
                scope_note=('Statement type and evidence support are assessed separately by a deterministic presentation policy. '
                            'Separate validation of every displayed magnitude, trend and credit-implication sentence '
                            'was not recorded. No new specialist assessment has been generated.'),
                original_review_flags=deepcopy(source.get('review_flags', [])))
