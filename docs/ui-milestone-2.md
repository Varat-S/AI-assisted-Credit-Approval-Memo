# Milestone 2 — Execution and durable history

Implemented locally on `Alan's-Branch`, preserving the uncommitted Milestone 1 workspace. No commit, push, merge or PR. Specialist, synthesis and challenge prompts, scoring, evidence admission and validation methodology are unchanged. Milestone 3 is not implemented.

## Implementation

Setup now submits only an explicit **Run Analysis** POST to `/analysis/start`. The handler repeats the company/package/hash/cutoff/scope/mode validation, settles the case through `bo_fo.plan`, constructs the existing BO, Module 3 and FO provider backends, and checks Vertex SDK/credential discovery without requesting a model response. A successful submission redirects to `/analysis/{job_id}/execution`. GETs, configuration checks, polling and page refresh never launch a job. Live model permissions and model availability can still fail during execution; configuration presence is not a successful paid connection test.

The worker remains the existing `bo_fo.run_bo_fo` and `BusinessOverviewRunner.run_case` full path: specialist analysis and validation, evidence reconciliation, synthesis and synthesis validation, independent challenge, existing bounded remediation, and reporting. The specialist-only entry point is not used. Combined scope also uses the existing `FinancialOverviewRunner`, FO staging/merge and deterministic RMS. Exploratory mode changes only the existing supported BO validator setting; FO checks remain enforced.

The existing background thread continues independently of the HTTP request or browser. Stage callbacks observe actual runner boundaries and recorded DAG outcomes; they do not alter agent tasks, dependencies, prompts, validators, retries or financial calculations. FO labels follow its real preparation, pre-check, scoring, trigger-check and reporting steps rather than inventing a separate validation pipeline. The stage event log retains attempts/rounds and failures even when a later repair succeeds. Module 3 and debt specialist validation outcomes are also recorded. No elapsed-time percentages are shown. Work units, errors, stage details, agent outcomes and token/cost summaries are collapsed under Execution Details. Cost is an estimate from configured prices and provider-reported tokens, including the separate Module 3 backend; it is saved at progress checkpoints.

Credit Memos lists persisted jobs of every terminal or active status and opens each execution screen. That screen links to existing BO/FO reports when committed run IDs are available. A missing synthesis is labelled unavailable/incomplete. Execution completion and human approval are separate: a finished pipeline normally remains Human Review Required. Existing report/review pages remain authoritative for subsequent human decisions; this milestone records governance at execution completion rather than implementing a new approval dashboard.

### Storage and recovery

`app/services/analysis_jobs.py` initializes schema version 1 in a SQLite sidecar: `<analysis database filename>.jobs.sqlite`, beside the database resolved from `DATABASE_URL`. For the default configuration this is `data/credit_memo.db.jobs.sqlite`. Its `analysis_jobs` table stores job IDs, process ownership, submission keys/request hashes and serialized configuration/progress/results. No provider objects, API keys or credential payloads are stored. The sidecar avoids the long BO write lock; no main analysis-table migration is needed. Keep the sidecar when backing up or moving the analysis database.

Claiming a submission key is transactional with a unique constraint. Concurrent retries with the same key and configuration return the original job; reuse with different settings returns HTTP 409. Each fresh Setup page provides a new key so an intentional repeat is allowed. The button disables during submission and successful POSTs redirect to a read-only URL. Keys are retained even for failed/interrupted jobs, preventing an accidental retry from becoming another paid run.

Created/start/end times, submitted metadata, scope, validation mode, cancellation requests, stage attempts, section results, BO/FO run IDs, output references and costs persist. A committed section's references are saved before waiting for its sibling. Partial committed outputs remain visible when another section fails or the process dies. Legacy `/run`, `/run/start`, status and stop routes keep their existing contracts (`status=finished` for normal completion); the new UI uses the normalized `execution_status=completed` field.

When history/status is read after worker process termination, active jobs owned by that dead process become **Interrupted**, with an explanation and their recorded partial state. Another live HTTP process does not incorrectly interrupt a live owner's job. A worker thread exiting exceptionally is also recorded as failed/interrupted. There is **no automatic resubmission or mid-run resumption**: open New Analysis and deliberately submit a new run. Restarting Uvicorn, reloading code, closing the Terminal server or shutting down the Mac ends workers. Browser navigation, closing its tab and refreshing do not.

Stop Analysis persists an explicit request, displays Stopping, and uses the existing checkpoint cancellation. A model call already underway finishes before the next checkpoint. A completed sibling retains its outputs. Pending/unreached stages become skipped; an active stopped stage is stopped. Uncommitted BO database work can roll back on cancellation/crash under the existing transaction design; the sidecar is not a checkpoint engine and cannot reconstruct uncommitted findings. In-flight token costs may be missing after a crash. History before this milestone's in-memory manager cannot be reconstructed automatically.

### Exploratory governance

The BO handoff acceptance service rejects `validators_enforced=false`, including direct review API requests. Existing BO and combined credit views hide acceptance for those handoffs. Recommendation sign-off and final snapshot finalization also fail closed when the case's latest BO handoff is exploratory. This conservative case-level guard prevents final approval through another endpoint; a new Standard-mode run is required before governed final approval. Existing missing-conclusion, unresolved-challenge acknowledgement, reviewer/reason, escalation, approval-hash and immutability protections still apply. Legacy handoffs lacking the flag retain their prior standard behavior.

## Files changed for Milestone 2

- `app/api/analysis.py`: POST launch, execution and stop routes; persisted history.
- `app/api/templates/analysis_setup.html.j2`: enabled explicit POST and duplicate-click protection.
- `app/api/templates/analysis_execution.html.j2` (new): polling, stages, cancellation, details and existing report links.
- `app/api/templates/credit_memos.html.j2`: basic persistent history.
- `app/services/analysis_jobs.py` (new): SQLite sidecar, idempotency, ownership recovery and persisted stop checks.
- `app/services/bo_fo.py`: persistence around the existing worker; partial outputs, normalized status and stage/cost callbacks.
- `app/services/bo/runner.py`, `app/services/fo/runner.py`: observational stage events only.
- `app/api/bo_fo.py`: remove obsolete in-memory-only error wording.
- `app/services/bo/handoff.py`, `app/services/bo/workbench.py`, `app/services/rms/case_view.py`: exploratory acceptance guards and existing button eligibility.
- `app/services/review/approval.py`, `workflow.py`, `finalization.py`: fail-closed final approval guard.
- `tests/integration/test_analysis_execution.py` (new), `test_analysis_workspace.py`, `test_bo_cli_workbench.py`, `test_bo_fo_combined.py`: lifecycle/governance/full-pipeline tests and updated Milestone 1 expectations.
- `docs/ui-milestone-2.md` (new): implementation, testing and manual instructions.

Other working changes shown by Git belong to the preserved Milestone 1. No extra frontend framework or alternate production pipeline was added.

## Automated verification

All tests use mocked/scripted providers and synthetic/fixture evidence; no paid generation or live SEC retrieval. The regression command is:

```bash
/Users/Daniel/.local/bin/uv run --locked --extra dev --extra vertex pytest -q \
  tests/integration/test_analysis_execution.py \
  tests/integration/test_analysis_workspace.py \
  tests/integration/test_browser_preview.py \
  tests/integration/test_workbench_api.py \
  tests/integration/test_bo_cli_workbench.py \
  tests/integration/test_bo_fo_combined.py \
  tests/integration/test_m3_workflow.py \
  tests/unit/test_bo_model_choice.py \
  tests/unit/test_llm_usage_cost.py \
  tests/unit/test_human_review_workflow.py \
  tests/integration/test_review_workflow.py
```

Execution in this environment uses the existing Python 3.11 interpreter and runtime dependencies on a source-matched `/private/tmp/bo_ui_milestone2_validation` mirror to avoid slow Documents filesystem reads. Final counts and captured logs are in `UI_Milestone2_20261101/implementation-and-test-report.md` and `automated-tests.log` beside the repository.

Coverage includes all four scope/mode combinations; server-side invalid/missing-evidence/provider rejection; no launch on GET/check; idempotency including concurrent SQLite claims and mismatched-key rejection; intentional repeats; refresh/navigation; active/completed/failed/interrupted history; cross-manager persistence and stopping; real full-runner synthesis/challenge callbacks; committed partial outputs; thread termination; exploratory UI/API rejection and sign-off/finalization guards; and existing BO/FO, workbench, cost and review regressions.

## Launch and manual testing

```bash
cd "/Users/Daniel/Documents/ChatGPT/Daniel's AI in Finance 2/alan-branch-current"
/Users/Daniel/.local/bin/uv run --locked --extra vertex uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ . Do not use `--reload` during a paid run: editing code would restart its worker.

1. Open New Analysis. HCA Healthcare FY2024 is the only company. Confirm the actual 14 February 2025 filing date and 31 March 2025 cutoff.
2. Select Business + Financial Overview or BO Only and Standard or Exploratory. Check setup makes no model calls. Correct any evidence/provider errors.
3. Click Run Analysis when you intend to incur configured provider charges. The server revalidates and redirects to a unique execution URL. An invalid setup starts nothing.
4. Watch actual stage status updates. Expand Execution Details to inspect attempts, validation, errors, work units and available token/cost information.
5. Record the job ID; choose Back to Workspace → Credit Memos → the same run. Its ID and progress should be preserved. Refresh, close and reopen the tab; no duplicate run should appear.
6. Only Stop Analysis requests cancellation. Expect Stopping until the current call reaches a safe checkpoint, then Stopped.
7. On completion use the available BO/FO report links. A completed execution can still require human review or lack a valid synthesis; inspect the recorded status rather than treating completion as approval.
8. To check restart behavior, restart the server while a test run is active. Its persisted job should become Interrupted, retain partial committed references and never automatically make another model call. A deliberate new Setup submission creates a separate run.
9. Exploratory handoffs must not expose acceptance and direct acceptance/finalization requests must be rejected.

### Browser evidence captured for this milestone

The isolated test preview is http://127.0.0.1:8766/ and is explicitly banner-labelled MOCKED BROWSER TEST ONLY. Its harness lives outside the repository, disables provider execution, and stores history in `/private/tmp/m2_browser_demo_jobs.sqlite`. It uses the actual HCA package for setup validation and synthetic progress for execution. It is not evidence of live HCA analysis, connectivity or model quality.

Screenshots in `UI_Milestone2_20261101/` were captured and visually inspected:

- `execution-mocked.jpg`: active mocked specialist progress with BO/FO panels.
- `history-mocked.jpg`: running and interrupted persisted test jobs.
- `returned-active-mocked.jpg`: same job returned through Home → Credit Memos, now at synthesis.
- `reopened-active-mocked.jpg`: same job after closing/reopening its tab.
- `interrupted-mocked.jpg`: actual test-server restart detected; no automatic retry.
- `stopped-mocked.jpg`: explicit Stop reaches a terminal state through polling.

## Milestone 3 readiness

Remaining: richer Credit Memos filtering/search/navigation; final synthesized memo presentation distinct from internal specialist evidence; run-specific Audit & Review; citation/evidence navigation; and the user-friendly human review experience. Existing reports and safeguards remain available, but those presentation features have not been built. Stop here for user review.
