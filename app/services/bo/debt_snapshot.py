"""Read-only diagram annotation from the selected run's debt schedules.

No obligor inference: exact names are preferred; an unmatched, unique note
issuer is explicitly provisional. Shared slash-delimited obligations stay in
the complete schedules rather than being assigned to the diagram borrower.
"""
from datetime import date
from decimal import Decimal
from html import escape
import re


def format_date(value):
    try:
        return date.fromisoformat(value).strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        return 'Not Recorded'


def _name(value):
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


def _amount(rows):
    values = [r[1] for r in rows]
    if any(v is None for v in values):
        return 'Not Recorded'
    return f'{sum((Decimal(str(v)) for v in values), Decimal(0)) / 1000:,.2f}'


def build_snapshot(structure, debt):
    if not structure or not debt:
        return None
    companies = list(structure['companies'].values())
    if len(companies) != 1:
        return None
    nodes = companies[0]['nodes']
    borrowers = [n for n in nodes if n['role'].lower() == 'borrower']
    if len(borrowers) != 1:
        return None
    borrower = borrowers[0]
    notes = debt.get('senior_notes_schedule', [])
    facilities = debt.get('non_note_obligations_schedule', [])
    names = {r['legal_borrower'] for r in [*notes, *facilities]
             if r.get('legal_borrower') and '/' not in r['legal_borrower']
             and not re.search(r'\band\b', r['legal_borrower'], re.I)}
    exact = [n for n in names if _name(n) == _name(borrower['display_name'])]
    issuers = {r['legal_borrower'] for r in notes if r.get('legal_borrower') in names}
    name = exact[0] if len(exact) == 1 else next(iter(issuers)) if len(issuers) == 1 else None
    if not name:
        return None
    matched = _name(name) == _name(borrower['display_name'])
    def belongs(row):
        legal = row.get('legal_borrower') or ''
        # Explicit co-borrowers are included, never slash-delimited group debt.
        return (_name(legal) == _name(name) or
                ('/' not in legal and re.match(re.escape(name) + r'\s+and\b', legal, re.I)))
    scoped_notes = [r for r in notes if belongs(r)]
    scoped_facilities = [r for r in facilities if belongs(r)]
    tiers = [
        ('tier_1_direct_opco_secured', 'Senior Secured Debt', 'Tier 1 · Secured'),
        ('tier_2_senior_unsecured_guaranteed', 'Unsecured Notes / Debt', 'Tier 2 · Guaranteed'),
        ('tier_3_unguaranteed_holdco', 'Unguaranteed Holding Debt', 'Tier 3 · Holding Company'),
    ]
    rows = []
    for tier, label, detail in tiers:
        amounts = [(r, r.get('principal_amount_m')) for r in scoped_notes if r.get('priority_ranking_tier') == tier]
        amounts += [(r, r.get('principal_drawn_m')) for r in scoped_facilities if r.get('priority_ranking_tier') == tier]
        if amounts:
            rows.append({'label': label, 'detail': detail, 'amount': _amount(amounts)})
    limits = [r for r in scoped_facilities if r.get('available_facility_limit_m') is not None
              or 'revolv' in r.get('obligation_facility', '').lower()]
    if limits:
        rows.append({'label': 'Facility Limits', 'detail': '',
                     'amount': _amount([(r, r.get('available_facility_limit_m')) for r in limits])})
    if not rows:
        return None
    return {'entity': name, 'matched': matched, 'borrower': borrower,
            'rows': rows, 'note': 'Exact entity match' if matched else 'Entity mapping pending',
            'scope_note': 'Co-borrower facilities included' if any(_name(r['legal_borrower']) != _name(name) for r in scoped_facilities)
                          else 'Recorded borrower obligations',
            'excluded_count': len(notes) + len(facilities) - len(scoped_notes) - len(scoped_facilities)}


def annotate_svg(svg, structure, snapshot):
    """Place a compact SVG card in free space; never cover recorded geometry."""
    if not snapshot:
        return svg, False
    spec = structure['visual_spec']
    canvas = spec['canvas']
    b = snapshot['borrower']['box']
    width = 440
    height = 78 + (len(snapshot['rows']) - 1) * 50 + (48 if snapshot['rows'][-1]['detail'] else 26)
    right = b['center_x_px'] + b['width_px'] / 2
    left = b['center_x_px'] - b['width_px'] / 2
    obstacles = [(n['box']['center_x_px'] - n['box']['width_px']/2, n['box']['top_y_px'],
                  n['box']['width_px'], n['box']['height_px'])
                 for c in structure['companies'].values() for n in c['nodes']]
    for company in structure['companies'].values():
        for path in company.get('connector_paths', []):
            for start, end in zip(path['points'], path['points'][1:]):
                obstacles.append((min(start[0], end[0]), min(start[1], end[1]),
                                  abs(end[0]-start[0]), abs(end[1]-start[1])))
    legend = spec['legend']
    obstacles.append((legend['x_px'], legend['y_px'], 255, 250))
    # Balance the right-hand legend with a card on the borrower's left.
    # If that space is occupied, use the existing below-diagram fallback.
    base_y = max(150, b['top_y_px'] + b['height_px'] - height)
    placement = None
    for x in [left - width - 60]:
        y = max(base_y, legend['y_px'] + 266) if x < legend['x_px']+255 and x+width > legend['x_px'] else base_y
        if x < 24 or x + width > canvas['width_px'] - 24 or y + height > canvas['height_px'] - 40:
            continue
        if any(x < ox+ow+12 and x+width > ox-12 and y < oy+oh+12 and y+height > oy-12
               for ox, oy, ow, oh in obstacles):
            continue
        placement = x
        break
    if placement is None:
        return svg, False
    x = placement
    edge = right if x > right else left
    end = x if x > right else x + width
    cy = b['top_y_px'] + b['height_px']/2
    parts = [f'<g class="bo-debt-snapshot" role="group" aria-label="Debt Snapshot For {escape(snapshot["entity"], quote=True)}">',
             f'<path d="M{edge},{cy} H{end}" class="bo-snapshot-link"' + (' stroke-dasharray="5 4"' if not snapshot['matched'] else '') + '/>',
             f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" class="bo-snapshot-surface"/>']
    def text(dx, dy, value, cls=''):
        parts.append(f'<text x="{x+dx}" y="{y+dy}" class="bo-snapshot-text {cls}">{escape(str(value))}</text>')
    title = snapshot['entity']
    text(18, 29, (title if len(title) < 25 else title[:21] + '…') + ' · Debt Snapshot', 'bo-snapshot-title')
    text(18, 53, f'{format_date(snapshot.get("as_of"))} · US$ Bn, Rounded', 'bo-snapshot-muted')
    for index, row in enumerate(snapshot['rows']):
        dy = 82 + index * 50
        text(18, dy, row['label'])
        text(width - 18, dy, row['amount'], 'bo-snapshot-value')
        if row['detail']:
            text(18, dy+22, row['detail'], 'bo-snapshot-muted')
    parts.append('</g>')
    return svg.rsplit('</svg>', 1)[0] + ''.join(parts) + '</svg>', True
