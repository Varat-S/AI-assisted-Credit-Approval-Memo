# Pipeline Viewer V2 — Milestone A

Implemented on `feat/pipeline-viewer-v2`, based on `origin/Finalized-Draft-Memo` at `0a50457`. Local worktree: `/Users/pearn/NTU/BU5203/kirotesting-pipeline-viewer-v2`. No push or merge.

## Demonstrate locally

The following uses the existing local virtual environment and the committed, disclosed offline fixtures. It makes no model calls and does not need a database:

```sh
cd /Users/pearn/NTU/BU5203/kirotesting-pipeline-viewer-v2
DEBUG=false OUTPUT_DIR=tests/fixtures/pipeline_viewer /Users/pearn/NTU/BU5203/kirotesting/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8017
```

Open [the graph](http://127.0.0.1:8017/pipeline?case=HCA_registry_fixture&run=bo-recorded). Choose a stage in the graph or searchable stage list. The report opens beside the graph; use **Open full report** for a larger report or **Close** / Escape to return. Scroll or use the buttons to zoom; drag the graph background to pan. **Fit graph** restores the overview. **Architecture on/off** toggles architecture connections independently of recorded references.

Use the run selector to demonstrate:

- `bo-recorded`: Pricing Power findings and evidence, two M4 specialists/validators, rejected challenge and pending governance.
- `run_fixture`: separate corporate-structure diagram and management assessment, with simulation provenance and limitations.
- `fo-recorded`: recorded financial measures, triggers and provisional composite.
- `rms-recorded`: exact recorded BO/FO source bindings, provisional recommendation, blocking gate and warning/waiver.

Each report contains **Report**, **Evidence & Audit**, and **Raw JSON**. Downloads distinguish whole-file original bytes from canonical normalized output. Slices expose their parent file and locator. The PDF link remains the existing deterministic JSON inspection export.

To inspect existing output, set `OUTPUT_DIR` to its absolute pipeline output root (the directory containing `bo`, `fo`, `m3_rebuild`, and/or `rms`). Choose the case and exact run. No files are copied, generated or updated. Runs are not joined by case name. When only one primary run is available it is selected; otherwise a selection is required. An RMS record can include its explicitly bound source runs.

Existing governed review and memo links retain exact run IDs. Those interfaces require their original database and application configuration. The standalone fixture demonstration has no review database; its links do not fabricate corresponding records.

## Architecture and changed files

- `app/services/registry/graph.py`: versioned graph metadata, corrected roster labels, run scoping, independent M3 components, distinct M4 specialists, validators, human review, RMS and final memo stages. Solid edges identify recorded artifact references; dashed edges are architecture only. An audit containing synthesis history is labelled recorded synthesis; a second execution is never inferred from it.
- `app/services/registry/indexer.py`: read-only RMS indexing and separately inspectable recorded roster-validator slices; graceful corrupt M3 manifest entries. Existing manifest and producer artifact schemas are unchanged.
- `app/services/registry/explorer.py`: bounded artifact access, exact identity checks, M3 manifest validation, four-section memo content/source checks, RMS FO hash binding, and byte-level selection pins. Per-agent details include only that producer's findings and referenced sources from the same recorded audit.
- `app/services/registry/stage_report.py`: reusable `pipeline-node-details-2.0` presentation contract and stage-specific field selection; separate execution, validation and governance axes. Reuses the existing management presentation policy. It performs no scoring or inference.
- `app/api/pipeline_explorer.py`: compatible GET routes plus `report.html`. The existing node JSON now includes structured presentation details. Optional content/source hash pins reject changes with HTTP 409.
- `app/api/templates/pipeline_explorer.html.j2` and `pipeline_stage_report.html.j2`: responsive graph, searchable navigation, read-only reports, evidence links, expandable JSON, and shared memo/theme typography and color tokens. Corporate diagrams reuse the existing deterministic SVG renderer.
- `tests/integration/test_pipeline_viewer_v2.py` and `tests/fixtures/pipeline_viewer`: offline HTTP regressions and disclosed recorded fixtures. The older Explorer dual-M4 tests now assert the actual recorded V8-07 rejection of their reduced historical fixture, rather than expecting a successful validation that the current validator does not record.

## Integrity and compatibility limits

Filesystem reports are an inventory of persisted outputs. Byte hashes identify exactly what was selected; a newly calculated hash is not proof of a producer signature or frozen database chain. M3 manifest hashes, four-section embedded hashes and available same-run audit source references, and recorded RMS FO content hashes are checked and rejected on mismatch. Existing governed memo routes retain full database-chain and source-binding verification; the viewer links to them without recreating their analytical or review logic.

Review statuses describe the persisted artifact at recording time. Later database decisions are not silently overlaid. A decision embedded in RMS is shown as recorded, including warnings and waivers; an RMS `approve` recommendation is never labelled final credit approval.

Missing outputs have explicit unavailable states. Unknown/historical schemas use a generic readable fallback and raw inspection. Legacy M3 files outside the current `m3_rebuild` layout are not automatically imported or converted; any available recorded BO memo/audit remains inspectable. Missing source documents, pages, excerpts or verification records are labelled unavailable. Successful execution is not treated as validation success; scoring alone is not a passed validation.

No analytical prompts, validators, scoring, escalation rules, human-review policies, persisted outputs or database records were changed. No API execution or cloud deployment was added.

## Verification results

- **112 passed** across the new viewer regressions and existing Explorer, registry, FO indexing, RMS runner and M3 integration tests. The new viewer file contributes 37 tests. See `focused-tests.txt`, `focused-tests.xml` and `test-summary.json`.
- Additional memo/workspace compatibility checks: **70 passed, 29 failed, 1 skipped**. The same 28 four-section/workspace failures reproduce on the untouched starting commit; the additional legacy memo test failure also reproduces separately there. These fixtures omit amounts required by the current V8-07 filed-amount validator, so expected complete debt content is unavailable. No new compatibility failures were identified. These analytical fixtures and validators were left unchanged. The skipped test requires a saved real HCA run absent from the checkout.
- Desktop 1600×1000 and mobile 390×844 browser inspection: graph selection, Report / Evidence & Audit / Raw JSON tabs, embedded reports, M3 SVG, management, M4 schedules, FO, RMS, and page overflow checks. No JavaScript errors or horizontal page/embedded-report overflow. See screenshots and `browser-verification.json`.
- Tests check original-byte equality, byte-level selection pins, changed slices, M3 component tampering on all routes, corrupt JSON/manifests, exact-run identity, final memo source binding, RMS FO hash mismatch, unresolved challenges, review decisions, missing/partial/skipped/running/failed stages, historical fallback, escaping and read-only access. Reads leave fixture hashes unchanged; provider, analytical execution and database session initialization are blocked during read-only regression checks.

Optional screenshot reproduction with Playwright already installed and the fixture server running:

```sh
PLAYWRIGHT_MODULE=/Users/pearn/stock-monitor/node_modules/playwright CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node scripts/verify_pipeline_viewer.cjs
```

On another machine, omit these variables when Playwright and its browser are available normally. `VIEWER_URL` optionally changes the localhost base URL. The script uses an isolated temporary browser profile.
