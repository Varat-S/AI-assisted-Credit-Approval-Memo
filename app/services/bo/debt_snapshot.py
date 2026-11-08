"""Read-only diagram annotation from the selected run's debt schedules.

No obligor inference: exact names are preferred; an unmatched, unique note
issuer is explicitly provisional. Shared slash-delimited obligations stay in
the complete schedules rather than being assigned to the diagram borrower;
a slash inside the diagram borrower's own legal name (CHS/Community Health
Systems, Inc.) is not a delimiter. Role notes the model adds to a legal name
('HCA Inc. (OpCo)', 'HCA Inc. (Issuer); HCA Healthcare, Inc. (Guarantor)')
are removed before names are compared.
"""
from datetime import date
from decimal import Decimal
from html import escape
import re
import textwrap


def format_date(value):
    try:
        return date.fromisoformat(value).strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        return 'Not Recorded'


def _name(value):
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


# "X and subsidiaries" (or "and operating affiliates") is group debt like
# "X / Subsidiaries", not a co-borrower.
_GROUP_SUFFIX = re.compile(r'\s+and\s+(its\s+)?([a-z]+\s+)?(subsidiaries|affiliates)\b', re.I)
_ANNOTATION = re.compile(r'\s*\([^)]*\)')
# Committed facilities with availability: revolvers and asset-based (ABL) lines.
_BORROWING_BASE = re.compile(r'\bABL\b|asset[- ]based', re.I)
_REVOLVER = re.compile(r'revolv|\bABL\b|asset[- ]based', re.I)


def _legal(value):
    """The bare legal name: parenthesised role notes and a guarantor tail removed.

    'X (Issuer) / Y (Guarantor)' and 'X; Y (Guarantor)' name X's credit support,
    not a co-borrower, so they are X. Any other slash is left for ``shared``.
    """
    value = value or ''
    head, *rest = re.split(r'\s*[;/]\s*', value)
    if rest and all(re.search(r'guarant', part, re.I) for part in rest):
        value = head
    return _ANNOTATION.sub('', value).strip()


def _amount(rows):
    values = [r[1] for r in rows]
    if any(v is None for v in values):
        return 'Not Recorded'
    return f'{sum((Decimal(str(v)) for v in values), Decimal(0)) / 1000:,.2f}'


def build_snapshot(structure, debt, *, ticker=None):
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
    def shared(legal):
        return '/' in legal and _name(legal) != _name(borrower['display_name'])
    def legal_of(row):
        return _legal(row.get('legal_borrower'))
    names = {legal_of(r) for r in [*notes, *facilities]
             if legal_of(r) and not shared(legal_of(r))
             and not re.search(r'\band\b', legal_of(r), re.I)}
    exact = [n for n in names if _name(n) == _name(borrower['display_name'])]
    issuers = {legal_of(r) for r in notes if legal_of(r) in names}
    name = exact[0] if len(exact) == 1 else next(iter(issuers)) if len(issuers) == 1 else None
    if not name:
        return None
    matched = _name(name) == _name(borrower['display_name'])
    def belongs(row):
        legal = legal_of(row)
        # Explicit co-borrowers are included, never slash-delimited or "and subsidiaries" group debt.
        return (_name(legal) == _name(name) or
                (not shared(legal) and not _GROUP_SUFFIX.search(legal)
                 and re.match(re.escape(name) + r'\s+and\b', legal, re.I)))
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
    # Undrawn availability as the filing states it; a backstopped program
    # (commercial paper) carries none, so it is never counted twice.
    limits = [r for r in scoped_facilities if r.get('available_facility_limit_m') is not None
              or _REVOLVER.search(r.get('obligation_facility', ''))]
    if limits:
        based = any(_BORROWING_BASE.search(r.get('obligation_facility', '')) for r in limits)
        rows.append({'label': 'Undrawn Availability',
                     'detail': 'Subject to borrowing base' if based else '',
                     'amount': _amount([(r, r.get('available_facility_limit_m')) for r in limits])})
    if not rows:
        return None
    return {'entity': name, 'ticker': ticker, 'title': f'{ticker} · Debt Snapshot' if ticker else 'Debt Snapshot', 'matched': matched, 'borrower': borrower,
            'rows': rows, 'note': 'Exact entity match' if matched else 'Entity mapping pending',
            'scope_note': 'Co-borrower facilities included' if any(_name(legal_of(r)) != _name(name) for r in scoped_facilities)
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
    # Reserve separate label/value columns and wrap before placing the card.
    # Conservative Arial width bounds keep long labels and missing values inside.
    def lines(value, available, size):
        return textwrap.wrap(str(value), width=max(1, int(available / (size * .65))),
                             break_long_words=True, break_on_hyphens=False) or ['']
    title_lines = lines(snapshot.get('title', 'Debt Snapshot'), width - 36, 21)
    caption_y = 29 + (len(title_lines) - 1) * 25 + 24
    rows, cursor = [], caption_y + 29
    for row in snapshot['rows']:
        label = lines(row['label'], 260, 18)
        amount = lines(row['amount'], 128, 18)
        detail = lines(row['detail'], width - 36, 16) if row['detail'] else []
        detail_y = cursor + max(len(label), len(amount)) * 22
        rows.append((cursor, label, amount, detail_y, detail))
        cursor = detail_y + len(detail) * 20 + 12
    height = cursor - 12 + 18
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
    for index, line in enumerate(title_lines):
        text(18, 29 + index * 25, line, 'bo-snapshot-title')
    text(18, caption_y, f'{format_date(snapshot.get("as_of"))} · US$ Bn, Rounded', 'bo-snapshot-muted')
    for baseline, label, amount, detail_y, detail in rows:
        for index, line in enumerate(label):
            text(18, baseline + index * 22, line)
        for index, line in enumerate(amount):
            text(width - 18, baseline + index * 22, line, 'bo-snapshot-value')
        for index, line in enumerate(detail):
            text(18, detail_y + index * 20, line, 'bo-snapshot-muted')
    parts.append('</g>')
    return svg.rsplit('</svg>', 1)[0] + ''.join(parts) + '</svg>', True
