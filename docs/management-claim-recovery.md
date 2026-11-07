# Management evidence recovery (backend only)

No templates, styles, labels, sections or controls are changed. The existing Management
projection consumes the same artifact contract, with an audited corrected overall
assessment when one was needed. Historical artifacts and source documents remain immutable.

## Claim-level retention

The management specialist receives a derived executive-biography index made of exact
canonical fragments, each with its original evidence ID. It cannot combine fragments
under a fabricated ID. Current-role appointment checks support `serves as` followed by
`has served in this role since`, within the same executive biography. Context recovery
requires an accurate, role-bearing declared quotation; a generic risk sentence cannot
borrow an appointment from elsewhere in the filing.

Prior roles retain independently supported title/employer information even when one or
both dates are unavailable or wrong. Only explicitly bound dates are retained; no end
date is inferred from a later appointment. Withheld fields and the original statement
are recorded separately. Employer resolution understands explicit `our` and `joined us`
inside a canonical executive biography, while explicit outside employers still block
an internal-role claim. Geographic territory and subsequent private practice are not
misread as the employer. Existing earlier-roster and director/CEO distinctions remain.

Director headings with credentials delimit biographies even when committee lines
intervene. An exact quotation spanning adjacent canonical chunks is represented by
its actual source fragments and offsets, within one executive biography. A date for
one named office may survive as a narrower claim without dating every concurrent
title in the profile.

## Bounded entailment and summary review

An exact quote is still mandatory, but a factual paraphrase no longer has to appear
verbatim as a whole statement. Facts with accurate, correctly attributed quotations
that fail the literal statement check can receive one batched `m3_fact_entailment`
review. The reviewer checks individual assertions and may retain a supported subset.
Its quote references must remain within the original admitted quotations. Identity,
quote occurrence and numeric checks run again. Original statements, rejection reasons,
review decisions, retained wording, prompt versions, raw responses and usage remain
available in the existing audit records. No permissive token-overlap threshold is used.
Semantic entailment remains model-reviewed, not mathematically proven.

Judgments now declare individual, team or company scope. Historical joint judgments
may be recognized as team-scoped only when every referenced executive is explicitly
named in the original explanation. Cross-executive evidence is still prohibited for
an individual judgment. The effective scope is recorded; original extraction is kept.

After final judgment admission, an overall summary referencing withheld judgments is
rebuilt from the surviving reviewed text only, using the separately versioned
`m3_surviving_summary` prompt. Its references and numerical values are checked. If that
bounded call fails, the fallback contains only the surviving reviewed statements,
with their original signals and qualifications; it invents no replacement analysis.
No survivors means no overall assessment. Optional model recovery never approves an
invalid source quotation and is not automatically retried.

## Verification

`tests/m3_rebuild/test_claim_recovery.py` covers undated roles, partial date withholding,
pronoun appointment clauses, faithful paraphrases, fabricated quotes/numbers, joint
scope boundaries, surviving-summary recovery and normal model-run/audit persistence.
It also covers director headings, geographic employer false positives, partially dated
concurrent titles and exact cross-chunk quotations.
The existing M3 suite covers HCA, fictional independent-company layouts, proxy/PDF
splits, false identities, wrong dates, wrong employers, negations and fabricated claims.

The original CYH run `run_b0f4b93ee41a` was replayed without model calls. The deterministic
fixes retain 26/41 claims (20 accepted, six qualified), versus 11/41 originally. All 30
original rejections were audited in `output/management_backend_fix/cyh-rejection-audit.json`;
that generated report and saved filings are not source code. The original files' hashes
were checked unchanged. The first fresh live extraction was also replayed through the final validators: all
36 claims survived as 26 accepted and ten qualified, with unsupported details removed
or narrowed. All four judgments survived. Historical findings are not silently replaced.

The complete targeted regression suite passed: 188 tests across M3, management
projection, Business Model presentation and Industry presentation.

Final live CYH verification: job `fd05423f46c34441be8412a23d8bde67`, BO run
`ar_d872a6ff122d41ec`, source run `run_7c94104d2217`. All 36 extracted claims
survived (18 accepted, 18 qualified), both reviewed judgments survived, and an
overall assessment rendered in the existing Management section. The report endpoint
returned HTTP 200 and the section reported complete. One unrelated pricing-power
specialist timed out in the combined run; Management completed successfully.
