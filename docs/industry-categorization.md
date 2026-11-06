# Industry findings: headwinds, tailwinds and company exposure

The `m2_industry` specialist's v3 prompt now requests company-specific classifications:
tailwind, headwind, mixed or uncertain. Structural company exposure is separately
classified as `company_exposure`; exposure alone is not an adverse industry trend.
The brief is in `app/prompts/industry.py`, composed with the existing shared BO rules.
Prompt registration creates a new version without modifying old runs.

The native hypothesis contract remains intact. Each finding has optional `industry`
metadata (kind, category, descriptive title, observed/structural/proposed/expected
state, and linked development IDs). The existing claim is the development or
exposure; interpretation.implication is the company effect, company_response is an
optional evidenced offset, and watch_trigger is the observable development to watch.
No continuous narrative or balanced quota of favourable/adverse findings is required.

Validator 6 keeps its quote, numeric, attribution and admissibility checks. Additional
metadata checks reject category/direction mismatches, exposure/development mismatches,
unknown links and unbound heading numbers. Company-response numbers go through the
same numeric grounding check as other interpretation fields. Invalid metadata is
withheld and recorded as a validation note; no inferred exposure classification is
substituted. Historical/offline outputs without metadata remain readable.

The governed hypothesis and module handoff preserve accepted industry metadata.
The four-section memo binding checks the same selected-run provenance as before.
`industry_view.py` groups findings without a model call or source mutation. Legacy
findings use their saved direction only, with neutral findings under Uncertain Factors;
no geographical exposure is inferred from keywords. New explicit exposures appear
separately and link only to visible development IDs.

The web and print templates show labeled development/exposure, company effect,
optional offset, and watch trigger. Null offsets/triggers are omitted. Each web card
has its own evidence panel; print keeps analytical text without interactive controls.

Tests: `tests/unit/test_industry_view.py` and
`tests/integration/test_industry_presentation.py`, plus existing validator and roster
regressions. These tests validate data flow and grounding rules, not model quality.
