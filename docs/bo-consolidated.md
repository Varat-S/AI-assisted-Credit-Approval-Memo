# Consolidated Business Overview v1

Baseline: UI_Draft_V1, fbf08aa7ded540aed58acdd3bc47c21389d00949; clean working tree.
No AGENTS.md found in the checkout or workspace parent. Read `.kiro/steering/credit-memo-principles.md`.

## Discovery and ownership

The production UI review is `analysis_review.html.j2` via `analysis_workspace.load_review`,
not `draft_review.html.j2` (the latter belongs to the older case review workflow).
`bo_memo.html.j2` serves historical standalone memo exports. Both new review and standalone
memo exports use the same consolidated body; Financial Overview is unchanged.

`_BoRun._build_module_conclusions` owns the exact-run M1–M4 outputs. Module 1 has five
primary specialists plus resilience integration; Module 2 has one industry specialist;
Module 3 runs a separate corporate structure/management workflow; Module 4 combines
strategy findings with Validator-8-governed debt deliverables.

## Design

New UI BO executions explicitly enable `consolidated=True` on the existing runner.
Direct CLI and legacy callers retain their prior prompt, schema, coverage and reporting
behaviour. A new prompt name `bo_competitive_consolidated_v1` fixes policy and schema;
PromptRegistry records its version/hash. No specialist prompt changes.

Competitive selection is owned by the LLM. Strict schema, existing synthesis validators,
new deterministic disposition/distinctness gates and the existing independent challenger
validate it. A lossless claim adapter feeds existing conclusion/challenge contracts; the
original full selection response is frozen separately in the audit archive.
No automatic coverage, qualification rewriting or further-findings fallback is used by
this new renderer. Semantic distinctness and analytical defensibility also require the
independent challenger: deterministic string/group checks alone cannot prove them.

A shortfall keeps supported points and records gaps. One selection repair over the already
admitted findings is permitted when the existing remediation setting allows; an invalid
repair retains the previous supported synthesis. Existing retrieval/coverage follow-ups
and challenger-targeted specialist remediation remain bounded and independent. No new
external acquisition is introduced. No adequate recorded evidence means incomplete,
human_review_required; no filler or inferred successful specialist review.

The assembler has no model dependency. It reads hash-chain-verified frozen memo/audit
archives, verifies handoff, run and snapshot identity through existing integrity guards,
and records `bo_consolidated:<run_id>` via StageRecorder. Loading reassembles and compares
against immutable sources, detecting changed copies, source hashes and identities.
Existing source archives retain their schemas, preserving approval and historical loader
contracts without fabricated assessments. The new JSON export is
`consolidated_business_overview.json`; legacy `business_overview.json` remains compatible.

## Source-field mapping (paths within the exact-run bo_memo archive)

| Section | Designated source |
| --- | --- |
| Corporate Structure & Debt Obligations | `module_conclusions.M3.m3_rebuild.structure.artifact` and complete `module_conclusions.M4.m4_analysis.deliverable_1` |
| Management | `module_conclusions.M3.m3_rebuild.management.artifact` |
| Competitive Position | `bo_audit:<run>.competitive_selection`, linked to the existing independently challenged conclusion |
| Refinancing History | Complete `module_conclusions.M4.m4_analysis.deliverable_2` and existing `deliverable_4` conclusion |
| Industry | Complete ordered `module_conclusions.M2.findings` |

Copies are lossless JSON structures: no numeric formatting/rounding, deduplication,
selection or reordering of arrays. Each item stores source stage, field path, SHA-256
content hash and origin. Copy hashes and full content are compared on every load.
Module completeness labels and limitations accompany copies. Execution diagnostics and
all specialist histories remain in the source audit rather than being appended to memo.

**Architecture limitation:** Module 2 has no standalone designated narrative/table report
field in this roster. The existing governed output consists of the ordered findings,
including interpretation, figures, quotes and qualifications. These are copied in full;
no replacement industry narrative is generated. The missing standalone report is explicitly labelled incomplete even when industry findings are available. Missing fields are explicit. Module 4's
existing refinancing conclusion is its complete D4 (including existing strategy supplement);
there is no separately stored refinancing-only conclusion. All D2 transactions and all D1
debt facilities are retained. No new conclusion is written. Module 3 has a structured
assessment rather than one prose field; its full artifact is preserved.

## Governance and compatibility

A well-formed schema is never approval. Frozen validation/challenge, execution mode and
pending review statuses are preserved; current human decisions are overlaid read-only
using existing reviewed_memo. Existing acceptance/rejection/finalization controls remain
unchanged. Exploratory output is labelled advisory and incomplete. Historical runs without
a consolidated stage continue through historical renderers; no backfill or new inference.
No database schema migration, dependency, financial calculation or FO template changes.

## Verification

See the accompanying implementation report for executed checks and remaining limitations.
