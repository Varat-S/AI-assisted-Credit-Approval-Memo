# Milestone 3 implementation report

Implemented on `UI_Draft_V1`, based on commit `34d61e7b3e547228d6766ec4a7e916395821a906`. Milestone 2 and unrelated working-tree content are preserved. No commits, pushes, merges, deployment, new dependencies, live inference or SEC acquisition were performed. Milestone 4 is not implemented.

## Delivered contract and behavior

The new document is `business_overview_four_section_memo`, schema `bo-four-section-memo-1.0.0`, assembler `bo-four-section-assembler-1.0.0`. The executable JSON Schema is in `app/schemas/bo_four_section.py`; its exported review copy is [four-section.schema.v1.json](four-section.schema.v1.json).

The assembler produces exactly four ordered sections. Section 1 records `structure_left_debt_right`. Sections and its two independent components expose `complete`, `partial` or `unavailable`, recorded upstream status, validation status, source reference and visible warnings. Overall completeness is complete only when every required component is complete. Completeness does not confer human approval.

The source-preserving Adjustment A takes precedence over the narrower projections in the Milestone 1 example. Competitive Positioning contains the **whole exact challenged TopicConclusion payload**, with the whole bound editorial selection ledger alongside it. Industry content is an object containing the full findings array. Source objects remain opaque JSON inside the output schema: assembly does not reconstruct them through presentation models, rename enums, calculate totals or drop nested fields.

Evidence disclosure is metadata only: initially collapsed evidence, citations and quotations retained in JSON, material limitations and completeness warnings marked always visible. No renderer, styling or expandable control was built. There is no Refinancing History section; D2–D4 remain in existing audit/module records.

## Exact source mappings

All paths below refer to the selected run's verified frozen `bo_audit:{analysis_run_id}` stage. Each copied source reference carries the whole-stage SHA-256, source JSON pointer and canonical component content hash.

| Output | Frozen source pointer | Copy behavior |
|---|---|---|
| Section 1 `structure.content` | `/module_conclusions/M3/m3_rebuild/structure/artifact` | Whole verified diagram artifact, including simulation notice and provenance |
| Section 1 `debt_obligations.content` | `/module_conclusions/M4/m4_analysis/deliverable_1` | Whole validated D1; both schedules, all rows/fields, creditor framework and signed reconciling items |
| Section 2 `content` | `/module_conclusions/M3/m3_rebuild/management/artifact` | Whole reviewed management artifact, observations, profiles, qualifications and limitations |
| Section 3 `content` | `/conclusions/{exact_conclusion_index}/payload` | Whole payload matching the selected current accepted TopicConclusion row |
| Section 3 `editorial_selection` | `/orchestrator/editorial_selection` | Whole Milestone 2 ledger, including validated Agent 6 interaction references |
| Section 3 `challenge_source_ref` | `/challenger/rounds/{final_round_index}` | Reference to exact validated final challenge bound to the same conclusion and ledger |
| Section 4 `content.findings` | `/module_conclusions/M2/findings` | Every eligible governed finding in original source order |

Module 2 findings must match the selected audit's accepted, validated canonical hypotheses and admitted evidence. There is no materiality threshold, sorting or deduplication. If its designated list contains an ineligible or mismatched record, the component is rejected rather than silently shortened.

Corporate structure and management are independently eligible. Reviewed management 3.0 is required; older management contracts are not silently promoted. Partial reviewed management can survive with explicit warnings. M4 requires the recorded enforced Validator 8 result, the six expected passing checks, exact producer identity, admitted evidence and D1 equality against its validated assessment. Empty schedules produce a partial warning rather than an inferred zero balance.

Competitive Positioning requires the exact Milestone 2 contract, conclusion/orchestrator IDs, ledger hash, successful producer validation and final independently validated challenge of that exact conclusion/ledger. It never invokes legacy narrative-reinsertion mechanisms or substitutes legacy M1 sections. Omitted findings stay in audit/downstream records.

## Architecture, persistence and review

`load_saved_inputs(session, analysis_run_id)` resolves the exact run, unique handoff and verified hash-chained stages. It checks case/company, run, snapshot version/hash, period, cutoff and root audit/provenance integrity. It never queries a latest run or opens local evidence files. Root corruption fails assembly closed. Component failures become explicit unavailable blocks while other eligible components survive.

Reporting freezes an additional `bo_assembly_provenance:{analysis_run_id}` stage, version `bo-four-section-provenance-1.0.0`. This captures already-recorded M3 packet bindings, source producer identities/validation results, component hashes and initial governance. It does not rerun specialist validators. The native M4 producer record has case/snapshot identity; its association with this BO analysis run is captured from that run's result in this frozen provenance stage.

`assemble(SavedInputs)` is a pure deterministic transformation. It rechecks detached input hashes/root identity, verifies component eligibility, deep-copies sources, emits warnings and computes a canonical content hash excluding the hash field itself. It has no clock, model, retrieval or source-file dependency.

`persist(...)` independently reloads the authoritative DB stages and requires equality with their recomputed memo. Detached examples cannot authorize persistence. It freezes `bo_four_section_memo:{analysis_run_id}` through the existing StageRecorder and, when reporting has an output directory, writes `business_overview_four_section.v1.json`. Repetition is idempotent. Conflicting existing stages or files produce integrity errors and are not overwritten.

Reporting binds the stage name, schema version, stage SHA-256 and memo content hash under `handoff.canonical_references.four_section_memo`, then recomputes the existing handoff analytical hash before storing the handoff. The artifact is assembled after recorded outcomes and before human review. Its frozen human-review status remains pending; existing review overlays carry subsequent decisions without rewriting analytical history.

`bo_artifact(..., kind='four_section')` reads only an existing bound artifact, verifies the complete source chain and handoff binding, and recomputes source equality. It never backfills historical runs. Legacy reporting remains available. Generation is additive for the explicit Milestone 2 Competitive Positioning contract; legacy defaults are unchanged. The registry discovers the new file when present, without adding entries for old runs. Registry disk inventory verifies the document contract/hash/directory identity; authoritative frozen-chain verification belongs to the strict reader.

## Offline artifacts and equality proofs

- [Populated sample](four-section.populated.sample.v1.json): all required components complete; human review pending; fictional scripted Northfield data, clearly marked example-only.
- [Partial sample](four-section.partial.sample.v1.json): structure, management and debt unavailable; eligible Competitive Positioning and Industry retained; overall incomplete with explicit warnings.
- [Frozen source bundle](four-section.sample-sources.v1.json): exported verified SavedInputs for independent deterministic replay of both examples. No importer or historical backfill is provided.
- [Equality verification results](four-section.verification.v1.json): five full source-object comparisons for the populated example and two available-component comparisons for the partial example, including source/component hashes and pointers.

Independent final replay reproduced both entire JSON objects exactly, including their hashes:

| Sample | Canonical content hash |
|---|---|
| Populated | `03c99acb58c85ab7134927aa29e1069e653a5eb02ddfbf536e47290b79c9afc0` |
| Partial | `4792b8e2b8ee4763d13030a81480635e63091809f14dfd8427dd43adc1bc4581` |

The populated fixture uses existing offline/scripted specialist paths and genuine recorded upstream validation outcomes. Fixture debt source rows and admitted passages were made internally consistent before validation. Those fixtures are never production fallbacks. Tests additionally preserve zero-drawn facilities, row order, null values, signed reconciling items, guarantees, canonical enum values and nested precision.

## Files added and modified in this milestone

Added:

- `app/schemas/bo_four_section.py`: versioned document schema/constants.
- `app/services/bo/four_section.py`: provenance capture, exact-run loader, pure assembler, strict persistence/reader.
- `tests/four_section_helpers.py`: isolated fictional offline source setup.
- `tests/integration/test_bo_four_section.py`: lossless-copy, partial availability, persistence and adversarial tests.
- The schema, populated/partial samples, source bundle, verification JSON and this report in this documentation directory.

Modified:

- `app/services/bo/reporting.py`: additive source freezes, assembly, artifact and handoff binding.
- `app/services/bo/runner.py`: optional result field only.
- `app/services/bo/workbench.py`: strict read-only artifact kind.
- `app/services/registry/indexer.py`: conditional inventory discovery.

SHA-256 comparison against the pre-Milestone-3 working-tree snapshot confirmed that these are the only four previously existing files changed in this milestone. Milestone 2 prompts, editorial selection, challenger, specialist code, validators and original design documents retain their previous bytes. Git's aggregate working-tree diff also includes earlier uncommitted Milestone 2 changes; those were preserved.

## Validation results

Final focused command (existing sibling virtualenv; no installs):

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q tests/integration/test_bo_four_section.py tests/integration/test_bo_competitive_positioning.py tests/unit/test_artifact_registry.py
```

**87 passed in 28.90s.** Includes the final guard proving detached sample inputs cannot persist into an empty authoritative database.

Broader offline regression run: **641 passed, 2 failed, 2 skipped**, with one existing Starlette/httpx deprecation warning. This run preceded the final detached-persistence test; the final focused run above includes it. Coverage included M3 rebuild, M4 contracts/Validator 8, memo modules, structural overview, audit immutability, Milestone 2, BO validation/registry/coverage/roster/cache, pipeline/governance/downstream/FO/archive/Agent 6 feedback, review workspaces/workflows, CLI and RMS.

The two failures were independently reproduced in an isolated baseline mirror with all four integration files restored to their exact pre-Milestone-3 hashes:

1. `test_bo_m4_dual_specialist.py::test_both_m4_specialists_reach_governed_output_and_synthesis`: expects accepted output despite missing M3; existing governance produces `human_review_required`.
2. `test_bo_m4_dual_specialist.py::test_validators_off_still_drafts_the_full_memo`: expects every validator version to be advisory, while existing Agent 6 enforcement remains mandatory.

Both fail identically before this milestone. Governance and specialist tests were not weakened to force them green. The two skips concern an unavailable local HCA artifact and missing PDF backend. No live HCA run was attempted.

Adversarial coverage includes cross-company/run/snapshot/period/cutoff contamination, corrupt root hashes, invalid producer and validation records, wrong debt assessment/ledger/challenge identity, superseded conclusions, incompatible handoff/stage/file data, repeated freeze, and same-company multiple-run isolation. It also covers independent partial blocks, omission preservation, unchanged legacy reads and immutable approval overlays. Monkeypatched prohibitions verify assembly/read paths do not invoke models, specialist validators or local source readers. `git diff --check` passes.

## Limitations and Milestone 4 readiness

The JSON contract and examples are ready for renderer implementation and independent review. Offline tests demonstrate contract/integrity behavior, not live analytical quality. Structure simulations and source scope limitations remain visible. Unsupported/legacy management contracts and unverified debt results remain unavailable instead of being adapted or fabricated. No automatic historical backfill exists.

The renderer must consume complete objects, preserve canonical enums and all debt rows, hide citations/quotations behind evidence disclosure, and retain visible material limitations. It must obtain current human-review state from existing review infrastructure rather than interpreting the immutable pending snapshot as a current approval decision. Milestone 4 has not started.
