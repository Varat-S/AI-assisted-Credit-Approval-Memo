# Milestone 5 — Offline end-to-end Business Overview integration

Completed 3 November 2026 (Singapore) on `UI_Draft_V1`, with HEAD unchanged at `34d61e7b3e547228d6766ec4a7e916395821a906`.

New Analysis now explicitly activates the existing simplified workflow. Actual offline browser submissions produced challenged, frozen four-section memos, displayed them in Review, and reopened identical artifacts through Credit Memos. Database/source preflight, exact-run rejection, partial Industry handling, cancellation, restart safety, review isolation and BO/FO/RMS compatibility were exercised.

**Known environment limit:** native binary PDF downloads still require the previously optional WeasyPrint/xhtml2pdf backend, which is absent here. Both actual native endpoints' integrity paths and print-template dispatch are covered; the browser demo confirmed the existing HTTP 501 on valid PDF requests. Actual landscape PDFs were generated and inspected using local Chrome over the same strict-read print HTML. This report does not claim an optional application backend was installed or tested.

No live Gemini/HCA analysis, SEC retrieval, external API calls, dependency installation, deployment, commits, pushes or merges were performed. All models used in acceptance were scripted, and live providers/SEC transport were explicitly blocked. The temporary localhost demo server was stopped after verification.

## Files changed and purpose

| File | Change |
|---|---|
| `app/api/analysis.py` | Database preflight before provider setup; explicit New Analysis contract activation; persisted workflow metadata and request fingerprint |
| `app/services/bo_fo.py` | Optional versioned contract passed to the existing BO runner; startup checks; saved artifact/snapshot references in summaries; selective-writer stage label and durable job configuration |
| `app/services/analysis_preflight.py` — new | Read/write-readiness probe and complete required table/column inspection, without creating/migrating the database or changing rows |
| `app/api/templates/analysis_setup.html.j2` | Replace the New Analysis scope description's obsolete cross-module-synthesis wording with Competitive Positioning; no styling changes |
| `tests/business_overview_browser_helpers.py` — new | Fictional local Inline-XBRL filing, corporate input and scripted specialist/independent-review responses |
| `tests/integration/test_business_overview_browser_e2e.py` — new | Eleven offline acceptance cases using actual submission, worker, source ingestion, governance, freezing and HTTP readers |
| `tests/integration/test_analysis_execution.py` | Give the existing mocked-worker fixture a real isolated initialized database so it satisfies the new preflight; existing assertions retained |
| This report and `milestone-5-verification/` — new | Execution trace, exact artifact exports, screenshots, proofs and PDF checks |

SHA-256 comparison of **657 pre-existing files** under `app`, `tests` and this documentation directory found only four previously existing files changed: `app/api/analysis.py`, `app/services/bo_fo.py`, `analysis_setup.html.j2` and the execution-test fixture. The other **653 files retain their previous bytes**. In particular, Milestones 2–4 prompts, specialist definitions, Agent 6, validators, orchestrator analytical logic, assembler/source-copy rules, strict reader, renderer/landscape correction and earlier reports/examples are unchanged. FO/RMS scoring, debt calculations, staging/merge implementation and review rules are unchanged.

## Exact activation and configuration path

1. `GET /analysis/new` retains the existing setup and scope/validation choices.
2. `POST /analysis/start` uses existing source-package validation and `bo_fo.plan()`, then calls `check_database()` before `execution_backends()`.
3. For BO-only or combined scope, the route supplies `business_orchestrator_contract=bo_fo.BROWSER_BO_CONTRACT` to `Jobs.start()`; FO-only scope supplies no BO contract.
4. Durable `Jobs` forwards the explicit argument to `run_bo_fo()`.
5. The worker creates the existing `BusinessOverviewRunner` with roster `v3`, debt specialist enabled, and the explicit selected contract.
6. Existing Milestone 2 routing selects the scoped writer/challenger and policy. Existing reporting assembles/freezes the Milestone 3 artifact and binds it to the handoff. Existing Milestone 4 routing reads that bound artifact for Review/export/history.

```text
bo_roster: v3
business_orchestrator_contract: bo-competitive-positioning-output-1.0.0
editorial_selection_policy: bo-editorial-selection-1.0.0
writer input: bo-competitive-positioning-input-1.0.0
memo schema: bo-four-section-memo-1.0.0
assembler: bo-four-section-assembler-1.0.0
```

The contract/policy are persisted in submission metadata, durable job `business_overview_workflow`, and the existing analysis run's `model_configuration`. The job summary includes the actual snapshot version and the exact frozen memo binding (stage, schema, stage SHA and analytical content hash). Workflow configuration also participates in the submission fingerprint, preventing silent reuse of a submission token for a different configuration.

`run_bo_fo()` defaults its new optional contract argument to `None`. The legacy CLI, direct runner defaults and older `/run/start` path do not silently opt into the new writer. Historical archives are not backfilled or regenerated. The new stage label is “Competitive Positioning writing & validation”; legacy executions retain their former label.

## Actual offline execution trace

[End-to-end trace](milestone-5-verification/end-to-end-trace.json) was exported from the last focused test's real durable job. Its source was a local fictional Northfield Inline-XBRL filing plus a corporate onboarding file, not the documentation sample JSON. The existing intake parser, source preparation, canonical evidence, routing, agent runtimes, validation, challenge, persistence and strict renderer all executed; none of those components were mocked.

Observed stage order:

```text
foundation
  management_analysis_and_validator7
primary_specialists (Agents 1–5, existing Industry/strategy specialists)
resilience (Agent 6 and existing governance)
debt_specialist_and_validation
reconciliation
orchestrator (scoped Competitive Positioning writing/validation)
challenger
memo_preparation (reporting, provenance freeze, assembler, handoff binding)
recorded_output (after database commit)
Review / Credit Memos / exact-run exports
```

Primary specialists may run concurrently; the test proves all five M1 primary calls precede Agent 6, which precedes the writer, which precedes the challenger. It verifies one writer and one challenge call, both management/Validator 7 calls, the scoped input schema and absence of `module_conclusions` from the writer packet. The `analyze` call in the backend method list is the separately keyed M4 debt specialist, not a new analytical agent. Final work progress is **15/15**.

```text
Test job: 250c775e95af45d9b19a8a8f0c22cc33
Analysis run: ar_b1e9fa0175e643f6
Case: NFH_BROWSER
Snapshot version: 1
Snapshot hash: 83a1fc0c86142884ddeea2073fe1ba33d25a3da9be0703481f6ffbf94dc1f7b1
Frozen memo stage: bo_four_section_memo:ar_b1e9fa0175e643f6
Stage SHA: a83283d3283661ca25fd8d7be2b41c5d0d204035a67dfd0a94a51c99fb6c905a
Memo content hash: 1346b2f0cd20c04bbd8b6414e3ce902b96c97f48aaa4eaa1b871a76fd3cd6174
```

The trace retains exact conclusion/orchestrator IDs, source snapshot identity, selected contract/policy, all observed events and the saved handoff's canonical references. The memo reassembled from `load_saved_inputs()` equals its persisted strict-reader artifact.

## Review, history and exact-run identity proofs

The real HTTP acceptance test follows `/analysis/{job}/review`, reads Credit Memos' link for that exact job, follows it back and compares the returned Review HTML. It also compares `/cases/{case}/bo/runs/{run}/memo.json` against `bo_artifact(..., 'four_section')`. All source-stage hashes and serialized payloads remain unchanged across these reads. Model generation is forbidden after execution, including management; restored `Jobs` instances retain the same run IDs without restarting anything.

The real browser separately submitted two analyses of the same company/case. These are independent of the pytest trace above:

| Browser case | Partial Industry | Populated governed Industry |
|---|---|---|
| Job ID | `efbb6642c2d4462caf26dd0d35a04f7e` | `d0d705e35a8f48e198b726c8d89fa8e0` |
| Analysis run ID | `ar_8762bbee4d474387` | `ar_93fab89e3e484608` |
| Case | `NFH_BROWSER_VISUAL` | `NFH_BROWSER_VISUAL` |
| Evidence snapshot | 1 | 2 |
| Memo completeness | incomplete | complete |
| Recorded conclusion outcome | human_review_required | accepted |
| Current human review | pending | pending |
| Memo content hash | `786c8911cd2808bbd0fb63d6d0b0efe94f1f7dd30394b3433e7772df820d0352` | `a6b107d64e2ecddebc958e371529adafe4dee4f147b76cade27300e45f7f6ffd` |

Both browser submissions used the actual form POST and durable worker. The browser clicked each completed job's Review link, navigated to Credit Memos, clicked the matching job entry and verified the exact saved run. After creating snapshot 2 it reopened snapshot 1 and confirmed its memo was unchanged. Recorded model-call counts and source/stage hashes did not change during Review/history/JSON/PDF-template access or native evidence interaction.

- [Partial proof](milestone-5-verification/partial-proof.json) and [canonical JSON](milestone-5-verification/partial-memo.v1.json)
- [Populated proof](milestone-5-verification/populated-proof.json) and [canonical JSON](milestone-5-verification/populated-memo.v1.json)
- [Browser identity/navigation checks](milestone-5-verification/browser-checks.json)

Adversarial tests replace the second run's handoff memo binding with the first run's valid binding and recompute the handoff digest. Review, JSON export and both PDF-export paths return **409**, despite the foreign binding's valid hash. No legacy fallback appears. A different-case HTML URL returns **404**. The first run remains readable. Existing independent assembler proofs in the regression suite cover root-chain tampering and detached persistence rejection as well.

## Partial Industry, omission and human review

The expected Industry-empty run retains four sections. Structure, complete debt, reviewed Management and selected Competitive Positioning are available; Industry contains no invented narrative and displays the existing placeholder. Memo completeness stays incomplete, finalized conclusion challenge status stays escalated and human review stays pending. The Industry specialist is not disabled globally: a separate scripted future-content case demonstrates faithful rendering when governed findings are available.

`M1S2-H001` is deliberately omitted from Competitive Positioning. Its narrative sentence is absent from the visible memo; its governed source record and explicit omission decision remain in Audit & Review. The handoff keeps all-module source findings and supported interaction/mitigant records; editorial omission does not delete downstream inputs.

There is no automatic approval. Exploratory acceptance is rejected under the existing rule. Blank reviewer/reason is rejected. An explicit signed acceptance of one selected BO run does not accept the other run and does not change the frozen memo's completeness or its initial review snapshot. Current review is overlaid from the existing records.

Important existing-rule distinction: missing Industry does not itself create an unresolved challenge record. The unchanged review service requires explicit acknowledgement when unresolved challenges are recorded; it can permit an explicit reviewer decision on an incomplete memo with a valid conclusion and no such challenge. The test checks that actual rule rather than inventing a new prohibition. Combined BO/FO approval still requires the selected pair's finalized snapshot; BO acceptance alone does not yield overall “Approved.”

## Database, source and execution reliability

New preflight opens only an existing file-based database in `mode=rw`, checks every required ORM table/column, then obtains/releases `BEGIN IMMEDIATE` with a five-second timeout. It writes no rows and performs no automatic initialization or migration. Failure produces a clear startup error before provider setup or a worker's model generation.

Source selection still uses existing package/bundle/company/period/path/hash checks. The worker rechecks the selected local bundle before either section starts, verifies the required BO schema file and confirms that the cutoff admits the primary report. Optional/missing specialist content still follows the existing partial-component behavior; preflight does not fabricate it.

Executed failure cases:

| Case | Observed result |
|---|---|
| Missing database | HTTP 400 before provider factory; no job/model calls |
| Missing required database column | HTTP 400 with migration/readiness diagnostic before provider factory |
| Missing required source file | HTTP 400 before provider factory/job |
| Source file hash mismatch | HTTP 400 before provider factory/job |
| Locked database | Bounded preflight failure; no provider calls/job |
| Source changes after initial preflight | Actual worker fails during revalidation; clear failed terminal job; no generation or accepted run |
| Stop during an in-flight scripted primary call | Cooperative cancellation after the call returns; stopped job; analytical run/handoff/four-section publication rolled back |
| Repeat the stopped submission token | Returns the same stopped job; no replay/model-call increase |
| Restore job manager / process-exit and storage faults | Existing real-thread, restart, durable-status, idempotency and write-failure regressions pass; no paid retries introduced |

Cancellation verification concerns analytical runs, handoffs and memo publication, not deletion of deterministic source-preparation diagnostics. Existing bounded analytical remediation is preserved; no new automatic retry or historical rerun was added.

## BO/FO/RMS and legacy compatibility

An actual combined worker run with the new BO contract executes FO in its existing separate staging database, merges it, removes the staging file and produces the existing RMS output. BO/FO/RMS all return completed execution statuses. The saved RMS source references match the exact BO and FO run IDs; the FO payload and recorded content hash remain unchanged when reviewed. BO-only acceptance does not approve the combined pair.

The minimal fictional filing intentionally lacks sufficient FO inputs for scoring. FO scores and RMS capacity therefore remain unavailable and RMS records its “No FO composite score” gate and required human review. This proves orchestration/persistence and honest missing-data compatibility, not a new fully scored financial analysis. Existing downstream, financial review, RMS, review/final-snapshot and JSON-export suites also pass.

Legacy defaults remain `business_orchestrator_contract=None` outside the explicit New Analysis activation. Old archives without a four-section binding continue through their existing reader/renderer, including portrait legacy PDF rules. Present corrupt new bindings fail closed. No historical source or report is modified on access.

## Browser and export inspection

Actual localhost pages were inspected for populated and partial cases at approximately 1440, 1024 and 390 px. Desktop retains structure left/debt right; mobile stacks structure above debt, retaining table scroll. Native evidence starts closed and expands/collapses without HTTP/model work. Existing layout tokens, typography, debt columns, simulation notices and qualifications remain unchanged.

- [New Analysis](milestone-5-verification/new-analysis.png)
- [Partial Review, 1440 px](milestone-5-verification/partial-review-1440.png), [1024 px](milestone-5-verification/partial-review-1024.png), [390 px](milestone-5-verification/partial-review-390.png), [mobile debt](milestone-5-verification/partial-review-mobile-debt.png)
- [Populated Review, 1440 px](milestone-5-verification/populated-review-1440.png), [1024 px](milestone-5-verification/populated-review-1024.png), [390 px](milestone-5-verification/populated-review-390.png)
- [Execution](milestone-5-verification/partial-execution.png), [Credit Memos history](milestone-5-verification/populated-history.png), [expanded evidence](milestone-5-verification/partial-evidence-expanded.png)
- [Partial landscape PDF](milestone-5-verification/partial-memo.pdf), [populated landscape PDF](milestone-5-verification/populated-memo.pdf), [PDF checks](milestone-5-verification/pdf-checks.json)

Chrome rendered the actual strict-selected-run print template. Both PDFs have the side-by-side diagram/debt summary on page 1, complete schedules from page 2, all 84 instrument-field values and all creditor-priority fields in the analytical body, and no horizontal text beyond the page boundary. The complete evidence appendices begin on page 7; total lengths are 64/66 pages because evidence is not truncated. First-page/table output was rasterized with Poppler and visually inspected. Canonical JSON exports equal the strict reader's saved memo.

Actual native application PDF requests returned the documented **501** because neither optional backend is installed; corrupt bindings returned **409 before backend selection**. Backend dispatch/content has existing capture tests, and actual browser print is verified. Native backend-specific PDF pagination and a successful native HTTP binary download remain unverified in this environment. No renderer/backend dependency change was made to conceal that limitation.

The demo used an isolated database and fictional source directory, injected only scripted upstream backends and blocked live providers/SEC. No product route or runtime offline switch was added for the demo. Saved HTML/screenshots are inspection artifacts; navigation requires a running app with the matching saved-job database. The temporary demo server has been stopped.

## Commands and results

Broad final integration regression command:

```sh
BO_M5_EVIDENCE=/private/tmp/kiro_m5_acceptance_evidence PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q --tb=short tests/integration/test_business_overview_browser_e2e.py tests/integration/test_analysis_execution.py tests/integration/test_analysis_worker_health.py tests/integration/test_execution_ui_refinement.py tests/integration/test_bo_fo_combined.py tests/integration/test_bo_four_section_renderer.py tests/integration/test_bo_four_section_independent.py tests/integration/test_bo_four_section.py tests/integration/test_analysis_review_workspace.py tests/integration/test_analysis_review_financial.py tests/integration/test_analysis_workspace.py tests/integration/test_bo_cli_workbench.py tests/integration/test_bo_competitive_positioning.py tests/unit/test_bo_competitive_positioning.py tests/integration/test_bo_downstream_contract.py tests/integration/test_rms_runner.py tests/integration/test_review_workflow.py tests/unit/test_human_review_workflow.py tests/unit/test_audit_immutability.py tests/integration/test_final_snapshot_immutability.py tests/integration/test_json_export_integrity.py
```

**363 passed, 1 skipped in 122.75s**, with the existing Starlette/httpx deprecation warning. The skip is the absent optional PDF backend.

After adding explicit corrupt-binding checks on both PDF routes, reran the directly affected new acceptance suite:

```sh
BO_M5_EVIDENCE=/private/tmp/kiro_m5_acceptance_evidence PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q --tb=short tests/integration/test_business_overview_browser_e2e.py
```

**11 passed in 12.91s**, with the same warning. These tests are a subset of the broad suite, not additional unique passing cases. An initial test assertion incorrectly expected missing Industry alone to require a challenge acknowledgement; it was corrected to follow the unchanged service's actual unresolved-challenge rule. No application governance was weakened to make that assertion pass.

The two M4 baseline failures documented in earlier milestone reports (acceptance despite absent M3, and universal advisory-validator expectations) were not part of this selected run and are not claimed fixed. No newly failing regression remains in the executed suites. `git diff --check` passes. No live-model analytical quality, real HCA completeness or production deployment is certified by scripted acceptance.

## Stop boundary

Final evidence packaging re-read both browser runs through the strict four-section reader and passed schema/content-hash verification. The saved JSON copies retain Python's canonical numeric representation: the browser harness's initial JavaScript serialization had converted integral floats to integers, which preserves JSON value equality but changes this repository's canonical hash bytes. Only the exported evidence copies were corrected from their identical persisted artifacts; no source artifact, recorded hash or application behavior changed. [Verification manifest](milestone-5-verification/verification-manifest.json) records SHA-256 hashes for the 28 evidence files and the 653 unchanged pre-existing files count.

Offline integration, strict saved-memo navigation and the requested lifecycle/compatibility verification are complete, subject to the explicit native-PDF runtime prerequisite above. Milestones 1–4 and legacy behavior are preserved. No live HCA run has been initiated; any live-model evaluation requires separate authorization. Stop here.
