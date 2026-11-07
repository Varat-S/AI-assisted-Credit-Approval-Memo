"""Bounded canonical context and recoverable M3 assertion checks; no source mutation."""
import re

from .matching import normalized_m3, locate
from .management import DATE_TEXT, natural_date, date_supported

SENTENCE_BREAK = r'(?<![A-Z])(?<!Mr)(?<!Dr)(?<!Ms)(?<!Mrs)\.\s+(?=[A-Z])'


def sentences(text):
    return [s.strip() for s in re.split(SENTENCE_BREAK, normalized_m3(text)) if s.strip()]


def appointment_clause(text, position):
    """Resolve an appointment and its immediate 'this role' continuation only.

    Never borrow an earlier role's date or a director appointment for the CEO.
    """
    from .claims import key
    scope = re.sub(r'(?:\s+and|;)\s+Director$', '', position, flags=re.I)
    parts = sentences(text)
    for index, sentence in enumerate(parts):
        if key(scope) not in key(sentence):
            continue
        if not re.search(r'\b(?:was appointed|has served as|became|has been|was named|joined|serves as|was promoted to)\b', sentence, re.I):
            continue
        current = sentence
        # The same sentence may discuss earlier jobs; its appointment clause
        # ends before historical role transitions.
        current = re.split(r'\b(?:after serving|prior to|previously)\b', current, maxsplit=1, flags=re.I)[0]
        if re.search(r'\b(?:since|effective|in)\s+(?:' + DATE_TEXT + ')', current, re.I):
            return current
        for following in parts[index+1:index+3]:
            if re.search(r'\b(?:He|She) has served in (?:this|that) role since\b', following, re.I):
                return current + '. ' + re.split(r'\bafter serving\b', following, maxsplit=1, flags=re.I)[0]
            if not re.search(r'\b(?:he|she) is responsible\b', following, re.I):
                break
    return None


def scoped_appointment(text, position, supplied_date):
    """A date for a specific office survives without dating every concurrent title."""
    from .claims import key
    source = normalized_m3(text)
    pattern = r'(?:was named|was appointed|was promoted to|\band to)\s+(.{4,140}?)\s+(?:in|since|effective)\s+(' + DATE_TEXT + ')'
    for match in re.finditer(pattern, source, re.I):
        scope = match[1].strip()
        # Appointment to a different office, rank or date remains rejected.
        if (re.search(r'\b(?:Chief .{1,75}Officer|President)\b', scope, re.I)
                and key(scope) in key(position)
                and natural_date(match[2]) == supplied_date):
            return scope
    return None


def date_assertions(role, text):
    """Return only supplied dates explicitly bound to the role; no guessed ends."""
    from .management import prior_role_date_pairs, date_interval
    value = dict(role)
    dropped = []
    pairs = prior_role_date_pairs(normalized_m3(role['position']), text)
    for field, side in [('start_date', 0), ('end_date', 1)]:
        date = role.get(field, '')
        try:
            supported = bool(date and date_supported(date, text))
        except ValueError:
            supported = False
        if pairs:
            supported = supported and any(pair[side] == date for pair in pairs)
        # An end year elsewhere in a multi-role sentence is not a role end.
        else:
            # A role-local promotion/join sentence with exactly one disclosed
            # date can establish a start, never an inferred end date.
            from .claims import key
            local = [s for s in sentences(text) if key(role['position']) in key(s)]
            starts = []
            position_pattern = r'\b' + r'\W+'.join(re.escape(w) for w in re.findall(r'\w+', normalized_m3(role['position']))) + r'\b'
            for sentence in local:
                match = re.search(position_pattern, sentence, re.I)
                direct = re.match(r'\s+(?:since|effective|in)\s+(' + DATE_TEXT + ')', sentence[match.end():], re.I) if match else None
                if direct:
                    starts.append(natural_date(direct[1]))
            if starts:
                supported = supported and field == 'start_date' and set(starts) == {date}
                if date and not supported:
                    dropped.append(field)
                value[field] = date if supported else ''
                continue
            for sentence in local:
                values = re.findall(r'\b(?:since|effective|in)\s+(' + DATE_TEXT + ')', sentence, re.I)
                if len(values) == 1 and re.search(r'\b(?:joined|promoted|named|appointed|served|became)\b', sentence, re.I):
                    starts.append(natural_date(values[0]))
            supported = supported and field == 'start_date' and starts == [date]
        if date and not supported:
            dropped.append(field)
        value[field] = date if supported else ''
    if value['start_date'] and value['end_date']:
        if date_interval(value['start_date'])[0] > date_interval(value['end_date'])[1]:
            dropped.extend(['start_date', 'end_date'])
            value.update(start_date='', end_date='')
    return value, dropped


def retention_guard(statement, quotes, executive, roster):
    """Constrain model entailment recovery: exact quotes, names and numeric values.

    Semantic entailment is assessed by the bounded reviewer, not a token overlap
    threshold. No date/number substitution or evidence about another executive.
    """
    from .claims import key
    if not statement.strip() or not quotes:
        raise ValueError('No retained factual assertion or supporting quotation')
    text = normalized_m3(' '.join(q['original_source_text'] for q in quotes))
    for number in re.findall(r'\b\d+(?:[.,]\d+)*\b', statement):
        if not re.search(r'(?<!\d)' + re.escape(number) + r'(?!\d)', text):
            raise ValueError('Retained statement contains an unstated number or date')
    if executive:
        for row in roster:
            if key(row['name']) != key(executive) and key(row['name']) in key(statement):
                raise ValueError('Retained statement attributes another executive’s evidence')
    return text


def judgment_scope(judgment, referenced_names):
    """Recognize an explicitly named joint judgment; never infer a team from citations alone."""
    from .claims import key
    named = {key(n) for n in referenced_names if n}
    executive = judgment.get('executive') or ''
    scope = judgment.get('scope') or ('individual' if executive else 'team')
    declared = {key(n) for n in judgment.get('executives', []) if n}
    if scope in {'team', 'company'} and declared:
        return scope, named <= declared
    if not executive:
        return scope, True
    if named <= {key(executive)}:
        return 'individual', True
    # Legacy joint judgments were sometimes tagged to one of the two executives.
    # Upgrade only when every referenced person is explicitly named in the
    # ORIGINAL explanation; record the scope correction in judgment_results.
    if len(named) > 1 and all(n in key(judgment['explanation']) for n in named):
        return 'team', True
    return 'individual', False
