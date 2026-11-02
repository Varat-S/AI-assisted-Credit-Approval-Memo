# Reuse, changes, and acceptance criteria

Design only, against `UI_Draft_V1` at `34d61e7`. See [architecture](architecture.md) and [contracts/mappings](contracts-and-mappings.md). These are proposed implementation milestones, not work authorized or performed by Milestone 1.

## Files to reuse unchanged

| File or family | Reuse |
|---|---|
| `app/services/bo/roster_v3.py`, `plans.py`, `ownership.py` | Specialist IDs, owned parameters, remits and evidence retrieval ownership. Do not rename agents as part of memo simplification. |
| `app/schemas/bo.py`, `app/schemas/agentic.py` | `HypothesisRecord`, `ParameterResult`, `ConclusionClaim`, `TopicConclusion`, `AcceptedBusinessOverview` remain the analytical contracts. Use existing extensible `canonical_references` for a new memo reference/hash. |
| `app/services/bo/hypotheses.py`, `validation_audit.py`, `citations.py`, `investigation.py`, `hybrid.py`, `semantic_entailment.py`, `resilience_retrieval.py` | Existing specialist validation, interpretation/evidence handling, lineage and Agent 6 bounded evidence cycle. |
| `app/services/bo/reconcile.py`, `indicators.py`, `retrieval.py` | Reconciliation, deterministic calculations and admitted evidence retrieval. No new calculation needed by the memo. |
| `app/services/bo/m3_rebuild/*` | Typed structure/management artifacts, manifests, geometry/SVG, claim validation and independent Validator 7. Reuse `management_claims()` / `validate_claims()` without discarding richer source fields. |
| `app/schemas/module4.py`, `app/services/modules/module4/*`, `app/services/bo/m4_debt.py`, `m4_output.py` | Both existing Module 4 specialists, Validator 8, reconciliation and unchanged D1 assembly. |
| `app/services/orchestration/conclusions.py`, `promotion.py`, `challenge_loop.py`, `rerun.py` | Typed conclusions, accepted/current provenance, bounded challenge/escalation/remediation. Extra selection metadata must be persisted separately because `build_topic_conclusion()` projects known fields only. |
| `app/services/bo/handoff.py`, `app/services/review/*`, `app/services/audit/log.py` | Human approval, unresolved-challenge acknowledgement, review overlay, immutability and audit. No alternate approval endpoint. |
| `app/services/pipeline/artifacts.py`, `app/core/hashing.py`, `app/services/agents/cache.py` | Frozen hash-chain stage records, canonical hashes, cache identity. Changed prompt/schema/packet/policy identities invalidate old writer reuse. |
| `app/models/orm.py`, `app/services/analysis_jobs.py` | Existing JSON payload storage/lineage and durable job sidecar; no new table/migration or automatic restart. |
| `app/api/templates/workspace_style.html.j2`, `theme.html.j2`, `analysis_nav.html.j2`, `analysis_tabs.html.j2`, `analysis_memo_style.html.j2` | Existing design tokens, memo typography, responsive columns, table scroll, notices, navigation. Add only narrowly scoped details/diagram styles if existing classes do not suffice. |
| `app/services/fo/*`, `app/services/rms/*`, legacy structural overview and financial orchestration | Outside the new BO writer/assembler remit; compatibility consumers remain unchanged. |

## Files to modify, and smallest additions

| File | Proposed bounded change |
|---|---|
| **New** `app/services/bo/four_section.py` | Pure deterministic projection/validation over governed same-run artifacts; lossless designated M2–M4 content, source wrappers, completeness/warnings, no provider or acquisition imports. Keep the new memo contract constants and simple shape checks here initially; a new Pydantic schema file is optional only if implementation needs it. |
| `app/prompts/bo_prompts.py` | Register distinct versioned Competitive Positioning writer/challenger prompts and response schema. Remove all-findings inclusion and new-interaction duties only in the new contract. Retain old prompt versions for replay. Add strict selection/interaction audit metadata. |
| `app/services/orchestration/business.py` | Add the new named input contract/builder or an explicit versioned branch. Filter to M1 by authoritative IDs/ownership, carry canonical interaction fields and referenced traces, reject whole-module/raw-document extras. Do not globally remove legacy inputs used elsewhere. |
| `app/services/bo/runner.py` | Record new workflow/selection contract identity for opted-in v3 runs; build narrowed packet; bypass `include_all_validated_findings()` only for those runs; validate and retain selection metadata; pass unused M1 findings/ledger to challenger. Leave M2–M4 execution/completeness, remediation and handoff module content intact. |
| `app/services/bo/synthesis.py` | Add the stricter M1-scope, ledger/reference/interaction checks. Reuse quote/type/provenance/duplicate gates. Eliminate run-wide M4 numeric allowances for the new writer. Keep old include-all helper for recorded legacy behavior, never invoke it on the new contract. |
| `app/services/agents/registry.py` and prompt/registry metadata in `app/prompts/registry.py` / `app/prompts/bo_prompts.py` | Select new writer/challenger definition/prompt/schema by explicit workflow version; hash the changed semantic contract. Specialist DAG and owned parameters stay unchanged. Exact registry plumbing can follow the existing builder conventions. |
| `app/services/bo/reporting.py` | After finalized challenge outcome, assemble and freeze new memo stage, include selection metadata in audit, add source identity/content-hash reference to the new handoff before review. Retain old memo/audit files and existing all-module handoff contents; no `further_findings` in new projection. |
| `app/services/bo/workbench.py` | Extend hash/identity checks to the new document/version/stage, including exact run/conclusion and handoff reference; keep old strict document-version checks working. Read later review state as an overlay. |
| `app/services/registry/indexer.py` | Add a discoverable `ArtifactType.MEMO` entry for `business_overview_four_section.v1.json` when present, with its actual schema/hash/run provenance. Existing explicit filename discovery does not pick up this new file automatically; no new artifact-type enum is required. |
| `app/services/analysis_workspace.py` | Prefer verified new artifact for new workflow; preserve job/run selection, conclusion equality and exact-current independent-challenge gates. Do not gate all copied M2–M4 content solely on availability of the M1 assessment; render component-specific unavailable states. Legacy runs retain current view. |
| `app/api/templates/analysis_review.html.j2` | Use the new four-section BO partial for new artifacts; retain FO, RMS and status behavior. Put all BO citations/quotes/details into initially closed evidence panels while keeping material limitations visible. |
| **New** `app/api/templates/bo_four_section.html.j2` | Four headings, structure/debt layout, full schedule columns, unchanged management/industry content, selected Competitive Positioning and source-bound evidence panels. No JS framework. |
| `app/api/analysis.py` | Supply the new verified BO projection to Review/PDF without changing unrelated routes. Static PDF evidence policy explicit; no paid generation on GET/export. |
| `app/services/analysis_audit.py`, `app/api/templates/analysis_audit.html.j2` | Show the new selection ledger, omissions, interaction basis and contract version; keep all historical findings, rejected/superseded versions, validator/challenger records, safe links and redaction. Retain the existing five audit sections. |
| `app/services/bo_fo.py` | Opt the intended browser v3 workflow into the recorded contract; rename its writer stage label from “Cross-module synthesis” to “Competitive Positioning writing.” Keep progress math, M4 debt enablement, job storage, FO/RMS and review unchanged. |
| Tests listed below | Add focused offline contract/assembly/UI regressions; update legacy all-findings tests only to scope their assertions to the legacy contract. Do not remove the tests or weaken validation. |

`app/services/bo/completion.py` remains a legacy recorded-specialists path in this minimum design. If it is later opted in, update its input, writer prompt, validation, ledger and challenge together; never label its current cross-module output as the new contract. Existing legacy HTML templates/routes remain replayable and may retain their earlier presentation. The new Review and its PDF must consistently use the new projection; do not globally overwrite `bo-memo-1.0` or change `MEMO_VERSION` in place.

## Existing reporting, storage and historical-run architecture

| Layer | Current behavior to preserve |
|---|---|
| Analytical execution | `BusinessOverviewRunner` routes admitted canonical evidence, persists agent outputs, parameters and hypotheses, reconciles, writes a conclusion, independently challenges it, runs bounded targeted remediation and finalizes status. Per-run model configuration records roster/mode/prompt/config identities. |
| Report production | `BoReportBuilder.finish()` creates memo, audit and `bo-handoff-1.3`; records `bo_memo:{run}` and `bo_audit:{run}` via `StageRecorder`; writes optional JSON/HTML/PDF under `output/bo/{case_id}/{analysis_run_id}/`. `AcceptedBusinessOverviewRow.artifacts` points to those outputs. |
| Audit | `AgentRunRow` retains raw/parsed outputs, input evidence, parents, usage, cache/provenance and validation; hypotheses/parameters/conclusions retain accepted/superseded history. Frozen audit stores module conclusions, validator decisions, source records, orchestrator history, challenge rounds and remediation. Artifact manifest/indexer/explorer describe files and provenance separately; new output should be registered through existing artifact discovery where used. |
| Integrity | `StageArtifact` records canonical payload JSON, SHA-256 and ordered chain hashes; mutation/deletion fails. BO workbench verifies hash chain **and** case/run/snapshot/document identity against handoff and run. A valid hash alone does not establish correct selected-run identity. |
| Human review | `review_handoff()` requires reviewer/reason, enforced validation and a conclusion; unresolved challenges need acknowledgement. Accepted handoff cannot be edited/deleted. Analytical hash excludes review metadata. Later review appears over the frozen report via `with_review()`. |
| Browser jobs | `analysis_jobs.py` SQLite sidecar records explicit job/BO/FO references and worker state, independent of the long BO transaction. History never silently restarts paid work. `analysis_workspace.selected_rows()` and `load_review()` use explicit selected IDs, verify exact frozen conclusion equality, enforce successful independent challenge for that conclusion and avoid latest-run substitution. |
| Audit UI | `analysis_audit.build_audit()` joins only exact-run logs and canonical evidence; displays source versus validated wording and missing records honestly. Redaction and `safe_url()` remain active. |
| Combined views | BO/FO worker uses isolated staging/merge and separate FO identity; FO/RMS have their own review and export behavior. Combined final approval is shown only when an existing finalized snapshot explicitly binds the selected pair. BO selection is not a new overall credit decision. |
| Historical runs | v1/v2/v3 schemas and past prompt policies remain readable. Legacy records lack some identity, validation or job mapping; missing provenance stays unavailable, never reconstructed by live inference or SEC access. No implicit backfill. |

The general `services/reporting/memo.py` / `schemas/credit_memo.py` draft/final-snapshot path and the separate `services/structural_overview` path exist alongside BO-only reporting. They are not the source contracts for the requested M2–M4 join and do not need replacement in this milestone.

## Automatic reinsertion inventory

| Location | Existing effect | New-workflow treatment |
|---|---|---|
| `bo_prompts._ORCHESTRATOR_TEMPLATE` | Requires EVERY usable hypothesis, including low materiality, in own-section drivers/risks. | Use distinct selective-writing prompt. |
| `runner._on_orchestrator()` → `synthesis.include_all_validated_findings()` | Inserts `COV-*` claims for missing usable findings across current narrow agents, with component provenance; duplicate checks exempt inserted IDs. | No call and no insertion exemptions for new contract. Preserve helper/history for legacy. |
| `BoReportBuilder._memo()` → `_further_findings()` | Appends unselected material findings to M1/module sections. | Do not use legacy section builder as new assembler input. |
| `render_memo_html()` → `_m1_sections_with_further_findings()` | Reconstructs “further findings” at render time for older archives. | New renderer never invokes this helper. |
| `services/reporting/templates/bo_memo.html.j2` | Displays further governed findings plus broad M4 D1–D4 and visible evidence. | Keep legacy template for legacy routes; use dedicated four-section partial for new workflow. |
| `analysis_claims.automatic_coverage_ids()` / current Review projection | Removes only positively documented coverage copies, bound to exact conclusion producer. | Preserve for legacy; new writer emits none. Never infer origin from `COV-` prefix alone. |
| `hybrid.execute_investigation_mode()` | Keeps unselected specialist candidates in authoritative specialist output. | Preserve: this governs investigation coverage, not memo editorial selection. |
| Enquiry-planning mandatory coverage repair; Agent 6 evidence feedback | Restores mandatory investigative perspectives/evidence requests. | Preserve: these are specialist governance, not memo reinsertion. |
| `m4_output.assemble_m4_output()` | Supplements D4 with governed strategy findings. | Preserve unchanged; new memo copies D1 only. D4 remains audit/module detail. |

## Milestone 2 — Selective Competitive Positioning writer

Acceptance criteria:

1. A versioned v3 opt-in records the new writer/challenger contract and policy. Existing v1/v2 and old v3 replay remain unchanged; changed writer inputs/schema/prompt cannot hit an old semantic cache entry.
2. Input contains only eligible same-run M1 Agents 1–6 findings, M1 parameters and their referenced deterministic traces; M2–M4 prose/debt numbers and raw documents are rejected. Canonical Agent 6 mechanism/components/qualification are retained.
3. The writer can omit a usable low-relevance finding without its return as a `COV-*` claim or “further finding.” Full source record remains audit-accessible. The ledger covers every eligible finding with a valid selected/merged/omitted decision.
4. Every displayed claim traces to exact current usable findings, source evidence and accepted parameters; no score, new hypothesis, number, stronger attribution or new implication is admitted. An unsupported causal combination of primary findings is rejected/challenged; an existing supported Agent 6 interaction can be selected without repeating its components as separate paragraphs.
5. Independent challenger reviews omissions, qualifications, counter-evidence and Agent 6 support; material omission yields challenge/repair or visible unresolved warning, never automatic insertion. Existing bounded targeted rerun and final-state safeguards pass. Failed primaries still restrict Agent 6; pending Agent 6 feedback never becomes support.
6. Offline fixtures cover positive, adverse, mixed, duplicate, qualified, management-attributed, rejected, unverified, superseded and missing Agent 6 outputs. No paid/provider/SEC calls occur.

Reuse relevant tests: `tests/unit/test_bo_validation.py`, `test_bo_orchestrator_coverage.py`, `test_bo_unbound_numbers.py`, `test_bo_roster_v3.py`, `test_bo_agent6_requests.py`; `tests/integration/test_bo_v3_complete.py`, `test_bo_governance_contract.py`, `test_bo_agent6_feedback.py`. Add focused new-contract tests; keep the include-all helper tests as legacy behavior tests.

## Milestone 3 — Deterministic four-section assembly

Acceptance criteria:

1. All four sections exist with exact titles/order. No separate refinancing section or replacement specialist analysis. Repeated assembly of identical inputs gives identical canonical content/hash.
2. Structure artifact and management artifact are structurally equal to their designated M3 inputs; SVG uses the same validated diagram. Management uses final surviving observations/overall wording, never unsupported/raw model judgments. Simulation, partial roster, coverage and review-source limitations remain visible.
3. D1 is equal to the designated validated M4 source, including every note/non-note row and field, original order, aggregate labels, zero draws, nullable limits, guarantors/security and signed reconciliation. Equality failure or an invalid/missing debt validation blocks that debt component; no FO/SO substitute. A passing bounded validator is not represented as independent proof of population completeness.
4. Industry findings equal usable M2 source projections in order, including mechanism/interpretation and qualifications. No fabricated standalone narrative, statistics or market forecasts.
5. Missing M2/M3/M4, failed M4, partial management, missing citation, mixed run/company/period/snapshot, mismatched artifact hash and exploratory cases fail honestly at the relevant component. All sections remain present. No zeros/neutral conclusions fill gaps; no overall completeness upgrade occurs.
6. New memo stage/hash is frozen with exact identity and referenced by the new handoff's analytical hash; approval cannot silently attach to a different assembled payload. Existing review and audit remain valid. Old archives are neither edited nor regenerated.

Reuse: `tests/integration/test_bo_memo_modules.py`, `test_bo_m4_dual_specialist.py`, `test_bo_downstream_contract.py`, `test_bo_archive_identity.py`; `tests/m3_rebuild/*`; `tests/unit/test_module4_schema.py`, `test_module4_validator8.py`, `test_artifact_registry.py`, `test_audit_immutability.py`. Add direct deep-equality and deterministic assembler tests.

## Milestone 4 — Existing design-system renderer

Acceptance criteria:

1. Desktop BO-only view displays exactly four memo headings, with M3 left and full D1 right in section 1. At narrow widths these stack in reading order without document overflow, while every debt row/column remains accessible via container scrolling.
2. Native evidence panels start closed; no visible inline source numbers, quotes, source list or calculation workings leak outside them. Keyboard activation works and evidence links resolve within the selected run. Material uncertainty, management attribution, simulation and necessary completeness warnings remain visible.
3. UI uses existing theme/typography/table/notice components and escaping/safe SVG/URL/redaction behavior. It never reruns a model, validator or acquisition on page view or evidence expansion.
4. PDF contains the same designated four-section BO content and complete debt schedules, readable across pages; static evidence is explicitly identified as an appendix. FO/RMS and their existing review/score behavior remain unchanged in combined memos. Legacy routes still render their recorded format.
5. Inspect populated, missing/partial, qualified, exploratory, long-table/long-label and mobile fixtures. Confirm expanding Evidence changes visibility only, not approved content or completeness.

Reuse: `tests/integration/test_analysis_review_workspace.py`, `test_analysis_review_financial.py`, `test_analysis_claim_origins.py`, `test_browser_preview.py`, `test_bo_cli_workbench.py`; add four-section HTML assertions and visual inspection. No new browser/runtime dependency is required.

## Milestone 5 — Compatibility, review and offline acceptance

Acceptance criteria:

1. Run a fully scripted same-run v3 fixture through unchanged Agents 1–6 governance, new writer/challenge, assembly, persistence and UI. Confirm a deliberately omitted finding stays out of the memo yet remains in audit; a relevant Agent 6 insight appears with its validated component lineage. Also test no eligible M1 finding: no fake lead, no new conclusion to approve, copied eligible modules still display as partial memo content.
2. Verify exact-job historical selection, multiple runs of the same company, foreign case/snapshot rejection, hash tampering, superseded conclusion, absent challenge and challenge bound to a different conclusion. Reading old records performs no backfill/model call and never substitutes another run's output.
3. Review remains pending until explicit reviewer action; Exploratory approval stays blocked; unresolved material issues require acknowledgement and remain visible. Approving another run or changing source/memo identity cannot approve this one. Frozen artifacts/accepted handoff remain immutable.
4. FO/RMS/structuring handoff readers continue to consume `bo-handoff-1.3` and all-module findings/mitigants/limitations with unchanged meanings. Memo omissions do not delete downstream source content. Combined approval remains bound to the explicit selected BO/FO pair, not inferred from one approved BO.
5. Existing execution/progress/cancellation/history, audit redaction, JSON export integrity, legacy report/PDF and financial review regressions pass. No live inference, SEC acquisition, deployment or dependency additions occur during offline acceptance. Record test commands, fixture identities, failures/limitations and visual-review evidence; do not claim live model quality from scripted results.

Reuse: `tests/integration/test_bo_fo_combined.py`, `test_bo_downstream_contract.py`, `test_analysis_workspace.py`, `test_analysis_execution.py`, `test_execution_ui_refinement.py`, `test_analysis_worker_health.py`, `test_json_export_integrity.py`, `test_review_workflow.py`, `test_final_snapshot_immutability.py`, `test_rms_runner.py`, plus the focused suites above. Broaden testing only where changed interfaces require it.

## Independent design-review checklist

- Are the writer's only analytical sources M1 Agents 1–6, with Agent 6 retaining interaction analysis ownership?
- Does the assembler copy exact designated M2–M4 outputs without adding analysis or silently shrinking tables?
- Can an omitted finding stay omitted from the body while its source, rationale and any material unresolved issue remain reviewable?
- Are source evidence panels distinct from visible qualifications/completeness warnings?
- Are new output/selection versions bound to exact run, conclusion, hashes and review, while legacy archives remain readable?

All five questions should be answerable from this package before implementation. No implementation approval is assumed by writing this specification.
