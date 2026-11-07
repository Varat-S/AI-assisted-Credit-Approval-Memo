"""M3 claim-level evidence admission; qualitative decisions belong to Validator 7."""
from datetime import date
import re

from .contracts import validate_extraction
from .matching import match_citation, normalized_m3, mapped_text, locate


def key(value):
    return ' '.join(re.findall(r'[a-z0-9]+',normalized_m3(value).casefold()))


class ClaimValidator:
    def __init__(self,sources):
        self.sources=sources
        self.claims=[]
        self.full=''
        self.starts={}
        prior_page=None
        self.proxy=getattr(sources,'document_kind','10-K')=='DEF 14A'
        breaks=[]
        for sid in sources.section_ids:
            page=sources.physical_pages.get(sid)
            if self.full and page!=prior_page:
                self.full+='\n'
            elif self.full and self.proxy and sources.passage_offsets.get(sid)!=prior_end:
                # Non-contiguous proxy passages (director biography, officer section).
                breaks.append(len(self.full)); self.full+='\n'
            self.starts[sid]=len(self.full)
            self.full+=sources.pages[sid]
            prior_page=page
            prior_end=sources.passage_offsets.get(sid,0)+len(sources.pages[sid])
        self.biographies={}
        if self.proxy:
            from .sources import proxy_bio_starts, proxy_boundaries
            heads={key(n):p for p,n in proxy_bio_starts(self.full)}
            ends=sorted(set(proxy_boundaries(self.full))|set(breaks)|{len(self.full)})
            for row in sources.expected_roster:
                start=heads.get(key(row['name']))
                if start is not None:
                    self.biographies[key(row['name'])]=(start,next(e for e in ends if e>start))
            return
        text,mapping=mapped_text(self.full,pdf=True)
        beginnings=[]
        for row in sources.expected_roster:
            name=normalized_m3(row['name']).rstrip('.')
            pattern=re.escape(name).replace(r'\ ',r'\s+')+r'\.?\s+(?:was appointed|has served|has been|became)\b'
            matches=list(re.finditer(pattern,text,re.I))
            if len(matches)==1:
                beginnings.append((mapping[matches[0].start()],key(name)))
        beginnings.sort()
        for i,(start,name) in enumerate(beginnings):
            end=beginnings[i+1][0] if i+1<len(beginnings) else len(self.full)
            boundary=re.search(r'^Item\s+\d+[A-Z]?\.',self.full[start:end],re.M|re.I)
            self.biographies[name]=(start,start+boundary.start() if boundary else end)

    def biography(self,name):
        span=self.biographies.get(key(name))
        return normalized_m3(self.full[slice(*span)]) if span else ''

    def biography_fragments(self, name):
        """Canonical pieces of one bounded biography; preserve IDs and offsets."""
        span = self.biographies.get(key(name))
        if not span:
            return []
        pieces = []
        for sid in self.sources.section_ids:
            start = self.starts[sid]
            lo, hi = max(span[0], start), min(span[1], start + len(self.sources.pages[sid]))
            if hi > lo:
                pieces.append({'source_id': sid, 'quote': self.sources.pages[sid][lo-start:hi-start]})
        return pieces

    def boundary_citations(self, source_id, quote, name):
        """Recover a verbatim quotation split across adjacent canonical chunks."""
        bio = self.biographies.get(key(name))
        if not bio or source_id not in self.sources.section_ids:
            return []
        match = locate(self.full, quote)
        if not match or not (bio[0]<=match['span_start'] and match['span_end']<=bio[1]):
            return []
        lo, hi = match['span_start'], match['span_end']
        members = [(sid, self.starts[sid], self.starts[sid]+len(self.sources.pages[sid]))
                   for sid in self.sources.section_ids if self.starts[sid]<hi
                   and self.starts[sid]+len(self.sources.pages[sid])>lo]
        if len(members)<2 or source_id not in {sid for sid,_,_ in members}:
            return []
        # No non-contiguous proxy spans or cross-person joins.
        if any(a[2]!=b[1] for a,b in zip(members,members[1:])):
            return []
        result=[]
        for sid,start,end in members:
            left,right=max(lo,start),min(hi,end)
            if right-left<12:
                left=max(start,bio[0],left-180)
                right=min(end,bio[1],max(right,left+12))
            a,b=left-start,right-start
            fragment=self.sources.pages[sid][a:b]
            result.append({'source_id':sid,'quote':fragment,'document_id':self.sources.document_id,
                'source_sha256':self.sources.sha256,'physical_page':self.sources.physical_pages.get(sid,1),
                'passage_offset':self.sources.passage_offsets.get(sid,0),
                'span_start':a,'span_end':b,'original_source_text':fragment,
                'normalized_quote':normalized_m3(fragment),'matching_method':'canonical_boundary_fragments',
                'quotation_check':'passed','outcome':'accepted',
                'page_char_start':self.sources.passage_offsets.get(sid,0)+a,
                'page_char_end':self.sources.passage_offsets.get(sid,0)+b,
                'recovery_basis':'Exact original quotation spans adjacent chunks in the same executive biography'})
        return result

    def citations(self,items,name=''):
        results=[]
        seen=set()
        for item in items:
            signature=(item['source_id'],item['quote'])
            if signature in seen: continue
            seen.add(signature)
            result=match_citation(self.sources,*signature)
            if result['outcome']=='unsupported' and name:
                recovered=self.boundary_citations(item['source_id'],item['quote'],name)
                if recovered:
                    results.append({**result,'recovery':'Recovered as separate adjacent canonical fragments'})
                    results.extend(recovered)
                    continue
            if result['outcome']=='accepted' and name:
                bio=self.biographies.get(key(name))
                start=self.starts.get(item['source_id'],0)+result['span_start']
                end=self.starts.get(item['source_id'],0)+result['span_end']
                if not bio or not (bio[0]<=start and end<=bio[1]):
                    result.update(outcome='unsupported',quotation_check='failed',
                                  reason='Incorrect executive attribution: quotation is outside this executive biography')
            results.append(result)
        return results

    def admit(self,cid,kind,name,statement,items,check=None):
        citations=self.citations(items,name if kind!='identity' else '')
        accepted=[c for c in citations if c['outcome']=='accepted']
        accepted.sort(key=lambda c:(self.starts.get(c['source_id'],0)+c['span_start']))
        text=normalized_m3(''.join(c['original_source_text'] for c in accepted))
        claim={'claim_id':cid,'kind':kind,'executive':name,'statement':statement,
               'outcome':'accepted','reason':'Claim is supported by its declared canonical citations',
               'citation_results':citations,'citations':accepted}
        original=''.join(c['original_source_text'] for c in accepted)
        claim['semantic_matching']={
            'method':'pdf_word_boundaries' if normalized_m3(original)!=mapped_text(original,pdf=False)[0].strip() else 'whitespace_typography',
            'comparison_text':text,'policy':'M3-only; no letter, digit, name, date, title or negation substitutions',
        }
        try:
            if not accepted: raise ValueError('No accurate, correctly attributed declared citation survives')
            if check: check(text,claim)
            if any(c['outcome']=='unsupported' for c in citations):
                claim.update(outcome='qualified',reason='Supported by the remaining declared citations; inaccurate citation(s) excluded')
        except ValueError as exc:
            claim.update(outcome='unsupported',reason=str(exc),citations=[])
        self.claims.append(claim)
        return claim


def assess_claims(payload,sources,reviewer=None,enforce=True):
    # enforce=False (validators off): Validator 7 still reviews when it can, but a
    # judgment it would withhold or rewrite keeps the specialist's own text as a
    # qualified observation. Evidence claims and identity checks stay as they are.
    from .management import date_interval, date_supported, natural_date, DATE_TEXT, review_window, recency, prior_role_date_pairs, compact_citations
    from .employers import internal_employer

    validate_extraction(payload)
    validator=ClaimValidator(sources)
    expected={key(r['name']):r for r in sources.expected_roster}
    names=[key(p['name']) for p in payload['executives']]
    if len(names)!=len(set(names)): raise ValueError('Duplicate executive in extraction')
    facts_ids=[f['fact_id'] for f in payload['facts']]
    judgment_ids=[j['judgment_id'] for j in payload['judgments']]
    if len(facts_ids)!=len(set(facts_ids)) or len(judgment_ids)!=len(set(judgment_ids)):
        raise ValueError('Duplicate fact or judgment identity')

    def roster_check(text,claim):
        anchor=payload['roster_date']
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',anchor): raise ValueError('Roster date needs disclosed day precision')
        if not date_supported(anchor,text) or not re.search(r'as of.{0,50}(?:executive|officer)',text,re.I):
            raise ValueError('Roster date is not supported by its declared quotation')
        declared=re.findall(r'As\s+of\s+(\w+\s+\d{1,2},?\s+\d{4}),?\s+(?:our\s+)?executive\s+officers',normalized_m3(validator.full),re.I)
        if len(set(declared))!=1 or not date_supported(anchor,declared[0]):
            raise ValueError('Selected section does not establish one consistent roster date')
        if date.fromisoformat(anchor)<date.fromisoformat(sources.filing_period):
            raise ValueError('Roster date precedes selected filing period')
    if validator.proxy:
        # A proxy's officer table states no as-of date: no roster-date claim is made,
        # so recency and tenure are not calculated rather than counted as a failure.
        roster=None
        window=None
    else:
        roster=validator.admit('roster','roster','',payload['roster_quote'],
            [{'source_id':payload['roster_source_id'],'quote':payload['roster_quote']}],roster_check)
        window=review_window(payload['roster_date']) if roster['outcome']!='unsupported' else None
    profiles=[]
    profile_map={}
    for i,raw in enumerate(payload['executives'],1):
        name=raw['name']; prefix=f'executive:{i}'
        def identity_check(text,claim):
            row=expected.get(key(name))
            if row is None: raise ValueError('Executive is not in selected canonical roster')
            if key(name) not in key(text): raise ValueError('Roster quotation does not identify this executive')
        row=expected.get(key(name),{})
        roster_sid=row.get('source_id',payload['roster_source_id'])
        lines=sources.pages.get(roster_sid,'').splitlines()
        roster_line=next((line for line in lines
                          if key(name) in key(line) and re.search(r'\b\d{2,3}\b',line)),None)
        if roster_line is None:
            # An SEC HTML table stacks name, age and position on separate lines.
            roster_line=next(('\n'.join(lines[j:j+3]) for j,line in enumerate(lines)
                              if key(line)==key(name) and j+1<len(lines)
                              and re.fullmatch(r'\d{2,3}',lines[j+1].strip())),payload['roster_quote'])
        identity=validator.admit(prefix+':identity','identity',name,name,
            [{'source_id':roster_sid,'quote':roster_line}],identity_check)
        def position_check(text,claim):
            if not raw['position'].strip() or key(raw['position']) not in key(row.get('position','')):
                raise ValueError('Position differs from disclosed roster')
        position=validator.admit(prefix+':position','identity',name,raw['position'],
            [{'source_id':roster_sid,'quote':roster_line}],position_check)
        def appointment_check(text,claim):
            if identity['outcome']=='unsupported': raise ValueError('Executive identity is unsupported')
            scope=re.sub(r'(?:\s+and|;)\s+Director$','',raw['position'],flags=re.I)
            # Director appointment can differ from CEO appointment: never assign
            # the CEO date to both. Preserve submitted title and record date scope.
            clause=re.search(r'(?:was appointed|has served as|became|has been)\b.*?(?=\.\s+[A-Z]|$)',text,re.I)
            if not clause or key(scope) not in key(clause[0]):
                # Proxy wording ("was named …", "joined … as …"); tried only after the
                # original clause fails, so a previously supported claim is unaffected.
                clause=re.search(r'(?:was named|joined)\b.*?(?=\.\s+[A-Z]|$)',text,re.I)
            if not clause or key(scope) not in key(clause[0]):
                from .claim_support import appointment_clause
                resolved = appointment_clause(text, scope)
                if not resolved:
                    raise ValueError('Current title is not supported by its appointment clause')
                clause = [resolved]
            if not raw['appointment_date']: raise ValueError('Current appointment date is unavailable')
            if not date_supported(raw['appointment_date'],clause[0]): raise ValueError('Appointment date/role is not supported')
            disclosed=re.search(r'\b(?:since|effective|in)\s+('+DATE_TEXT+r')',clause[0],re.I)
            if disclosed and natural_date(disclosed[1])!=raw['appointment_date']:
                raise ValueError('Appointment date changes disclosed value or precision')
            if window: recency(raw['appointment_date'],window)
            claim['appointment_scope']=scope
        appointment=validator.admit(prefix+':appointment','appointment',name,
            raw['position']+'; '+raw['appointment_date'],
            [{'source_id':raw['source_id'],'quote':raw['quote']}]+raw.get('supporting_citations',[]),appointment_check)
        if (appointment['outcome']=='unsupported' and appointment['citation_results'] and any(
                c['outcome']=='accepted' and key(raw['position']) in key(c['original_source_text'])
                for c in appointment['citation_results'])):
            context = validator.biography_fragments(name)
            if context:
                original = dict(appointment)
                repaired = validator.admit(prefix+':appointment','appointment',name,
                    raw['position']+'; '+raw['appointment_date'], context, appointment_check)
                validator.claims.pop()
                appointment.update(repaired, original_outcome=original['outcome'],
                                   original_reason=original['reason'], context_recovery='same_executive_biography')
        if appointment['outcome']=='unsupported' and any(c['outcome']=='accepted' for c in appointment['citation_results']):
            from .claim_support import scoped_appointment
            surviving_quotes=[c for c in appointment['citation_results'] if c['outcome']=='accepted']
            scope=scoped_appointment(' '.join(c['original_source_text'] for c in surviving_quotes),
                                     raw['position'], raw['appointment_date'])
            if scope:
                appointment.update(original_statement=appointment['statement'], original_outcome='unsupported',
                    original_reason=appointment['reason'], outcome='qualified', citations=surviving_quotes,
                    statement=scope+'; '+raw['appointment_date'], appointment_scope=scope,
                    partial_appointment_scope=True,
                    reason='Disclosed date retained for the named office only; other concurrent titles are undated')
        admitted_roles=[]
        for ri,role in enumerate(raw['prior_internal_roles'],1):
            def role_check(text,claim,role=role):
                if identity['outcome']=='unsupported': raise ValueError('Executive identity is unsupported')
                if key(role['position']) not in key(text): raise ValueError('Prior role title differs from quotation')
                from .claim_support import date_assertions
                retained, dropped = date_assertions(role, text)
                claim['retained_dates'] = {k: retained[k] for k in ('start_date', 'end_date')}
                claim['withheld_assertions'] = dropped
                claim['original_statement'] = claim['statement']
                hi = date_interval(retained['end_date'])
                if window and hi and hi[0]>date.fromisoformat(window['end']):
                    retained['end_date']=''
                    claim['retained_dates']['end_date']=''
                    claim['withheld_assertions'].append('end_date')
                claim['statement'] = role['position'] + (('; ' + retained['start_date']) if retained['start_date'] else '') + ((' to ' + retained['end_date']) if retained['end_date'] else '')
                # Employer checks receive only canonical biography context and
                # previously admitted roles, never unvalidated sibling assertions.
                biography=validator.biography(name)
                # Employer attribution can use the role's uniquely disclosed
                # date range even when the model supplied the wrong date. Do
                # not publish that rejected model value in retained_dates.
                attribution_role = dict(retained)
                disclosed_pairs = set(prior_role_date_pairs(normalized_m3(role['position']), text))
                if len(disclosed_pairs)==1:
                    attribution_role['start_date'], attribution_role['end_date'] = next(iter(disclosed_pairs))
                try:
                    internal_employer({**attribution_role,'position':normalized_m3(role['position']),'quote':text},
                        {'quote':biography,'prior_internal_roles':admitted_roles},sources.company)
                except ValueError as exc:
                    if 'ambiguous' not in str(exc): raise
                    from .employers import company_link
                    first=re.split(r'(?<![A-Z])(?<!Mr)(?<!Dr)(?<!Ms)\.\s+(?=[A-Z])',biography,maxsplit=1)[0]
                    boundary=re.search(r'(?:Prior to|Before) joining',biography,re.I)
                    location=biography.find(text)
                    entities=re.findall(r'([A-Z][a-z]+ Group) of the Company',biography)
                    internal_entity=any(key(entity) in key(role['position']) for entity in entities)
                    explicit_scope=(company_link(first,sources.company) and boundary and
                                    location>=0 and location<boundary.start())
                    if not (internal_entity or explicit_scope): raise
                    claim['employer_basis']='Explicit same-biography company/entity scope; not inferred from tenure'
                claim['context_evidence_ids']=[sid for sid in sources.section_ids
                    if (validator.starts[sid]<validator.biographies[key(name)][1]
                        and validator.starts[sid]+len(sources.pages[sid])>validator.biographies[key(name)][0])]
            claim=validator.admit(prefix+f':role:{ri}','prior_internal_role',name,
                role['position']+'; '+role['start_date']+' to '+role['end_date'],
                [{'source_id':role['source_id'],'quote':role['quote']}]+role.get('supporting_citations',[]),role_check)
            if claim['outcome']=='unsupported' and any(c['outcome']=='accepted' for c in claim['citation_results']):
                # Context is supplied to attribution checks, not substituted for
                # an invalid declared quotation or another executive's evidence.
                context = validator.biography_fragments(name)
                if context and 'attribution' in claim['reason']:
                    original = dict(claim)
                    repaired = validator.admit(prefix+f':role:{ri}','prior_internal_role',name,
                        role['position'], context, role_check)
                    validator.claims.pop()
                    claim.update(repaired, original_outcome=original['outcome'], original_reason=original['reason'])
            if claim['outcome']!='unsupported':
                dates=claim['retained_dates']
                start,end=date_interval(dates['start_date']),date_interval(dates['end_date'])
                if claim.get('withheld_assertions'):
                    claim.update(outcome='qualified',reason='Role and employer retained; unsupported date assertions withheld')
                admitted_roles.append({'position':role['position'],'start_date':dates['start_date'],
                    'end_date':dates['end_date'],'start_precision':start[2] if start else 'unavailable',
                    'end_precision':end[2] if end else 'unavailable',
                    'source_id':role['source_id'],'quote':role['quote'],
                    'validated_citations':claim['citations']})
        # A concurrently held explicitly attributed company office can validate
        # another role with the same disclosed start date. Recheck only employer
        # ambiguity after independent sibling evidence has itself been admitted.
        for ri,role in enumerate(raw['prior_internal_roles'],1):
            cid=prefix+f':role:{ri}'
            old=next(c for c in validator.claims if c['claim_id']==cid)
            if (old['outcome']=='unsupported' and 'employer attribution is ambiguous' in old['reason']
                    and role['start_date'] and role['end_date']):
                try:
                    text=normalized_m3(''.join(c['original_source_text'] for c in old['citation_results'] if c['outcome']=='accepted'))
                    internal_employer({**role,'position':normalized_m3(role['position']),'quote':text},
                        {'quote':validator.biography(name),'prior_internal_roles':admitted_roles},sources.company)
                except ValueError:
                    from .employers import company_link
                    concurrent=any(other['start_date']==role['start_date'] and
                        re.search(r'\balso served\b',normalized_m3(other['quote']),re.I) and
                        company_link(other['quote'],sources.company) for other in admitted_roles)
                    if not concurrent:continue
                old.update(outcome='accepted',reason='Supported role and dates; concurrently held company office establishes employer scope',
                           citations=[c for c in old['citation_results'] if c['outcome']=='accepted'])
                start,end=date_interval(role['start_date']),date_interval(role['end_date'])
                admitted_roles.append({'position':role['position'],'start_date':role['start_date'],'end_date':role['end_date'],
                    'start_precision':start[2],'end_precision':end[2],
                    'source_id':role['source_id'],'quote':role['quote'],'validated_citations':old['citations']})
        external=None
        if raw['external_recruitment_quote'] or raw['external_source_id']:
            def external_check(text,claim):
                if not re.search(r'(?:joined|recruited|hired).{0,120}\bfrom\b',text,re.I):
                    raise ValueError('External recruitment needs an affirmative source statement')
            external=validator.admit(prefix+':external','external_recruitment',name,
                raw['external_recruitment_quote'],[{'source_id':raw['external_source_id'],
                    'quote':raw['external_recruitment_quote']}],external_check)
        if identity['outcome']!='unsupported':
            interval=date_interval(raw['appointment_date']) if appointment['outcome']!='unsupported' and not appointment.get('partial_appointment_scope') else None
            anchor=date.fromisoformat(window['end']) if window else None
            profile={'name':name,'position':raw['position'] if position['outcome']!='unsupported' else expected[key(name)]['position'],
                'roster_position':expected[key(name)]['position'],
                'appointment_date':raw['appointment_date'] if interval else '',
                'appointment_precision':interval[2] if interval else 'unavailable',
                'recency':recency(raw['appointment_date'],window) if interval and window else 'unavailable',
                'prior_internal_roles':admitted_roles,
                'succession':'internal' if admitted_roles else 'confirmed_external' if external and external['outcome']!='unsupported' else 'unavailable',
                'citations':identity['citations']+appointment['citations']+
                    [c for role in admitted_roles for c in role['validated_citations']],
                'semantic_support_check':'passed_bounded_rules',
                'tenure':{'as_of':window['end'] if window else None,
                    'minimum_days':max(0,(anchor-interval[1]).days) if anchor and interval else None,
                    'maximum_days':(anchor-interval[0]).days if anchor and interval else None,
                    'basis':'Calculated from accepted appointment claim at disclosed precision'}}
            profiles.append(profile);profile_map[key(name)]=profile
    facts=[]
    for fact in payload['facts']:
        def fact_check(text,claim,fact=fact):
            if fact['executive'] and key(fact['executive']) not in expected:
                raise ValueError('Fact executive identity is unsupported')
            if not fact['statement'].strip() or locate(text,fact['statement']) is None:
                raise ValueError('Fact statement changes or exceeds its surviving quotations')
        claim=validator.admit(fact['fact_id'],'fact',fact['executive'],fact['statement'],fact['citations'],fact_check)
        if claim['outcome']!='unsupported':
            facts.append({**fact,'citations':claim['citations']})

    # Only exact, correctly attributed quotations are eligible for bounded
    # semantic recovery. Invalid citations never get a second path to admission.
    candidates = [c for c in validator.claims if c['kind']=='fact' and c['outcome']=='unsupported'
                  and c['reason']=='Fact statement changes or exceeds its surviving quotations'
                  and any(q['outcome']=='accepted' for q in c['citation_results'])]
    if candidates and hasattr(reviewer, 'review_claims'):
        inputs = [{'claim_id':c['claim_id'], 'executive':c['executive'], 'statement':c['statement'],
                   'quotations':[{'source_id':q['source_id'], 'quote':q['original_source_text']}
                                 for q in c['citation_results'] if q['outcome']=='accepted']}
                  for c in candidates]
        try:
            decisions = reviewer.review_claims(inputs, sources)
            by_id = {d['claim_id']:d for d in decisions}
            if len(by_id)!=len(decisions) or set(by_id)!={c['claim_id'] for c in candidates}:
                raise ValueError('Missing or duplicate fact recovery decision')
        except (ValueError, KeyError, RuntimeError, AssertionError):
            by_id = {}
        for claim in candidates:
            decision = by_id.get(claim['claim_id'])
            if decision is None:
                continue
            claim['entailment_review'] = decision
            if decision['outcome'] not in {'supported','partially_supported'}:
                continue
            try:
                quotes = validator.citations(decision['supporting_citations'], claim['executive'])
                quotes = [q for q in quotes if q['outcome']=='accepted']
                # Recovery may narrow the original evidence; cannot introduce
                # an uncited passage or enlarge the evidence boundary.
                original_ids={q['source_id'] for q in claim['citation_results'] if q['outcome']=='accepted'}
                originals=[q for q in claim['citation_results'] if q['outcome']=='accepted']
                if (not quotes or not {q['source_id'] for q in quotes} <= original_ids
                        or any(not any(q['source_id']==old['source_id'] and
                            locate(old['original_source_text'], q['original_source_text']) is not None
                            for old in originals) for q in quotes)):
                    raise ValueError('Recovery changed the declared evidence boundary')
                from .claim_support import retention_guard
                retention_guard(decision['retained_statement'], quotes, claim['executive'], sources.expected_roster)
            except (ValueError, KeyError):
                claim['recovery_rejected'] = 'Retained assertion failed canonical evidence/identity/number checks'
                continue
            original = claim['statement']
            claim.update(original_statement=original, original_outcome='unsupported', original_reason=claim['reason'],
                         statement=decision['retained_statement'], outcome='qualified', citations=quotes,
                         reason='Bounded entailment review retained supported assertions: '+decision['reason'])
            facts.append({'fact_id':claim['claim_id'], 'executive':claim['executive'],
                          'statement':claim['statement'], 'citations':quotes})

    ids=[c['claim_id'] for c in validator.claims]
    if len(ids)!=len(set(ids)):raise ValueError('Fact identity collides with a reserved evidence claim identity')
    accepted={c['claim_id']:c for c in validator.claims if c['outcome']!='unsupported'}
    candidates=[]
    for judgment in payload['judgments']:
        candidates.append({**judgment,'remaining_fact_ids':[f for f in judgment['supporting_fact_ids'] if f in accepted],
                           'rejected_fact_ids':[f for f in judgment['supporting_fact_ids'] if f not in accepted]})
    unavailable_review={
        'mode':'not_attempted','decisions':[],
        'overall':{'signal':'insufficient_evidence','text':'Validator 7 qualitative review has not been performed.',
                   'judgment_ids':[],'limitations':['Qualitative reasoning remains unreviewed.']}}
    try:
        review=reviewer.review(payload,validator.claims,sources) if reviewer is not None else unavailable_review
    except (ValueError,KeyError,RuntimeError) as exc:
        review={**unavailable_review,'mode':'failed','error':str(exc)}
    decisions={d['judgment_id']:d for d in review.get('decisions',[])}
    observations=[];judgment_results=[]
    directions={'credit_positive':'positive','credit_negative':'negative','neutral':'neutral','insufficient_evidence':'unavailable'}
    for judgment in candidates:
        decision=decisions.get(judgment['judgment_id'])
        outcome=decision['outcome'] if decision else 'unsupported'
        reason=decision['reason'] if decision else 'Validator 7 has not reviewed this judgment'
        refs=decision['supporting_claim_ids'] if decision else []
        if not set(refs)<=accepted.keys() or not refs:
            outcome='unsupported';reason='No sufficient accepted claim basis supplied by Validator 7'
        from .claim_support import judgment_scope
        effective_scope, attribution_ok = judgment_scope(judgment, [accepted[r]['executive'] for r in refs if r in accepted])
        if not attribution_ok:
            outcome='unsupported';reason='Reviewer attributed another executive evidence to this individual'
        if judgment['executive'] and key(judgment['executive']) not in profile_map:
            outcome='unsupported';reason='Individual judgment lacks an admitted executive identity'
        if decision and outcome=='accepted' and (judgment['rejected_fact_ids'] or decision['reviewed_text']!=judgment['explanation']):
            outcome='qualified';reason+='; original basis/text changed and is explicitly qualified'
        if re.search(r'\btenure\b.{0,45}\b(?:proves?|establishes?|demonstrates?)\b.{0,25}\bcompeten',decision['reviewed_text'] if decision else judgment['explanation'],re.I):
            outcome='unsupported';reason='Tenure alone cannot establish competence'
        # The specialist's own surviving facts are its basis; without one, or without
        # an admitted executive identity, there is nothing to cite and it stays withheld.
        own=[r for r in judgment['remaining_fact_ids'] if r in accepted]
        advisory=(not enforce and outcome!='accepted' and bool(own)
                  and (not judgment['executive'] or key(judgment['executive']) in profile_map))
        if advisory:
            refs=own
            reason=f'Validators off: Validator 7 outcome {outcome} ({reason}) not applied; the specialist\'s judgment stands'
            outcome='qualified'
        result={'judgment_id':judgment['judgment_id'],'outcome':outcome,'reason':reason,
                'original_text':judgment['explanation'],'original_fact_ids':judgment['supporting_fact_ids'],
                'removed_fact_ids':judgment['rejected_fact_ids'],'supporting_claim_ids':refs,
                'reviewed_text':decision['reviewed_text'] if decision else None,
                'original_executive':judgment['executive'], 'effective_scope':effective_scope}
        judgment_results.append(result)
        if outcome!='unsupported':
            observations.append({'observation_id':judgment['judgment_id'],'executive':(judgment['executive'] or None) if effective_scope=='individual' else None,
                'rule':('unenforced_model_judgment' if advisory
                    else 'explicit_review_correction' if any(
                    change['judgment_id']==judgment['judgment_id']
                    for change in review.get('explicit_corrections',{}).get('changes',[]))
                    else 'validator_7_review'),'direction':directions[judgment['signal']],
                'signal':judgment['signal'],'category':judgment['category'],
                'text':judgment['explanation'] if advisory else decision['reviewed_text'],'supporting_fact_ids':refs,
                'uncertainties':judgment['uncertainties']+(decision['limitations'] if decision else []),
                'review_outcome':outcome,'review_reason':reason,
                'citations':[c for ref in refs for c in accepted[ref]['citations']]})
    surviving={o['observation_id'] for o in observations}
    overall=review['overall']
    overall_valid=bool(overall['judgment_ids']) and set(overall['judgment_ids'])<=surviving
    summary_recovery = None
    if not overall_valid and observations:
        original_overall = dict(overall)
        try:
            if not hasattr(reviewer, 'summarize_surviving'):
                raise ValueError('No bounded summary reviewer available')
            corrected = reviewer.summarize_surviving(observations)
            if not corrected['text'].strip() or not corrected['judgment_ids'] or not set(corrected['judgment_ids']) <= surviving:
                raise ValueError('Recovered overall references an unavailable judgment')
            # Summary may restate only supplied values, not add numerical claims.
            from .claim_support import retention_guard
            retention_guard(corrected['text'], [{'original_source_text':o['text']} for o in observations], '', [])
            overall = corrected
            overall_valid = True
            summary_recovery = {'original_overall':original_overall, 'method':'bounded_surviving_judgments', 'corrected_overall':corrected}
        except (ValueError, KeyError, RuntimeError, AssertionError):
            # A model-independent fallback consists only of surviving reviewed
            # wording, with no new synthesis or reinstatement of rejected ideas.
            directions_left={o['signal'] for o in observations}
            signal = ('mixed' if {'credit_positive','credit_negative'} <= directions_left else
                      next(iter(directions_left)) if len(directions_left)==1 else 'neutral')
            overall={'signal':signal,'text':' '.join(o['text'] for o in observations),
                     'judgment_ids':[o['observation_id'] for o in observations],
                     'limitations':['Overall limited to surviving reviewed findings.']}
            overall_valid=True
            summary_recovery={'original_overall':original_overall,'method':'surviving_reviewed_text_only','corrected_overall':overall}
    limitations=list(sources.limitations)+payload['overall_assessment']['uncertainties']+payload['overall_assessment']['missing_information']+overall['limitations']+review.get('scope_limitations',[])
    if validator.proxy:limitations.append('The proxy statement states no as-of date for its executive officer table; recency and tenure were not calculated.')
    failed=[c for c in validator.claims if c['outcome']=='unsupported']
    if failed:limitations.append(f'{len(failed)} individual evidence claims are unsupported; other supported claims remain usable.')
    if any(j['outcome']!='accepted' for j in judgment_results):limitations.append('Qualified or withheld judgments are identified individually in the review record.')
    if review.get('mode')=='offline_fixture':limitations.append('Validator 7 used a saved/offline reviewer response; this execution does not verify live reviewer model performance.')
    # Evidence completeness is separate from qualitative scope: no seven-person
    # credit-judgment quota. The review reports disclosed/principal/team coverage.
    missing=[r['name'] for k,r in expected.items() if k not in profile_map]
    # Rejected evidence claims and qualified judgments are excluded individually
    # (recorded above); only lost coverage or an unsupported judgment is partial.
    complete=not missing and overall_valid and all(j['outcome']!='unsupported' for j in judgment_results) and sources.coverage_verifiable
    result={'schema_version':'m3-management-assessment-3.0','artifact_type':'senior_management_assessment',
        'company':sources.company,'filing_period':sources.filing_period,
        'source':{'path':sources.source_path,'sha256':sources.sha256,'section_ids':sources.section_ids,'physical_pages':sources.physical_pages},
        'roster_date':payload['roster_date'] if window else None,'roster_citation':roster['citations'][0] if roster and roster['citations'] else None,
        'review_window':window,'profiles':profiles,'observations':observations,'facts':facts,
        'model_assessment':payload['overall_assessment'],
        'validation':{'claim_results':validator.claims,'judgment_results':judgment_results,
            'rejected_facts':[{'fact_id':c['claim_id'],'detail':c['reason']} for c in failed if c['kind']=='fact'],
            'rejected_judgments':[{'judgment_id':j['judgment_id'],'detail':j['reason']} for j in judgment_results if j['outcome']=='unsupported'],
            'overall_references_valid':overall_valid,'validator_7':review.get('original_review',review),
            'explicit_review_corrections':review.get('explicit_corrections'),
            'overall_recovery':summary_recovery},
        'coverage':{'expected':len(expected) if sources.coverage_verifiable else None,'admitted':len(profiles),'missing':missing,'verifiable':sources.coverage_verifiable},
        'rejected_profiles':[], 'limitations':limitations,'completion_status':'complete' if complete else 'partial',
        'overall_assessment':{'outcome':directions.get(overall['signal'],overall['signal']) if overall_valid else 'unavailable',
            'information_gaps':bool(limitations),'policy':overall['text'] if overall_valid else 'No overall assessment with valid surviving judgment references.',
            'information_direction':'unavailable' if limitations else 'neutral'}}
    return compact_citations(result)
