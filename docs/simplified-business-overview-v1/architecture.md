# Simplified Business Overview — Milestone 1 design

Status: **design for independent review; no implementation**. Version: `simplified-bo-design-1.0.0`, 2 November 2026 (Singapore).

Inspected repository: `Varat-S/kirotesting`, branch `UI_Draft_V1`, commit `34d61e7b3e547228d6766ec4a7e916395821a906`. Code at that commit is authoritative where older reports disagree. Companion deliverables: [contracts and exact mappings](contracts-and-mappings.md), [versioned four-section JSON example](four-section.example.v1.json), [file plan and acceptance criteria](implementation-plan.md).

## Smallest viable architecture

Keep the specialist pipeline, Agent 6, validation, independent challenger, append-only records and human review. Narrow the Business Orchestrator to **editorial selection and supported writing from Module 1 Agents 1–6**. Add one deterministic reporting projection that combines its challenged output with designated Module 2–4 content. Render that projection with the existing UI design system. No new analytical agent, retrieval, calculation engine, model call or database table is needed for assembly.

```text
Agents 1–5 → existing validation → Agent 6 → existing Agent 6 governance
                         ↓                   ↓
                       validated Module 1 findings
                                  ↓
                 Business Orchestrator: select / consolidate / write
                                  ↓
                 synthesis validation → independent challenger
                                  ↓
                     challenged Competitive Positioning
                                  ↓
M3 structure + M3 management + M4 D1 + M2 findings → deterministic assembler
                                  ↓
                    four-section memo → existing UI styling

All stages → existing audit / provenance / review / historical-run records
```

The assembler consumes governed outputs after the existing bounded challenge/remediation cycle. It never runs a model or retries specialists. Partial components can be displayed with their actual status; assembly never upgrades analytical acceptance, completeness or review status.

The four Business Overview sections, always present in this order, are:

1. **Corporate Structure & Debt Obligations** — M3 diagram on the left; both complete M4 D1 obligation schedules on the right, retaining every supplied row and column. Reconciliation/priority context stays with the debt table.
2. **Management** — M3's reviewed management assessment, without rewriting.
3. **Competitive Positioning** — selected, consolidated findings from Module 1 Agents 1–6, including relevant supported Agent 6 interactions.
4. **Industry** — all usable M2 industry findings in their source order, without new synthesis.

This is the Business Overview portion of the credit memo. Existing Financial Overview and RMS sections, scores, decisions, tabs and exports outside this BO portion remain in place. A BO-only presentation has exactly the four sections above. Status banners and evidence controls are not additional memo sections. No separate Refinancing History section is added; M4 D2–D4 remain available in existing audit/module detail.

## Findings that constrain the design

| Current implementation | Design consequence |
|---|---|
| `roster_v3.py` supplies five M1 primaries, M1A6, M2 and M4 strategy. M3 is an independent rebuild workflow; M4 debt is an additional specialist. | Preserve producers and their identities. Do not equate “Agent 6” with Module 2's `validator_6`, or strategy Validator 8 with debt Validator 8. |
| `runner._build_orchestrator()` sends all usable hypotheses and `module_conclusions`, with “Test interactions across M1-M4.” | For the new workflow, pass only M1 findings/parameters and their source-bound numeric context. Remove this cross-module analytical instruction. Modules 2–4 go to the assembler and audit, not the writer. |
| The orchestrator prompt requires EVERY usable finding, including low materiality. `include_all_validated_findings()` inserts omissions. Reporting also supplies `further_findings`. | Version the selection behavior and bypass all these reinsertion paths for the new projection. Preserve original findings in audit. |
| The current Review workspace already excludes positively documented automatic coverage copies. | Reuse its identity and challenge checks, but render the new frozen four-section artifact. Do not rely on UI filtering to fix the writer's remit. |
| M2 has validated hypotheses and parameters, **no dedicated industry narrative field**. | Industry is a deterministic rendering of its usable findings and supported implications. Do not promise unavailable market forecasts or industry prose. |
| M3 structure is submitted/simulated information; management can be partial and has independent Validator 7 review. | Retain simulation/unverified-legal-status notices. Never infer actual borrower, guarantee or cash-access relationships from the diagram. |
| M4 D1 has separate notes and non-note schedules. Existing templates omit guarantor/support columns and some security fields. | A complete debt table needs direct contract fields, not a copy of the current reduced view. |
| Runner defaults to roster v2 and debt disabled; the BO/FO browser worker explicitly uses v3 with debt enabled. | Scope the new workflow to recorded v3 runs. Do not change defaults for unrelated CLI/legacy use. Missing debt remains visibly missing. |

## Orchestrator responsibility and selection policy

The writer may shorten, order, deduplicate and combine already supported statements. It may explain an implication **only when that implication already exists in the validated finding's claim, credit mechanism, interpretation or Agent 6 transmission mechanism**. It may not create hypotheses, introduce new causal links, recalculate numbers, assign a score, reinterpret management competence or assess debt capacity.

Use materiality, company specificity, supported credit implication, non-duplication and decision relevance to select the most important findings. Do not impose an agent quota or a fixed number of paragraphs. Agent 6 findings are eligible on the same basis: meaningful interactions should survive editorial consolidation; not every interaction needs a paragraph. Primary findings may be merged for readability without implying a new causal interaction. A causal cross-dimensional statement must cite a usable Agent 6 finding whose validated components and mechanism support that statement. Merely listing two primary IDs is insufficient.

For every usable M1 finding, record one selection decision: `selected`, `merged` (with a displayed claim reference) or `omitted` (with a specific reason). The ledger is audit metadata, not a specialist finding and not a command to display everything. The independent challenger sees selected **and unselected** findings, duplicate groups, counter-evidence and the ledger. It can challenge omission of a material risk or meaningful mitigating capability. A material unresolved omission yields a visible warning and the existing challenge/review outcome; it never triggers automatic insertion of the omitted narrative. Ordinary low-relevance omissions do not create warnings.

Do not promote `audit_only`, rejected, unverified or superseded findings. Preserve management attribution, qualified wording, uncertainty, material opposing evidence and limitations. Confidence and evidence quality remain separate from credit direction. Keep current source findings and validators unchanged.

The proposed I/O contract in the companion document retains existing `TopicConclusion` fields to minimize downstream changes. Its overall assessment is a lead paragraph **within Competitive Positioning**, not an additional executive section. Existing handoff fields remain usable by downstream consumers; the memo's editorial selection must not erase all-module risk, mitigant, FO-handoff or limitation records from `AcceptedBusinessOverview`.

## Deterministic assembly and evidence presentation

The assembler reads the selected run's immutable audit/module artifacts and its accepted/current challenged conclusion. It copies designated content, adds identity/status/reference wrappers, and records source-to-output pointers and hashes. It does not use legacy `further_findings`, select unrelated historical outputs, generate substitute specialist prose, or silently fill gaps from raw filings.

For the new artifact use `document=business_overview_four_section_memo`, `schema_version=bo-four-section-memo-1.0.0`. Record it under a new stage key `bo_four_section_memo:{analysis_run_id}`, alongside existing `bo_memo:` and `bo_audit:` archives, and optionally write `business_overview_four_section.v1.json` in the same run directory. Keep old files and stage names intact. Use a version-aware reader with the existing hash-chain/identity guards. A missing new artifact on an old run renders the existing recorded view with its legacy label; do not fabricate a new synthesis or rewrite history. Initial rollout need not backfill anything.

Assembly eligibility is component-specific: M1 requires enforced validation and a validated independent challenge bound to the exact current conclusion; M2 requires usable governed findings; M3 requires the typed, manifest-verified components and their real validation status; M4 requires validated debt output and a passing recorded Validator 8 report. Partial M3 components may contribute their surviving reviewed content with warnings. Exploratory/advisory text remains available through existing audit screens and cannot be presented as validated or approved.

When no component is eligible, its block has `content:null` (or an empty findings array), `status:unavailable`, and a visible specific reason. Missing is never represented as a zero debt balance, a neutral management assessment, a complete industry assessment or absence of risk. Overall memo completeness is `complete` only when all designated components and the challenged M1 conclusion are available and their recorded completeness is complete. Otherwise it is `incomplete`; existing human-review status is preserved separately.

Initial UI displays narrative, the diagram, **all debt obligation rows and business columns**, management analysis and relevant industry findings. It hides source citations (including inline source numbers), quotations, calculation workings, detailed validation records and source excerpts inside native `<details><summary>Evidence</summary>…</details>` panels, closed by default. Each panel resolves references to the exact selected run. A numeric business fact or table amount remains visible; its quotation/calculation trace is evidence detail. Attribution and necessary uncertainty remain attached to the visible statement.

Always-visible notices include structure simulation/unverified status, partial/missing components, missing source references, material qualifications/counter-evidence, unresolved material challenge/omission, scope/currency/period uncertainty, and Standard versus Exploratory/review state. Render M2/M3 limitations conservatively as visible until a reviewed rule distinguishes non-material technical detail. The debt table's reconciling item `label`/`amount_m` remain visible; `quote`/`evidence_id` go to Evidence. Full source blocks remain unchanged in JSON.

Collect visible completeness warnings from **all** designated module envelopes and M1 coverage/presentation records, including material unverified findings marked as open questions. Do not restrict warnings to the writer's selected hypotheses (the existing memo builder collects some missing information that way). Describe an unverified matter as an information gap, never as an established risk finding.

Reuse `.memo-paper`, `.memo-columns`, `.memo-table-wrap`, `.memo-table`, `.notice-warning`, theme color variables, typography and existing details patterns. At desktop width, keep structure left/debt right; on narrow screens stack structure before debt and scroll the table within its container. No row truncation, top-N debt filter or closed obligation-table accordion. Reuse safe SVG generation, URL filtering, escaping and audit redaction. No frontend dependency is required. PDF uses the same four-section BO projection, with a readable stacked layout when necessary; static evidence can be an appendix because PDF cannot expand panels. UI evidence remains collapsed.

## Governance, compatibility and limits

Retain sealed evidence packets, admitted evidence routing, per-specialist validators and ownership, hypothesis/parameter gates, quote recovery, semantic entailment/investigation paths, Agent 6's bounded evidence feedback cycle, reconciliation, provenance validation, independent challenge, bounded targeted rerun, escalation and human sign-off. Existing `presentation-policy-1` remains a specialist policy; `display` is a candidate priority, not a requirement to put every finding into this editorial memo. Record a separate versioned selection policy instead of overwriting specialist display decisions.

`synthesis.validate_orchestrator_output()` checks references, numbers and double counting; it does **not prove prose entailment or detect every new hypothesis**. Add source-scope and selection checks, but retain the independent challenger to examine semantic support. Require an explicit Agent 6 interaction reference for causal interactions and preserve that reference in audit. Do not claim that a schema/reference check guarantees faithful writing.

Current reports freeze memo/audit in hash-chained `StageArtifact` rows; agent, hypothesis, parameter and conclusion records retain lineage. `AcceptedBusinessOverview` is hash-checked on read and cannot be changed after acceptance. Human review overlays frozen reports without editing them. The new artifact must be bound to the same run/conclusion and included in that run's reviewed analytical content hash (an additive reference in `canonical_references` for new runs); do not reuse an old approval for changed memo content. Current BO approval is not automatically an overall combined BO/FO/RMS approval.

Key risks:

- Agent IDs and dimension metadata are not intuitive: M1S1's ID is `m1_revenue_quality` but its title/remit is Pricing Power; M1S2 and M1S3 labels likewise differ from older fixtures. Bind by the current roster and owned parameters, never a guessed number/title mapping.
- The checkout has no executed `output/bo` archive. Committed M4 examples are illustrative fixtures, not a real run. Contract inspection proves available shapes, not actual company completeness or live-provider quality.
- M2 may be company-disclosure-centric and sparse. Rendering existing findings cannot create a comprehensive industry report.
- M3 supports management schemas 1.0/2.0/3.0; absent historical Validator 7 records must read “not recorded.” Do not relabel old bounded continuity observations as newer reviewed judgment text.
- M4's schema permits empty schedules, aggregates and non-nullable numerical assumptions. A passing Validator 8 checks six bounded properties, not completeness of every debt instrument or all historical analysis. Preserve aggregate row labels and source scope; never split aggregate tranches, invent unknown coupons or call a zero-drawn facility “no obligation.”
- The M4 sample README says five validator checks; current code has six, including reconciling-item support. Current code wins.
- M4 debt evidence is currently recorded at the assessment level, not per obligation row. Panels must disclose that granularity; do not invent row citations. Some debt text may embed citation language, so hiding citations needs a source-aware display rule, not destructive regex changes to canonical text.
- Removing global M2–M4 context from the writer is a deliberate analytical-scope change. Keep all-module governance and downstream module handoff content; verify RMS/FO/structuring compatibility instead of silently shrinking their records.
- Legacy `completion.py` has a separate M1–M4 writer path. Keep it explicitly legacy unless deliberately opted into this new contract; it must not emit the new schema while retaining cross-module analytical instructions.

## Milestone 1 verification and review boundary

This package documents source contracts, proposed interfaces, exact mappings, file changes and Milestones 2–5 acceptance criteria. The JSON example intentionally shows unavailable M1–M3 and copies only the existing illustrative M4 D1; it is a design artifact with no run identity, not a governed analysis. Its warning prevents inference that these samples form a historical run. It demonstrates lossless debt-table shape and honest missing data without creating specialist analysis.

Only documentation/example files are added. Verification is limited to JSON parsing, exact equality with the cited committed D1 sample, source hash/path checks, four-section order and a clean application-code diff. No application tests, live/paid inference, SEC acquisition, deployment, dependency installation, commits, pushes or merges are needed for this design milestone. Implementation starts only on subsequent instruction.
