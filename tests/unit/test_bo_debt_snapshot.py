from copy import deepcopy

from app.services.bo.debt_snapshot import build_snapshot, annotate_svg


def structure(name='HCA Healthcare, Inc.'):
    return {'companies': {'hca': {'nodes': [
        {'role': 'Borrower', 'display_name': name, 'box': {
            'center_x_px': 720, 'top_y_px': 446, 'width_px': 310, 'height_px': 90}}]}},
        'visual_spec': {'canvas': {'width_px': 1440, 'height_px': 1080},
                        'legend': {'x_px': 1180, 'y_px': 30}}}


def debt():
    return {'senior_notes_schedule': [
        {'legal_borrower': 'HCA Inc.', 'principal_amount_m': n,
         'priority_ranking_tier': 'tier_2_senior_unsecured_guaranteed'} for n in (125, 40541, 450)],
        'non_note_obligations_schedule': [
            {'legal_borrower': 'HCA Inc.', 'principal_drawn_m': 1238,
             'available_facility_limit_m': None, 'obligation_facility': 'Term loan',
             'priority_ranking_tier': 'tier_1_direct_opco_secured'},
            {'legal_borrower': 'HCA Inc. and designated subsidiary borrowers', 'principal_drawn_m': 0,
             'available_facility_limit_m': 4500, 'obligation_facility': 'ABL Revolving facility',
             'priority_ranking_tier': 'tier_1_direct_opco_secured'},
            {'legal_borrower': 'HCA Inc.', 'principal_drawn_m': 0,
             'available_facility_limit_m': 3486, 'obligation_facility': 'Revolving facility',
             'priority_ranking_tier': 'tier_1_direct_opco_secured'},
            {'legal_borrower': 'Operating subsidiaries / HCA Inc.', 'principal_drawn_m': 1046,
             'available_facility_limit_m': None, 'obligation_facility': 'Finance leases and other debt',
             'priority_ranking_tier': 'tier_1_direct_opco_secured'}]}


def test_scoped_amounts_priority_mapping_warning_and_no_mutation():
    s, d = structure(), debt()
    before = deepcopy((s, d))
    snapshot = build_snapshot(s, d)
    assert [r['amount'] for r in snapshot['rows']] == ['1.24', '41.12', '7.99']
    assert [r['detail'] for r in snapshot['rows']] == [
        'Tier 1 · Secured', 'Tier 2 · Guaranteed', '']
    assert snapshot['excluded_count'] == 1
    assert snapshot['note'] == 'Entity mapping pending'
    assert snapshot['scope_note'] == 'Co-borrower facilities included'
    snapshot['as_of'] = '2024-12-31'
    svg, placed = annotate_svg('<svg></svg>', s, snapshot)
    assert placed and 'stroke-dasharray' in svg and '41.12' in svg
    assert 'Entity mapping pending' not in svg
    assert 'Debt Snapshot' in svg
    from xml.etree import ElementTree
    card = ElementTree.fromstring(svg).find('.//rect')
    assert float(card.attrib['x']) + float(card.attrib['width']) < 565
    assert '31/12/2024' in svg and '2024-12-31' not in svg
    assert snapshot['note'] == 'Entity mapping pending'
    assert (s, d) == before


def test_missing_values_do_not_become_zero_or_partial_totals():
    d = debt()
    d['senior_notes_schedule'][0]['principal_amount_m'] = None
    d['non_note_obligations_schedule'][1]['available_facility_limit_m'] = None
    snapshot = build_snapshot(structure('HCA Inc.'), d)
    assert snapshot['matched']
    assert snapshot['rows'][1]['amount'] == 'Not Recorded'
    assert snapshot['rows'][2]['amount'] == 'Not Recorded'
    assert 'stroke-dasharray' not in annotate_svg('<svg></svg>', structure('HCA Inc.'), snapshot)[0]


def test_slash_in_borrower_legal_name_is_not_group_debt():
    name = 'CHS/Community Health Systems, Inc.'
    d = {'senior_notes_schedule': [
        {'legal_borrower': name, 'principal_amount_m': n,
         'priority_ranking_tier': 'tier_1_direct_opco_secured'} for n in (644, 1244)] + [
        {'legal_borrower': name, 'principal_amount_m': 42,
         'priority_ranking_tier': 'tier_2_senior_unsecured_guaranteed'}],
        'non_note_obligations_schedule': [
            {'legal_borrower': name + ' and subsidiaries', 'principal_drawn_m': 345,
             'available_facility_limit_m': None, 'obligation_facility': 'Finance lease and financing obligations',
             'priority_ranking_tier': 'tier_1_direct_opco_secured'},
            {'legal_borrower': 'CHS / Subsidiaries', 'principal_drawn_m': 10,
             'available_facility_limit_m': None, 'obligation_facility': 'Other debt',
             'priority_ranking_tier': 'tier_1_direct_opco_secured'}]}
    snapshot = build_snapshot(structure(name), d)
    assert snapshot['entity'] == name and snapshot['matched']
    assert [r['amount'] for r in snapshot['rows']] == ['1.89', '0.04']
    assert snapshot['excluded_count'] == 2
    assert snapshot['scope_note'] == 'Recorded borrower obligations'


def test_ambiguous_issuer_and_missing_source_are_not_guessed():
    d = debt()
    d['senior_notes_schedule'].append({**d['senior_notes_schedule'][0], 'legal_borrower': 'Another issuer'})
    assert build_snapshot(structure(), d) is None
    assert build_snapshot(structure(), None) is None
    assert build_snapshot(None, d) is None


def test_no_room_falls_back_without_covering_diagram_and_escapes_names():
    s, d = structure('HCA Inc.'), debt()
    snapshot = build_snapshot(s, d)
    s['visual_spec']['canvas']['width_px'] = 920
    s['companies']['hca']['nodes'].append({'role': 'OpCo', 'display_name': 'Left node',
        'box': {'center_x_px': 300, 'top_y_px': 400, 'width_px': 420, 'height_px': 180}})
    assert annotate_svg('<svg></svg>', s, snapshot) == ('<svg></svg>', False)
    s = structure()
    snapshot['entity'] = '<script>bad</script>'
    svg, placed = annotate_svg('<svg></svg>', s, snapshot)
    assert placed and '<script>' not in svg and '&lt;script&gt;' in svg
