# Milestone 3 — Credit Memo History, Review & Audit Workspace

Implemented locally on `Alan's-Branch`. Milestones 1 and 2, including both execution progress-bar components, are preserved. No specialist/synthesizer/challenger prompt, validation methodology, scoring, financial calculation, worker, job store, migration or approval safeguard changed. No paid calls, commit, push, merge or PR. Stopped before Milestone 4.

## Checkpoint 3A: Credit Memos history

**Files:** `app/api/analysis.py`, `app/api/templates/credit_memos.html.j2`, new `app/services/analysis_workspace.py`, new `tests/integration/test_analysis_review_workspace.py`.

The persisted job list is newest first and shows company, creation date, scope, Standard/Exploratory mode, execution status and credit memo governance. Company/job/recorded BO/FO IDs are searchable; execution and validation-mode filters compose. Running, failed, stopped, interrupted and completed states have distinct styling and text. Accessible link labels identify the individual run.

Every destination uses the selected job ID. Running/failed/interrupted jobs open Execution. Completed jobs with a recorded report open Review. Jobs with missing or inconsistent references remain selectable through Execution and are never matched to another company's or the same company's latest memo. Active history does not query unfinished analytical outputs.

**Checkpoint verification before 3B:** 41 tests passed, 0 failed. Browser search returned the selected synthetic HCA run only. Screenshots: `3a-history.jpg`, `3a-search.jpg`, final `3a-history-final.jpg`.

**Manual test:** open `/credit-memos`; search `hca-first` in the synthetic preview, or an actual job/BO/FO ID in the real app. Combine execution/mode filters. Select different HCA rows and confirm their URLs retain distinct IDs.

**Limit:** history is based on M2's durable job records. Older CLI/in-memory executions without an explicit job-to-report mapping are not guessed into combined jobs. Existing legacy report routes remain available. History is not yet paginated.

## Checkpoint 3B: Credit Memo Review

**Files:** workspace service/router above; new `app/api/templates/analysis_review.html.j2` and `analysis_memo_style.html.j2`; `app/api/templates/analysis_execution.html.j2` (an exact-job Review link when execution completes with recorded reports); review tests plus new `tests/integration/test_analysis_review_financial.py`.

`/analysis/{job_id}/review` displays company/period, scope/mode, execution and governance separately, executive assessment, strengths, vulnerabilities, integrated conclusions, recorded Financial Overview, uncertainties and clickable citations. Active jobs return to their Execution page. BO-only jobs omit FO.

The primary BO is projected from the selected handoff's exact `TopicConclusionRow`, compared against its hash-verified frozen audit conclusion. Case, BO ID, evidence version and conclusion acceptance must agree. A validated independent-challenge record must refer to that final conclusion. No successful challenge, missing synthesis, missing archives or advisory-only Exploratory output produces the exact message: **“No validated Business Credit Assessment is available for this run.”** Advisory synthesis remains inspectable in Audit.

Inspected `_further_findings()`, `_m1_sections_with_further_findings()` and the two “Further … findings” template sections. The new Review does not call the legacy renderer or append module/specialist findings. It also omits automatic `COV-*` coverage copies inserted by the existing runner for findings omitted from the model's synthesis. These copies and all canonical reports remain intact. Only citations used by displayed synthesized claims appear in the primary memo; Audit retains the full recorded evidence catalogue. Original citation numbers are preserved.

FO uses the existing `build_memo`, `run_header`, review and override services over the exact recorded FO row, after verifying its payload hash and case. The UI creates no financial metrics and does not fetch a current filing to fill historical provenance. It links to that run's existing FO memo for the complete financial presentation.

**Checkpoint verification before 3C:** 56 tests passed, 0 failed, including actual existing FO rendering with scripted provider fixtures. Screenshots: `3b-review-final.jpg`, `3b-combined-financial.jpg`, `3b-unavailable-exploratory.jpg`, `3b-review-narrow.jpg`, `3b-source-citation.jpg`. The combined visual fixture deliberately uses NVIDIA financial test data and is labelled **not HCA financial analysis**.

**Manual test:** select a completed row from history. Confirm its assessment differs from another run's, click a citation, inspect Financial Overview when included, and use Audit & Review. An exploratory/unavailable record must not present specialist text as a validated assessment.

**Limits:** a historical run lacking sufficient recorded validation/challenge provenance stays incomplete. The UI does not synthesize a replacement narrative. Canonical legacy HTML/PDF exports are unchanged and may retain their older specialist-inclusive presentation. That export behavior is not silently rewritten by this new view.

## Checkpoint 3C: Audit & Review

**Files:** new `app/services/analysis_audit.py` and `app/api/templates/analysis_audit.html.j2`; workspace router/service and shared memo styles; review tests; `tests/integration/test_bo_cli_workbench.py` adds a compatibility test over real existing scripted BO artefacts.

`/analysis/{job_id}/audit` has exactly five top-level sections:

1. **Specialist Findings:** all recorded versions, including superseded, qualified, rejected and audit-only findings; originating specialist; raw-response original wording where actually recorded; validator-recorded wording; supporting/contradicting evidence; management/debt artefacts; available raw/parsed outputs.
2. **Validator Decisions:** dispositions, notes, modifications, review flags, model-stated classifications, quote recovery, coverage/reconciliation, validator run logs, and the selected FO's prechecks/analyst decisions.
3. **Cross-Module Synthesizer:** run outputs, validation feedback/attempts, accepted and superseded conclusions, individual claims, and exact links to supporting specialist records, evidence and calculation traces. Coverage copies remain available here.
4. **Independent Challenger:** actual execution logs, rounds, severity, affected-claim links bound to the same conclusion version, reanalysis/remediation requests, decisions and final recorded outcome.
5. **Evidence & Citations:** admitted snapshot passages, document identities, quotation records and locations, parameter/calculation provenance and rejected sources. Citation existence, quotation verification, entailment verification and the finding's disposition are separate fields. Missing explicit verification reads **Not recorded**; the UI never treats a citation as proof or reruns validation.

Existing `bo_artifact`/`verified_artifacts` and typed handoff hash verification remain authoritative. Raw agent logs are selected only by exact analysis ID and checked against case/evidence version. No model run is selected just because its case/company matches. Raw responses and original wording not bound to the selected run are not guessed from unrelated files or model logs. The canonical evidence stage is verified against its frozen audit hash where recorded.

Display copies redact credential keys, configured secret values, bearer tokens, private-key material and recognizable credential patterns. Provider configuration objects are not exposed. Credential-bearing, non-HTTP(S) or userinfo-bearing source URLs are not linked. Original stored records are unchanged. Only recorded verification results are displayed: case-level grounding records without a safe run binding are not borrowed from another run.

The new audit workspace is read-only. Existing BO/FO human-review links carry exact run IDs and keep all prior acceptance, acknowledgement, escalation, integrity and Exploratory restrictions. No competing approval service or automatic approval was added. BO-only approval reflects the existing accepted handoff; combined approval is shown only for an existing finalized, integrity-checked snapshot explicitly identifying both selected BO and FO runs. Without that explicit pair binding it remains Human Review Required.

**Focused checkpoint verification:** 29 tests passed, 0 failed, including the actual legacy full BO runner's memo/audit, exact-run selection, frozen-record preservation, original/validated traceability, missing-data behavior, redaction, direct Exploratory API rejection and Standard acceptance through the existing guarded service. The final suite below includes these checks.

**Browser verification:** all five audit sections and local reference targets were checked; no foreign HCA run appeared in the selected audit; the seeded credential was redacted. Synthesized-claim → hypothesis and memo-citation → source links were clicked and stayed within the selected run. Desktop and narrow layouts were inspected; the narrow financial view showed seven recorded measure rows without document overflow. Temporary viewport overrides were reset.

**Manual test:** open Review → Audit & Review. Use the five navigation links, compare original and validator wording, expand raw output/validation feedback, follow a supporting hypothesis/evidence link and inspect the challenger decision. Use the existing human-review links for decisions; merely viewing either new page must never approve anything.

**Limits:** historical data that was never recorded cannot be reconstructed. Some independent module outputs may exist without a safe run-bound raw-log reference; only their recorded artefacts are shown. Audit renders all selected-run records rather than paginating them. Missing records render unavailable/Not recorded; conflicting or corrupt integrity-checked records fail closed with HTTP 409. Decision entry remains in the existing human-review pages rather than a newly redesigned approval flow.

## Final test run

The consolidated suite covers the new workspace plus Milestones 1/2, legacy BO/FO routes, full orchestration, workbench, model/cost checks, review workflow, Exploratory safeguards and all execution-bar refinements. No paid generation or live SEC requests. Final count and complete output: `UI_Milestone3_20261101/automated-tests.log` beside the repository; source hashes and browser checks are recorded there too.

Run the same tests from the checkout:

```bash
/Users/Daniel/.local/bin/uv run --locked --extra dev --extra vertex pytest -q \
  tests/integration/test_analysis_review_workspace.py \
  tests/integration/test_analysis_review_financial.py \
  tests/integration/test_execution_ui_refinement.py \
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

This environment used its existing Python 3.11 interpreter and runtime dependencies on a source-matched `/private/tmp/bo_ui_milestone2_validation` mirror, avoiding slow Documents reads. JavaScript state tests used existing JavaScriptCore. No framework or runtime dependency was added.

## View locally

The isolated, labelled synthetic preview is http://127.0.0.1:8767/credit-memos . Select `hca-first` for validated post-challenge presentation, `hca-second` for an advisory/unavailable assessment, or `financial-display-fixture` for the explicitly mixed-source financial UI demo. These are test records, not real HCA model outputs. The preview harness blocks live providers and is outside the repository. Real production history/database records were not seeded or modified.

Launch the real application with:

```bash
cd "/Users/Daniel/Documents/ChatGPT/Daniel's AI in Finance 2/alan-branch-current"
/Users/Daniel/.local/bin/uv run --locked --extra vertex uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ → Credit Memos → select a tracked run → Review → Audit & Review. Reading these pages does not create a job or call a provider. Do not use `--reload` while a paid M2 worker is active; server restarts retain its history and mark interruption rather than resume paid calls.

## Milestone 4 candidates — not implemented

- A polished decision-entry experience over the existing guarded review endpoints, and explicit combined-run final-snapshot binding where older records lack it.
- Print/export of the new synthesis-only Review presentation, keeping canonical exports reproducible.
- Larger-history pagination/batched projections and large-audit navigation improvements.
- Explicit migration/import of legacy reports only when trustworthy job-to-report lineage is available, plus better run-bound raw/verification recording for future analyses.
- User acceptance testing with actual historical records and, only under separate authorization, live provider runs.

These are remaining candidates, not an assumed Milestone 4 scope. No Milestone 4 work has started.
