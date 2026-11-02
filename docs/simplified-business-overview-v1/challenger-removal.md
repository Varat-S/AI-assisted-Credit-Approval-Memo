# Business challenger removed from new browser runs

The browser workflow now uses `bo-source-selection-output-1.1.0` and policy `bo-source-selection-1.1.0`. Module 1 specialists and Agent 6 still run with their existing validation; the orchestrator still selects and orders exact source findings. No Business Challenger call or challenge-triggered remediation is scheduled. Module 3 reviewer/validators and Financial Overview checks are unchanged.

## Execution and governance

- The Business Challenger is excluded from the active execution roster and job stages. The work plan counts one fewer model call, and successful jobs reach their actual planned total.
- New typed conclusions record `challenge_status: not_performed`; they are not labelled clean or falsely independently reviewed. Human review remains required.
- The frozen audit records `disabled_by_workflow`, the versioned policy, exact conclusion ID and editorial-selection hash. The handoff and persisted run configuration explicitly bind the disabled-challenge setting.
- The deterministic assembler admits this exception only for the new contract and only with its exact frozen policy/conclusion/selection bindings. The memo keeps Competitive Positioning available when source selection passes. It visibly says independent challenge was not performed.
- Selection integrity, source provenance, schema checks, specialist validation, review rules, exact-run isolation and hash checks remain enforced. Invalid selections still receive at most the existing one repair and otherwise remain unavailable.
- The existing four-section page, full debt tables, print layout and expandable evidence design are unchanged. Audit & Review explains that independent challenge is intentionally disabled.

## Historical compatibility

The previous source-selection 1.0.0 and editorial-writing contracts retain their original challenge requirements in strict readers. All three actual saved HCA runs (`ar_e58358f9a55f4a72`, `ar_919c5f5c8483497b`, `ar_811b307105db4192`) were read with the strict reader, passed schema/content-hash checks and matched their existing exported JSON exactly. No historical analysis was rewritten or backfilled.

## Files

`app/prompts/source_selection.py`, `app/services/agents/registry.py`, `app/services/bo/runner.py`, `app/schemas/agentic.py`, `app/services/bo/reporting.py`, `app/services/bo/four_section.py`, `app/services/bo/workbench.py`, `app/services/bo_fo.py`: versioned activation, execution removal, honest persisted status, strict compatibility and assembly.

`app/api/templates/analysis_setup.html.j2`, `app/api/templates/analysis_audit.html.j2`: scope/mode descriptions and explicit disabled-challenge notice. Existing memo templates and styles were retained.

`tests/business_overview_browser_helpers.py`, `tests/integration/test_business_overview_browser_e2e.py`: fixture has no challenger answer; acceptance asserts zero calls, no challenge stage, complete work progress, viewable source-copy memo, explicit governance status, unchanged historical isolation and rejection of a tampered persisted challenge policy.

## Verification

Results and restart confirmation are recorded below after checks complete. No paid inference or SEC acquisition is part of verification. No dependencies, commits, pushes, merges or deployment were performed.

Verification completed:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/integration/test_business_overview_browser_e2e.py tests/unit/test_bo_source_selection.py tests/unit/test_bo_competitive_positioning.py tests/integration/test_bo_competitive_positioning.py tests/integration/test_bo_four_section.py tests/integration/test_bo_four_section_independent.py tests/integration/test_bo_four_section_renderer.py tests/integration/test_bo_fo_combined.py tests/integration/test_bo_downstream_contract.py tests/integration/test_rms_runner.py tests/integration/test_analysis_review_workspace.py tests/integration/test_analysis_execution.py tests/integration/test_analysis_worker_health.py
```

**259 passed, 1 skipped in 119.81s.** The skip is the pre-existing absent optional PDF backend; the existing Starlette/httpx deprecation warning remains. The initial new tampering test expected the inner error text, but the strict reader wraps it as `Frozen root identity is malformed`; the assertion was corrected to the existing public error without changing the reader's rejection behavior.

After final completeness-warning/status wording, the directly affected browser suite was rerun:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/integration/test_business_overview_browser_e2e.py
```

**15 passed in 16.29s** (a subset of the broad run, not 15 additional unique cases). `git diff --check` passes.

The server was restarted on `127.0.0.1:8000` after confirming there were no active live jobs. The actual New Analysis page was opened and verified with both HCA filings available and the independent-challenge wording removed from the workflow descriptions. [Setup screenshot](challenger-free-setup.png). The tab is left open for the user. No live analysis was launched.
