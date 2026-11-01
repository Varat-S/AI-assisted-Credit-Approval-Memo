# Milestone 1: Credit Analysis Workspace and New Analysis Setup

Implemented locally on `Alan's-Branch`, based on `adbf6e6a62a1c20345fc7ccf4116ab2c450546db`.
This milestone is setup only. No new execution, persistent history, memo review or audit workflow is implemented.
No paid model calls, Git commits, pushes, merges or pull requests were made.

## What changed

| File | Purpose |
| --- | --- |
| `app/api/browser.py` | Read-only minimal homepage, without querying case history. Existing `/bo` remains available. |
| `app/api/analysis.py` | GET-only `/analysis/new` setup and `/credit-memos` placeholder. |
| `app/main.py` | Register the setup router alongside existing routers. |
| `app/services/analysis_setup.py` | Validate the configured source package and selections; construct the existing backend parameter map without submitting it. |
| `config/analysis_companies.json` | Small versioned registry, containing HCA Healthcare (HCA) and its FY2024 package only. |
| `app/api/templates/home.html.j2` | Credit Analysis Workspace title and exactly two primary navigation cards, with inline SVG icons. |
| `app/api/templates/analysis_nav.html.j2` | Consistent workspace navigation. |
| `app/api/templates/analysis_setup.html.j2` | Setup form, real evidence metadata, standard/exploratory controls, collapsed options and disabled Run Analysis button. |
| `app/api/templates/credit_memos.html.j2` | Clearly labelled history placeholder, with no invented runs. |
| `app/api/templates/workspace_style.html.j2` | Responsive neutral/navy/teal visual styling, native controls and visible keyboard focus. Reuses the existing base CSS. |
| `tests/integration/test_analysis_workspace.py` | 21 setup cases, including parameterized scope and safeguard combinations. |
| `tests/integration/test_browser_preview.py` | Update the old homepage assertion; retain the existing workbench and database immutability checks. |
| `tests/integration/test_bo_cli_workbench.py` | Update the old homepage assertion; retain existing BO, audit, review and export tests. |

No specialist, synthesizer or challenger prompts were changed. The worker, pipeline runner, validators,
financial calculations, reporting logic, database schema, migrations and approval rules are unchanged.

## Configuration and evidence

The sole company is HCA Healthcare (HCA), selected by default. Its registry entry points to:

```text
edgar_filings/HCA 10-K FY2024/package.json
```

`SourcePackage.load` and `shared_filing.load_bundle` perform the existing package/bundle loading and source-hash checks.
Setup confirms the company CIK, ticker, reporting period, annual-report identity, shared manifest and file hashes.
It requires the shared filing layout supported by the existing browser backend, including its schema.
Missing, tampered or mismatched evidence produces a visible error; there is no fallback to a different company or year.

The actual local package supplies these values (they are not hard-coded UI dates):

- Reporting period: year ended 31 December 2024.
- Filing date: 14 February 2025.
- Original evidence cutoff: 31 March 2025, 23:59:59 UTC.
- Source identifier: `0000950170-25-020134`.
- Primary report: `hca-20241231.htm`.
- Package contents: 20 files.

Default setup maps to the existing `/run/start` contract:

```json
{
  "folder": "HCA 10-K FY2024",
  "case_id": "",
  "sections": "both",
  "cutoff": "2025-03-31T23:59:59+00:00",
  "bo_validators": "on"
}
```

Business Overview Only maps to `sections="bo"`. Exploratory Mode maps to `bo_validators="off"`;
no Financial Overview safeguard parameter is added. Its separate setup policy is
`ineligible_for_final_approval`; Standard Mode preserves the existing review/approval requirements.
This is a setup contract, not a change to any existing approval endpoint.

Advanced cutoff overrides require a timezone and must include the selected annual report's availability.
The case reference uses the existing case-ID validator. Check setup uses a GET request, preserving the
selected values in the URL for refresh, bookmarks and browser back navigation.

Provider readiness reuses local configuration checks from the existing BO/FO service factories.
It does not generate text, contact Vertex, refresh credentials or verify live model availability.
The UI explicitly distinguishes settings being present from connectivity having been tested.

## Browser instructions

From Terminal:

```bash
cd "/Users/Daniel/Documents/ChatGPT/Daniel's AI in Finance 2/alan-branch-current"
uv run --locked --extra vertex uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>.

1. Confirm the title is Credit Analysis Workspace and the two cards are New Analysis and Credit Memos.
2. Open New Analysis. Setup is active; Execution and Review are inactive placeholders.
3. Confirm the hospital dropdown has only HCA Healthcare (HCA), already selected.
4. Confirm Business + Financial Overview and Standard Mode are selected.
5. Inspect the evidence panel. It should show the actual FY2024 package metadata above.
6. Select Business Overview Only and Exploratory Mode. The unvalidated/non-approval warning appears immediately.
7. Click Check setup. No execution starts. Refresh and confirm these selections remain selected.
8. Expand Advanced settings to inspect or validate an optional cutoff/reference. They are collapsed initially.
9. Confirm Run Analysis remains disabled in every mode.
10. Open Credit Memos. It must show a coming-next placeholder, without fabricated history or review results.

Existing advanced routes remain directly accessible, including `/run`, `/bo`, `/fo`, `/inspect`,
`/pipeline`, `/docs`, and the existing case workbench/memo URLs. The old `/run/start` remains a live
legacy endpoint; it is deliberately **not** connected to the new setup form in this milestone.

Screenshots were captured from the same UI code with the original local HCA files, without an analysis run:

- `../../UI_Milestone1_20261101/homepage.jpg` (workspace-level screenshot folder; see the final delivery links).
- `setup.jpg` (default setup).
- `setup-exploratory.jpg` (checked exploratory/BO-only selection).
- `setup-compact.jpg` (768px responsive layout).

## Tests and results

Final result: **92 passed, 0 failed**, in 65.75 seconds. One existing Starlette/httpx deprecation warning;
no dependency upgrades were introduced to silence it. `git diff --check` passed.

```bash
uv run --locked --extra dev python -m pytest -q \
  tests/integration/test_analysis_workspace.py \
  tests/integration/test_browser_preview.py \
  tests/integration/test_workbench_api.py \
  tests/integration/test_bo_cli_workbench.py \
  tests/integration/test_bo_fo_combined.py \
  tests/integration/test_m3_workflow.py \
  tests/unit/test_bo_model_choice.py \
  tests/unit/test_llm_usage_cost.py
```

Validation used a byte-matched temporary source mirror and the already installed Python 3.11 test runtime,
to avoid slow Documents-directory reads. No `.env` is read by the tests. New setup tests use tiny,
explicitly synthetic source-file fixtures and assert that no job or provider generation can be started;
they do not mock a completed analysis. Existing regression tests retain their offline fixtures.

The tests cover all requested homepage/default/selection/evidence/error/mapping/no-execution requirements,
and exercise legacy routes, workbench immutability, existing BO/FO execution integration and review/export behavior.
Browser checks confirmed the actual HCA metadata, selected controls, exploratory warning, refresh retention,
disabled Run Analysis, history placeholder, and no horizontal overflow at 768px. Screenshots were inspected.

## Limits and next-milestone readiness

- HCA FY2024 is the only configured company/package. Evidence is kept locally and is not invented or downloaded by Setup.
  A fresh clone without those existing evidence files correctly shows an error.
- There is no new launch endpoint, job store, progress screen, persisted history or Audit & Review implementation.
- The setup contract is ready to be connected to the existing `POST /run/start`, followed by
  `GET /run/jobs/{job_id}` and, where appropriate, `POST /run/jobs/{job_id}/stop` in Milestone 2.
  That existing service uses the full BO pipeline rather than the specialists-only entry point.
- The existing job manager is in memory. Durable history, restart/interruption handling and browser-independent
  monitoring remain Milestone 2 work; no such changes remain in this working diff.
- Existing advisory BO execution marks drafts for human review. That alone does not establish the requested
  final-approval exclusion: execution integration must carry the exploratory policy through persisted run metadata
  and enforce the exclusion at the appropriate approval boundary. Existing approval rules were not changed here.
- Provider credential/connectivity validation remains an execution-integration concern. No paid test was performed.
- Work stops after Milestone 1 for user review.
