# Deterministic Revenue / Cost presentation

The specialist detail was present in the frozen audit but the source-copy projector retained only the headline in the conclusion, and the renderer used generic claim categories as headings. This change is a read-only presentation adapter; it does not ask an LLM to sort, rewrite, explain or qualify anything.

## Grouping

- Revenue Drivers: pricing/reimbursement (`m1_revenue_quality`), demand/payer mix (`m1_customer_stickiness`), customer retention (`m1_pricing_power`), competitive position/entry barriers (`m1_competitive_durability`).
- Cost Drivers: operating costs (`m1_operating_model`).
- Agent 6: use the primary components' recorded producer dimensions. Revenue-only or cost-only interactions remain in that group; mixed interactions appear once under Revenue & Cost Interactions. There is no semantic or keyword inference.
- Within each group, sort by the fixed specialist order and source finding ID, irrespective of the model's selection order or positive/negative placement. Both main headings are retained even if a category has no selected findings. A factual empty-state message replaces invented content.

## Source detail

For each already-selected finding, display its governed claim type (Fact, Calculated fact, Management statement, Inference or Assumption) and direction. Copy existing `credit_mechanism`, `interpretation.implication`, `interpretation.magnitude`, `interpretation.trend`, `interpretation.watch_trigger` and `transmission_mechanism` verbatim. Omit absent fields and exact duplicates. Every copied field has an internal pointer into the selected run's frozen audit. These explanations are specialist interpretations, not newly verified factual claims or new overall credit judgments.

The adapter requires one current, eligible source with matching analysis/producer identity, claim text/type, parameter references, evidence set and component lineage. Foreign, superseded, duplicated or mismatched records fail closed. Raw `model_stated` material, rejected findings and omitted component narratives are not republished. Quotations and detailed evidence remain collapsed. Existing source limitations stay visible; no additional uncertainty or analytical text is generated.

The existing four-section artifact, content hash, selection ledger and source audit are unchanged. The display enriches the selected findings using the same strictly verified frozen audit that already backs their evidence panels. JSON exports remain exact copies of the frozen artifact; full specialist records remain in the audit. Legacy non-source-copy writing contracts retain their prior renderer. No prompts, specialist logic, selection contract, governance or scoring changed.

## Verification

Actual run `ar_8ec1650cef6e4fef` displays three selected findings under Revenue Drivers, one under Cost Drivers and one mixed interaction. The highlighted labour-cost finding now shows its original credit explanation, interpretation, trend, watch trigger and transmission mechanism. The frozen memo hash remains `f0b0df506409fc994dc83b8ee85421c0e435a319ef77eac28d4495711affdaa4` before and after rendering.

- [Revenue screenshot](revenue-drivers.png)
- [Cost screenshot](cost-drivers.png)

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/unit/test_bo_competitive_presentation.py tests/integration/test_business_overview_browser_e2e.py tests/integration/test_bo_four_section_renderer.py tests/integration/test_bo_four_section_independent.py tests/integration/test_bo_four_section.py
```

98 passed in 48.72s. After making within-group ordering independent of selector order, reran the directly affected suites:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/unit/test_bo_competitive_presentation.py tests/integration/test_business_overview_browser_e2e.py
```

29 passed in 15.29s (a subset of the 98 cases). Only the existing Starlette/httpx deprecation warning remains. `git diff --check` passes. The actual browser page was visually inspected with the new headings, source explanations, Fact/Inference labels and collapsed evidence panels. The local server was restarted after confirming no active analyses. No live inference, acquisition, historical rewrites, commits or pushes were performed.

## Three-pointer layout refinement

Each selected finding now has exactly three visible content labels:

1. **Finding**: source headline, recorded magnitude and trend.
2. **Credit Implication**: source credit mechanism, interpretation and transmission mechanism.
3. **Watch Triggers**: the original `interpretation.watch_trigger`, preserving any existing metrics, comparisons, thresholds or qualitative events verbatim. No new metric or threshold is inferred. An absent trigger gets a factual empty-state message. A trigger is not suppressed even if identical wording appears in another source field.

The individual Magnitude, Trend, Specialist interpretation and transmission headings no longer compete in the memo. Their original text and field pointers remain intact. Classification/direction badges, source qualifications and expandable evidence remain available. Desktop uses a compact label/content layout; narrow screens stack labels over content.

Verification: 47 passed in 24.15s across `tests/unit/test_bo_competitive_presentation.py`, `tests/integration/test_business_overview_browser_e2e.py` and `tests/integration/test_bo_four_section_renderer.py`. The main browser acceptance test was rerun after adding an explicit assertion for exactly these three labels and passed in 2.22s. An initial template nesting error was caught by the print-template regression and corrected before completion. Only the existing Starlette/httpx deprecation warning remains; `git diff --check` passes.

The local server was restarted with no active analyses, and the actual saved HCA memo was visually inspected. [Three-pointer preview](three-pointers.png). No live inference, historical changes, commits or pushes were performed.
