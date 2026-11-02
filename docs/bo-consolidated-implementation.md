# Consolidated Business Overview — implementation report

Branch: UI_Draft_V1. Baseline: fbf08aa7ded540aed58acdd3bc47c21389d00949.
The initial checkout was clean. No commits, push, merge, deployment, live inference,
SEC acquisition, production data writes, dependency installation or prompt changes to
specialists were performed.

## Delivered behaviour

New Analysis BO executions opt into a fixed, versioned Module 1 selection prompt and
strict schema. All candidate dispositions are audited separately from admissibility.
Five distinct supported insights are required for complete status, with duplicate-group,
text, source-reference, quote binding, qualification and disposition checks. Existing
independent challenge also checks semantic splitting, contradictions and economic
coverage. One bounded selection repair uses existing admitted findings; unsupported
repairs cannot erase the previous supported draft. Specialist retrieval/coverage and
challenger remediation retain existing bounds. Shortfall remains incomplete and requires
human review. No audit-only coverage insertion is applied in this path.

The deterministic assembler reads existing exact-run memo/audit archives through their
hash-chain and identity guards. It copies mapped M2–M4 fields, stores item hashes and
source field paths, and records the versioned consolidated JSON through StageRecorder.
Loading verifies both its own chain and full equality with reassembly from frozen sources.
Selection must match the actual final conclusion and orchestrator producer, with an
actual recorded challenger outcome. A successful schema never confers approval.

Review and existing HTML/PDF memo routes share one pure Jinja body. It renders only the
five ordered BO sections, preserves full copied records and qualifications, exposes
sources and copy verification, and includes responsive desktop/mobile and print styles.
No content selection or inference occurs in the renderer. The new JSON is available via
`/cases/<case>/bo/runs/<run>/consolidated.json` and as
`consolidated_business_overview.json` in the existing run output directory. Historical
memo/audit/handoff schemas and JSON exports remain compatible. Current human review
statuses are overlaid through the existing reviewed-memo logic without rewriting archives.

## Source discovery and intentional adaptations

See `bo-consolidated.md` for exact field mappings and ownership. Actual UI entry point:
`analysis_review.html.j2`, not the older `draft_review.html.j2`.

Module 2 exposes governed industry findings, not a standalone full report. The UI
explicitly marks this report gap/incompleteness and copies every available finding,
including figures, interpretation, quotations and qualifications. No replacement industry
prose is generated. Module 3 exposes a complete structured management artifact rather
than one narrative field. Module 4's existing D4 is its designated credit conclusion,
not a separately stored refinancing-only conclusion; it is copied in full alongside D2.

The shortfall repair is selection-only over admitted validated material. It does not
launch new acquisition or an unconstrained specialist search to fill a point quota.
Existing bounded specialist retrieval and independent challenge remediation remain in place.
Missing, failed and unexecuted coverage cannot be represented as successful review.

## Files changed

New source:
- `app/schemas/bo_consolidated.py`: versioned artifact, strict synthesis/point/decision contracts.
- `app/prompts/bo_consolidated.py`: fixed selection and independent-review policy v1.
- `app/services/bo/consolidated.py`: deterministic selection gates, assembly and verified loading.
- `app/services/reporting/templates/bo_consolidated{,_body}.html.j2`: shared renderer.
- `tests/integration/test_bo_consolidated.py`: 19 offline acceptance/security/fidelity/UI cases.

Integration edits:
- `app/services/bo/{runner,reporting,workbench}.py`: existing execution, report persistence,
  artifact retrieval, bounded shortfall handling and consolidated HTML/PDF dispatch.
- `app/services/bo_fo.py`: explicit opt-in argument; old callers keep legacy defaults.
- `app/services/analysis_workspace.py`: verified artifact loading and current review overlay.
- `app/api/{analysis,workbench}.py`: UI opt-in, shared template path, existing export routes.
- `app/api/templates/analysis_{review,audit}.html.j2`: five-section Review and selection audit.
- Documentation and `examples/bo_consolidated/`: schemas, synthetic JSON/audit, previews,
  screenshots, reproducible offline tools and test logs.

## Verification

Combined relevant offline regression run: **264 passed, 2 failed**, 1 existing
Starlette/httpx deprecation warning (104.52 seconds). It covers the new path, archive
identity, Review/Audit, claim provenance, financial Review, combined workers, setup,
legacy BO pipeline, v3 roster, debt specialists, reporting, governance and handoff.
Final consolidated-path run: **19 passed**, 1 existing warning, repeated
after contract/rendering changes. No full-repository pass is claimed.

Both failures were reproduced separately on untouched baseline fbf08aa in an isolated
checkout: `test_both_m4_specialists_reach_governed_output_and_synthesis` expects an
accepted overall status while current Module 3 is incomplete; and
`test_validators_off_still_drafts_the_full_memo` expects every hypothesis validator to
be advisory despite existing enforced validation. Neither is changed by this task.
Full assertion output is retained in the baseline/regression logs.

The new tests cover five supported points; qualified eligibility; shortfall/invalid
repair preservation; invalid numbers/bases/qualifications/duplicates/dispositions;
independent material challenge; full D1/D2/D4 copy fidelity; synthetic structure and
management fidelity; long industry content with exact numeric strings and citations;
case/run/hash/copy/approval/selection forgeries even with recomputed archive checksums;
and exactly five ordered headings in both Review and HTML exports, plus Audit and JSON.
Synthetic long-source fixture tests leave M3 incomplete rather than fabricating review.

Test tooling blocked network connections and PDF extraction. The shared optional PDF
package stalled during initial imports; it was replaced only in the isolated test
runner with a stub that raises if used. Application imports and PDF parsing logic were
not modified. Existing pytest fixtures also disable local .env loading and live SEC calls.

## Limits and manual verification

Offline scripted output verifies infrastructure and governance, not live model analytical
quality. No live result is represented as tested. Missing M3 content and the Industry
report gap remain visible. Complete copied debt/industry material can require multiple
pages; there is no one-page clipping or forced small type. Actual PDF generation and
pagination have not been visually verified; shared HTML/print rules are supplied.

Open the saved `review-preview.html` or `preview.html` without running a model. In the
app, select a newly executed consolidated run in Credit Memos, inspect its five-section
Review, open Audit & Review for all candidate decisions, and use the existing memo HTML
or PDF route. Historical runs retain their old presentation. Do not start a live run
merely to inspect the supplied offline preview.

Browser verification checks and final screenshot notes are recorded below.

Browser inspection used the existing Review template with the saved offline run, in
its current dark theme. Exactly five BO h2 headings were observed. Actual rendered
viewport widths were 1309px (desktop) and 354px (mobile); document scroll widths matched
in both cases after correcting nested definition-list overflow. Mobile collapsed the
copy layout to one column. Saved screenshots show the Review context and competitive
analysis. Provenance colours and notices use existing theme variables. Both HTML
previews permit natural multi-page continuation; no PDF pagination claim is made.
