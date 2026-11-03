# Competitive Positioning merge into UI Draft V2

Target parent: `b94f9776942c7a9b5b505040c85d3958a52fd66b` (`UI_Draft_V2`).
Source parent: `e468abf251d88713ac8384fd74e831a025f965e4` (`Competitive_Pos_Refinement`).

The merge keeps V2's Credit view, Financial Overview audit report, workbench review controls, portrait print layout and exclusion of raw evidence JSON from the memo PDF. Competitive Positioning retains deterministic Revenue Drivers / Cost Drivers grouping, verbatim specialist content, Finding / Credit Implication / Watch Triggers, and expandable evidence within each finding's separator. No agent, assembler, frozen-run or governance logic changes were introduced to reconcile the branches.

The finding badges now use V2's existing fact/inference/assumption semantic colour tokens and compact typography. Icons and positive/negative signs remain. Source branch history is preserved by a two-parent merge.

## Verification

Command (from repository root, using the existing sibling environment):

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q --tb=short tests/unit/test_bo_competitive_presentation.py tests/integration/test_business_overview_browser_e2e.py tests/integration/test_bo_four_section_renderer.py tests/integration/test_analysis_review_financial.py tests/integration/test_credit_page.py tests/integration/test_fo_runner_api.py tests/integration/test_analysis_workspace.py tests/integration/test_analysis_review_workspace.py
```

Result: **140 passed, 1 failed, 1 skipped**. The failure is `test_home_page_links_to_financial_overview`, which still expects a homepage `/fo` link although the existing homepage uses New Analysis and Credit Memos. Running that exact test against an untouched archive of target commit `b94f977` reproduces the failure. Neither the homepage nor this test was changed by the merge. The PDF backend test is skipped because no PDF backend is installed; actual PDF binary rendering was not verified. Four-section HTML/PDF-template checks passed.

Browser verification used the persisted offline-readable HCA job `e3d99019343a447abdc8703c10e945cf`, BO run `ar_888bced33fbd43b9`, and FO run `fo-7e2eaa1468fc46f1`. No new analysis or live model calls were made. The memo, expandable evidence, V2 Credit view and FO audit report rendered successfully. Saved screenshots:

- [Competitive Positioning](competitive-positioning.png)
- [Expanded evidence](evidence-expanded.png)
- [Credit view](credit-view.png)
- [Financial Overview audit](fo-audit.png)

`git diff --check` passed. No new dependencies were installed.
