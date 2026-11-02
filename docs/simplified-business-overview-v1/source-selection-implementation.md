# Source-only Business Orchestrator — implementation and verification

The browser New Analysis path now uses `bo-source-selection-output-1.0.0` with policy `bo-source-selection-1.0.0`. The orchestrator selects and orders existing Module 1 Agents 1–6 findings. It cannot return analytical text, numerical values, citations, titles, component references or an authored overall assessment. Existing contracts and frozen historical reports remain readable.

## Behavior

The model returns `selections` (finding ID, lead/driver/risk placement, audit reason) and `omissions` (finding ID and audit reason). Every eligible finding must occur exactly once across the two lists. Exactly one existing finding is the lead; there is no newly synthesized headline opinion. Ordering is retained within the page's existing driver/risk groups. Contradictory direction placement, unknown IDs, duplicates, missing decisions, whitespace-only reasons and extra fields fail closed.

A pure deterministic projector copies each chosen source claim verbatim, together with its original parameter references, numerical bindings and evidence IDs. It attaches the source's Agent 6 components automatically and generates claim IDs, the complete selection ledger and interaction references. Management-attributed and qualified findings receive fixed visible labels; original missing-information text and counterevidence warnings remain visible. Detailed validation notes, interpretation, quotes, citations and the full source records remain in existing expandable evidence panels and Audit & Review. Audit reasons are never memo analysis or evidence.

The internal adapter is separately versioned `bo-source-copy-projection-1.0.0`. It populates the existing conclusion fields for compatibility; it does not invoke the old prose-writing validator or reinterpret specialist calculations. Source eligibility, current producers, snapshot identity, canonical evidence and accepted/current parameter provenance remain enforced. Invalid selection plans receive the existing single bounded repair; a second failure produces an unavailable Competitive Positioning block, retains eligible other sections and leaves review pending. No extra retries or calls were introduced.

Independent challenge still reviews selection, material omissions, balance, duplication and source faithfulness. The challenger has a versioned source-selection prompt. Exploratory Mode still relaxes specialist validators, while selection integrity and source provenance remain mandatory; the setup UI now says this explicitly. Exploratory runs remain ineligible for approval.

## Design and compatibility

The four-section JSON schema, source-copy rules for Modules 2–4, existing HTML renderer, desktop corporate-structure/debt columns, landscape print CSS, full debt schedules and collapsed evidence controls are retained. The existing final-page layout renders the selected lead, business drivers and material risks in Competitive Positioning. Selection order cannot move findings into unrelated memo sections.

The old writing contract (`bo-competitive-positioning-output-1.0.0`) and no-contract legacy path remain supported. Existing HCA runs were not backfilled, regenerated, reapproved or modified. Saved readers still reject corrupt bindings and cross-run substitutions. The source-selection contract has distinct prompt, response-schema and agent/cache identities; specialist/Agent 6 definitions remain identical. FO/RMS scoring and review rules were not changed.

## Files in this change

- `app/prompts/source_selection.py` — new narrow response contract, selector/challenger prompts and versions.
- `app/services/bo/source_selection.py` — new selection validator and deterministic projector.
- `app/services/bo/runner.py` — opt-in selection execution, projection, audit plan and mandatory provenance; old writer retained.
- `app/services/agents/registry.py` — versioned selector/challenger registrations and separate identity.
- `app/services/bo_fo.py` — browser activation, contract-specific policy metadata and selection stage label; legacy contract retained.
- `app/services/bo/competitive_positioning.py` — dispatch independent-review schema by policy; old writer checks unchanged.
- `app/services/bo/workbench.py`, `app/services/bo/four_section.py` — recognize the new version with exact contract/policy identity checks. Existing assembler content-copy behavior is unchanged.
- `app/api/templates/analysis_setup.html.j2` — clarify Exploratory Mode's remaining mandatory checks.
- `tests/unit/test_bo_source_selection.py` — source equality, rewrite rejection, selection integrity, Agent 6 lineage and specialist/cache separation.
- `tests/business_overview_browser_helpers.py`, `tests/integration/test_business_overview_browser_e2e.py` — new scripted selection responses and real pipeline/evidence/history/repair checks.
- This report and `source-selection-verification/` — offline proof artifacts and screenshots.

All pre-existing uncommitted milestone work was retained. No specialist analytical prompt, Agent 6 reasoning, renderer stylesheet or debt calculation was edited.

## Saved HCA failures: read-only offline proof

[Replay results and exact projections](source-selection-verification/saved-hca-replay.json) were produced using the strict saved-source reader and a read-only SQLite connection. Example selections were supplied deterministically; this is a projection/provenance proof, not a live-model selection-quality test or a new production analysis.

| Original run | Mode | Eligible current findings | Selected example findings | Result |
|---|---|---:|---:|---|
| `ar_e58358f9a55f4a72` | Standard | 25 | 4 | PASS |
| `ar_919c5f5c8483497b` | Exploratory | 29 | 3 | PASS |

Both projections passed selection integrity, exact source-text/reference/numerical-binding equality and existing typed conclusion provenance. Frozen stage hashes and hash chains remained unchanged. This removes the original model-authored citation, attribution-placement and ledger reconstruction failure mechanism. It does not certify all possible future selections or repair poor specialist analysis.

Replay command (local proof script, not installed application functionality):

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python /private/tmp/kiro_replay_source_selection.py
```

## Actual browser proof

An isolated localhost demo blocked real providers and SEC transport and used fictional Northfield source files. The actual New Analysis submission, worker, ingestion, specialist execution, governance, source selection, independent challenge, persistence, strict reader and existing Review renderer executed.

Job `15a100def7e94bd0a57cae1a0d3016f8`, run `ar_8bb717884a784ffb`: selection and challenge each executed once, no selection repair was required, and the source-copy Competitive Positioning displayed successfully. Industry remained unavailable and the memo honestly remained incomplete/human review required. Native evidence controls began collapsed and expanded/collapsed successfully.

- [Strict-read memo JSON](source-selection-verification/offline-browser-memo.json)
- [Stage, selection and challenge trace](source-selection-verification/offline-browser-trace.json)
- [Desktop Review](source-selection-verification/review-desktop.png)
- [Competitive Positioning preview](source-selection-verification/competitive-positioning.png)
- [Expanded evidence](source-selection-verification/evidence-expanded.png)

The temporary demo was stopped. Both real local HCA jobs were confirmed completed before the actual server was restarted with the new implementation. `http://127.0.0.1:8000/analysis/new` was opened and visibly verified with both HCA filings available and the updated mode explanation. No live run was started.

## Test commands and results

Run from the repository with the existing sibling virtual environment; no dependency installs.

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/unit/test_bo_source_selection.py tests/unit/test_bo_competitive_positioning.py tests/integration/test_bo_competitive_positioning.py tests/integration/test_bo_four_section.py tests/integration/test_bo_four_section_independent.py tests/integration/test_bo_four_section_renderer.py
```

**135 passed in 42.46s.** This includes the prior writer, assembler/strict-reader adversarial proofs and renderer regressions. An enum assignment in the new test fixture initially produced a serializer warning; the fixture now uses the actual enum.

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/integration/test_business_overview_browser_e2e.py tests/integration/test_analysis_execution.py tests/integration/test_analysis_worker_health.py tests/integration/test_bo_fo_combined.py tests/integration/test_bo_downstream_contract.py tests/integration/test_rms_runner.py tests/integration/test_analysis_review_workspace.py tests/integration/test_analysis_review_financial.py tests/integration/test_analysis_workspace.py tests/integration/test_bo_cli_workbench.py tests/integration/test_review_workflow.py tests/unit/test_human_review_workflow.py tests/unit/test_audit_immutability.py tests/integration/test_final_snapshot_immutability.py tests/integration/test_json_export_integrity.py
```

**185 passed, 1 skipped in 85.75s.** The skip is the existing absent optional PDF backend, not a selector failure. Existing native PDF availability is unchanged. The Starlette/httpx deprecation warning remains.

After adding three malformed-selection/repair cases and the final projection version, reran all new focused tests:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q --tb=short tests/unit/test_bo_source_selection.py tests/integration/test_business_overview_browser_e2e.py
```

**26 passed in 14.40s**, with only the existing Starlette/httpx warning. This includes 23 previously covered cases and 3 additional repair/fail-closed cases: **323 distinct passing cases across these suites, 1 skipped**. A malformed plan repairs once without rerunning specialists, or remains rejected after the one repair in either Standard or Exploratory Mode. The existing UI still opens a partial memo in the latter case.

`git diff --check` passes. No failing test remains in the executed suites. Earlier documented unrelated M4 baseline failures were not part of these selected suites and are not claimed fixed.

## Practical limits

The selector can still fail if it returns invalid IDs, incomplete decisions or an invalid shape, or if an upstream specialist is unavailable. Such states remain explicit rather than being published as successful analytical acceptance. Live selection quality has not been tested by this change. The optional native PDF backend is still absent; the renderer/print layout was reused and covered by regression tests without installing it.

No live inference, SEC acquisition, new dependencies, historical report writes, deployment, commit, push or merge was performed. The real UI is running for the user's next test.
