# Contracts and exact source-to-output mappings

Companion to [architecture](architecture.md). All “existing” paths below are relative to inspected commit `34d61e7b3e547228d6766ec4a7e916395821a906`. “Proposed” fields do not exist in application code yet. `MC` below means the **same selected run's** frozen `audit.module_conclusions` (also copied into memo/handoff); it is never a latest-run lookup. `S` denotes the proposed memo's `sections` array.

## 1. Existing Module 1 Agents 1–6

Authoritative roster: `app/services/bo/roster_v3.py`, `V3_SPECS`. The table deliberately retains the actual agent IDs despite misleading historical variable/dimension names.

| Agent/code and actual ID | Current title | Exact owned parameters | Validator identity |
|---|---|---|---|
| 1 / M1S1 / `m1_revenue_quality` | Pricing Power | `pricing_power_assessment`, `revenue_realisation_assessment` | `validator_1` |
| 2 / M1S2 / `m1_customer_stickiness` | Demand Defensiveness | `business_model_classification`, `revenue_recurrence_assessment`, `demand_defensiveness_assessment`, `cyclicality_seasonality_assessment` | `validator_2` |
| 3 / M1S3 / `m1_pricing_power` | Customer Stickiness | `customer_dependence_assessment`, `contract_termination_risk_assessment`, `switching_cost_assessment` | `validator_3` |
| 4 / M1S4 / `m1_operating_model` | Cost Resilience | `workforce_cost_resilience_assessment`, `supplier_dependence_assessment` | `validator_4` |
| 5 / M1S5 / `m1_competitive_durability` | Competitive Positioning | `competitive_position_assessment`, `competitive_pressure_assessment`, `barriers_to_entry_assessment` | `validator_5` |
| 6 / M1A6 / `m1_resilience_integration` | Business Resilience, Risk Interactions & Synthesis | `compound_risk_assessment`, `mitigating_capability_assessment` | `agent6_governance` |

All six ultimately use `BO_NARROW_JSON_SCHEMA` in `app/prompts/bo_prompts.py`:

- Required top-level arrays: `parameters`, `hypotheses`. Optional: `retrieval_requests`, `checklist_responses`, `missing_information`. Objects permit additional properties in this wire schema; that is not permission to invent source fields.
- Each parameter requires `parameter_id`, `value_type`, `status`; optional `value` (string/null), `evidence_ids`, `materiality`, `hypothesis_ids`, `notes`. Ownership and permitted categorical values are separately gated. Raw agent status vocabulary is exactly `ok|provisional|unavailable|not_applicable|requires_review` (`AGENT_PARAMETER_STATUSES` in `app/prompts/agent_schemas.py`); canonical statuses also include application-owned states below.
- Each raw hypothesis requires `hypothesis_id`, `claim`, `claim_type`, `direction`, `disposition`. Optional fields: `confidence`, `materiality`, `credit_mechanism`, `interpretation`, `supporting_evidence_ids`, `contradicting_evidence_ids`, `evidence_quotes`, `quoted_values`, `missing_information`, `display_priority`, `review_required`, `corrects_hypothesis_id`, `parameter_id`, `mitigant`, `evidence_basis`, `fo_handoff`, `transmission_mechanism`, `component_hypothesis_ids`, `interaction_kind`.
- A quote requires `evidence_id`, `quote`; a quoted value requires `parameter_result_id`, numeric `value`, with optional `unit`, `period`, `denominator`. Interpretation fields are `implication`, `magnitude`, `trend`, `watch_trigger` (nullable strings). Mitigant fields are `capability`, `existence`, `effectiveness`, `outcome_evidence_ids`.
- A retrieval request requires `purpose`, `terms`, optionally `hypothesis_id`; a checklist response requires `check_id`, `status`, optionally `hypothesis_ids`, `note`. These are evidence-workflow records, not findings.

The validated **canonical** contract is `HypothesisRecord` in `app/schemas/bo.py`, not the model's raw answer. Required fields are `hypothesis_id`, `analysis_run_id`, `agent_id`, `agent_run_id`, `section`, `claim`, `claim_type`, `direction`, `disposition`, `admissibility`. Defaults/optional fields are:

```text
topic="business"
supporting_evidence_ids=[], contradicting_evidence_ids=[], evidence_quotes=[]
parameter_result_ids=[], quoted_values=[]
confidence="medium", materiality="medium", credit_mechanism=null
interpretation={}, missing_information=[], display_priority="on_demand"
review_required=false, corrects_hypothesis_id=null, parameter_id=null, mitigant=null
component_hypothesis_ids=[], interaction_kind=null, validation_notes=[]
evidence_basis="none", model_stated={}, review_flags=[]
transmission_mechanism=null, fo_handoffs=[], recovery=[]
supersedes_id=null, acceptance_state="accepted"
validator_id=null, validator_version=null, presentation_basis={}, investigation={}
```

Exact enums: `claim_type` = `fact|calculated_fact|management_claim|inference|assumption`; `direction` = `positive|negative|mixed|neutral`; `disposition` = `supported|qualified|rejected|unverified`; `admissibility` = `established|attributed|qualified_narrative|audit_only`; `confidence` = `high|medium|medium_low|low`; `materiality` = `low|medium|high`; `display_priority` = `display|on_demand|suppress`; `acceptance_state` = `accepted|superseded|rejected`. Raw interaction kinds are `compound_risk|mitigating_capability|dependency|unresolved_question|null`.

`HypothesisRecord.usable` checks accepted state and non-audit-only admissibility. `derive_admissibility()` makes rejected/unverified/assumption records audit-only; qualified or inference becomes qualified narrative; management claim becomes attributed; otherwise established. For the new input also require supported/qualified disposition and a successful recorded producer validation; do not trust a hand-built inconsistent record solely because `.usable` is true.

`HypothesisValidator` (`bo/hypotheses.py`, version `bo-hypothesis-validator-2.2.1`) applies evidence/quote/number, remit, sufficiency, classification, mitigant and presentation gates. `runner._on_narrow()` repairs citations, checks the sealed packet and schema, validates hypotheses, gates parameters, promotes validated outputs and persists them with lineage. `validation_audit.py` records validator identity/version/packet hash. Investigation/hybrid paths adapt to the same BO response/canonical records; their intermediate hypotheses are not a replacement output contract.

Agent 6 reads usable validated M1 primaries, not M2–M4; failed v3 primary agents block it. Its validated interaction uses component IDs, an interaction kind and a transmission mechanism. A compound risk needs at least two distinct primary IDs (other kinds at least one); the existing gate does not itself require distinct agents. Invalid components make the interaction unverified; qualified premises constrain certainty and materiality cannot exceed every component. Keep the specialist semantics; do not relabel a single-dimension interaction as cross-dimensional in the memo. Outstanding retrieval requests remain gaps, not support. Pending reconsideration findings are withheld from `_usable()`.

Canonical parameters use `ParameterResult` (`app/schemas/agentic.py`): required `parameter_result_id`, `analysis_run_id`, `parameter_id`, `topic`, `value_type`, `method`, `status`; optional/default `value`, `risk_signal`, `evidence_quality`, `confidence`, `materiality`, `source_fact_ids`, `source_parameter_ids`, `evidence_ids`, `formula_id`, `formula_version`, `agent_id`, `agent_run_id`, `prompt_id`, `model_id`, `input_hash`, `contradictions`, `missing_information`, `notes`, `supersedes_id`, `parent_id`, `rerun_of`, `acceptance_state`. Status = `ok|provisional|unavailable|not_applicable|proposed_new_calculation|requires_review|not_assessed`. LLM origin and deterministic formula origin have different enforced metadata. Never infer an approved conclusion from a categorical parameter alone.

## 2. Existing orchestrator/challenger and proposed contract

Existing orchestrator: ID `business_orchestrator`; prompt `bo_v2_business_orchestrator` (also reused by v3); `BusinessOrchestratorInput` in `services/orchestration/business.py`. Current packet contains accepted business parameters, optional score (BO runner supplies no score), open conflicts, data limitations and an allowlisted extras dictionary. Runner extras include hypotheses, audit-only hypotheses, resilience findings, duplicate groups, contradictions, indicators, coverage, module conclusions, cross-module instruction, feedback and section metadata. `hypothesis_view()` omits some canonical fields, notably transmission mechanism, validator identity, presentation basis and acceptance state. New packet construction must explicitly include these from canonical records; absence in an old projection does not authorize reconstruction.

Existing `BO_ORCHESTRATOR_JSON_SCHEMA` requires `overall_assessment`; optional `strengths`, `weaknesses`, `key_drivers`, `material_risks`, `open_questions`, `unresolved_contradictions`, `merged_duplicates`, `follow_up`. Each `_BO_CLAIM` requires `claim_id`, `category`, `text`; optional `title`, `section`, `claim_type`, `hypothesis_ids`, `parameter_result_ids`, `evidence_ids`, `materiality`, `uncertainty`, `quoted_values`. Current validation checks references, accepted parameters, numeric support, claim-type overstatement, qualifications, score prohibition and duplicate risks/text. It currently allows run-wide numeric context, including M4 validated debt figures; remove that allowance for the narrowed writer.

**Proposed input: `bo-competitive-positioning-input-1.0.0`** (strict named keys; no raw documents or whole module blocks):

| Required field | Type and content |
|---|---|
| `schema_version` | Literal above. |
| `identity` | `{case_id, analysis_run_id, evidence_snapshot_version, evidence_snapshot_hash, as_of_date, evidence_cutoff_timestamp}` copied from selected records; nullable source dates stay null. |
| `policy_version` | `bo-editorial-selection-1.0.0`. |
| `hypotheses` | Canonical usable M1 Agents 1–6 records; retain exact original text, interpretation, Agent 6 mechanism/components, qualifiers and all provenance. |
| `parameters` | Current accepted M1-owned parameters only, with their full `ParameterResult` identity/status. Unavailable values are gaps, not proof. |
| `indicators` | Existing deterministic traces actually referenced by eligible M1 records; no free run-wide M2–M4 numerical pool. |
| `duplicate_groups`, `contradictions` | Existing reconciliation entries projected to M1 IDs; keep relevant counter-evidence and omitted/unusable-side limitations. |
| `coverage`, `data_limitations`, `open_conflicts` | Recorded M1 coverage, gaps and unresolved matters, including Agent 6 feedback gaps. |
| `audit_only_hypotheses` | Labelled M1 exclusions for context only; never a basis for a positive/adverse assertion. |
| `challenge_feedback`, `validation_feedback` | Arrays, empty initially; populated by existing bounded repair/rerun flow. |

Do not add `module_conclusions`, raw source documents, M2–M4 findings, a business score or permission to test new interactions. Attached verified quotation fragments remain usable for provenance checking; they are not a new retrieval corpus.

**Proposed output: `bo-competitive-positioning-output-1.0.0`**: retain the existing orchestrator JSON fields with stricter required semantics, plus selection metadata persisted in the audit, not forced into `TopicConclusion`.

```text
schema_version: literal above
policy_version: bo-editorial-selection-1.0.0
overall_assessment: required supported lead claim (section="executive")
key_drivers: ordered claim[]; material_risks: ordered claim[]
strengths: []; weaknesses: []  # no duplicate headline lists in this workflow
open_questions: string[]; unresolved_contradictions: string[]
merged_duplicates: {kept_hypothesis_id, merged_hypothesis_ids[], reason}[]
follow_up: string[]
selection_decisions: {hypothesis_id, decision, claim_ids[], reason}[]
interaction_basis: {claim_id, agent6_hypothesis_ids[]}[]
```

For minimal compatibility, listed claims retain an existing M1 section code matching a cited lead finding; this is producer provenance only. The assembler places **every** selected claim, including the executive lead, in Competitive Positioning. No new `ConclusionClaim.section` enum is required. Preserve order: overall lead, `key_drivers`, then `material_risks`, with no duplicated claim text. A later revision can add interleaving if needed; it is not necessary for this milestone.

Every claim requires nonempty unique `claim_id`, `category`, `text`, `section`, `claim_type`, `hypothesis_ids`, `parameter_result_ids` (possibly empty), `evidence_ids`, `materiality`, `uncertainty` (nullable), `quoted_values` (possibly empty). Use existing claim/category/number contracts. Preserve exact source-bound figures and qualifiers. Selection decision enum = `selected|merged|omitted`; selected/merged records must resolve to displayed claims; omitted records require a reason and no claim IDs. Every eligible finding appears exactly once in the ledger. Component IDs referenced by an Agent 6 claim count as supporting lineage, not necessarily separately selected findings.

An interaction claim must have `interaction_basis` naming at least one selected usable Agent 6 record; the cited primary component IDs must resolve to that record's validated components. Do not rewrite a mechanism into a stronger one. Non-causal consolidation need not have interaction metadata. Deterministic validation checks identity, scope, references, ledger completeness, duplicate use, quote/parameter support and no official score. Semantic support and material omissions are explicitly reviewed by the challenger.

Persist the validated raw writer output/selection metadata via existing `AgentRunRow.parsed_response` and frozen audit (new versioned `editorial_selection` block). Keep `TopicConclusion` and `ConclusionClaim` typed fields as they are; `build_topic_conclusion()` currently drops `quoted_values`, `merged_duplicates`, `follow_up` and extra metadata, so those must be retained in the frozen audit/new memo evidence instead of assumed to survive in the conclusion. Bind selection metadata to `orchestrator_run_id` and exact conclusion ID.

Existing challenger ID `business_challenge`, prompt `bo_v2_business_challenge`; schema requires `challenges[]`, optional `overall_outcome`, `summary`. A challenge requires `challenge_id`, `issue_type`, `severity`, `reason`; optional exact `target` claim ID, `affected_agent_ids`, `affected_parameter_ids`, `evidence_ids`, `requires_reanalysis`, `requested_rerun_scope`. Severity is `low|medium|high|material`. Preserve `validate_challenger_output()`, deterministic prechecks, `ChallengeLoop`, escalation and `RerunController`; recorded outcome is derived, not accepted from the model. Supply the ledger/unselected M1 hypotheses to the new prompt version and explicitly test unsupported new implications and material omissions (`issue_type=other` can represent an omitted risk without changing the common enum). No new challenger is needed. Assembly equality/completeness checks govern copied M2–M4 material; they do not replace their existing specialist validation.

For an omitted finding with no displayed target claim, the challenger uses `target:null`, includes the omitted hypothesis ID in its reason and names the responsible agent/rerun scope. Never manufacture an unknown target ID to satisfy claim-level targeting.

| Exact accepted M1 conclusion source | Proposed output |
|---|---|
| `audit.conclusions[*]` entry matching handoff `business_topic_conclusion_id` and its `orchestrator_run_id` | `S[2].content.conclusion_id`, `.orchestrator_run_id` |
| Matching entry `.payload.overall_assessment` | `S[2].content.assessment`, unchanged claim object |
| Matching entry `.payload.key_drivers`, `.material_risks` | `S[2].content.key_drivers`, `.material_risks`, unchanged and in source list order |
| Matching entry `.payload.open_questions`, `.unresolved_contradictions`; claim `.uncertainty`; relevant module/coverage/open-question records | `S[2].visible_warnings`, source text retained without adding analytical claims |
| Matching writer's frozen `editorial_selection` and parsed `quoted_values`, `merged_duplicates`, `follow_up` | Competitive Positioning evidence/audit detail, bound to exact conclusion producer; necessary unresolved follow-up also visible |
| Claim hypothesis/evidence/parameter IDs; Agent 6 component/transmission fields | Competitive Positioning Evidence panels via exact-run audit hypothesis/parameter/calculation/source records |

## 3. Exact Module 2 fields and Industry mapping

M2 producer = `m2_industry`, validator = `validator_6`; owned parameters = `regulatory_dependency_assessment`, `external_event_exposure_assessment`. Retrieval addresses structure, cyclicality, regulation, external events, trends and existing versus forecast evidence; a retrieval topic is **not** an output field or proof that analysis exists.

`runner._build_module_conclusions()` produces this exact common module envelope:

```text
module, status, agent_ids, failed_or_missing_agents, unresolved_coverage_checks,
findings, audit_only_hypothesis_ids, missing_information
```

`status` = `complete|incomplete`; `findings` includes usable records projected by `hypothesis_view()`. That exact projection is: `hypothesis_id`, `agent_id`, `section`, `claim`, `claim_type`, `direction`, `disposition`, `admissibility`, `confidence`, `materiality`, `credit_mechanism`, `interpretation`, `supporting_evidence_ids`, `contradicting_evidence_ids`, `evidence_quotes`, `quoted_values`, `missing_information`, `corrects_hypothesis_id`, `mitigant`, `component_hypothesis_ids`, `interaction_kind`, `validation_notes`. It has no dedicated `industry_analysis`, market-size, growth-forecast or industry-rating field.

| Exact source | Proposed output | Rule |
|---|---|---|
| `MC.M2.findings` | `S[3].content.findings` | Copy all usable governed findings unchanged and in order; no materiality threshold or second editorial writer. Check current canonical acceptance/producer validation against audit. |
| Each finding's `claim`, `credit_mechanism`, `interpretation.*` | Industry visible analysis | Render source text verbatim, with attribution and required uncertainty; do not invent section-specific conclusions. |
| `disposition`, `admissibility`, `missing_information`, envelope status/gaps | `S[3].visible_warnings` plus visible finding qualifications | Show partial scope and qualification. |
| Quotes, source/evidence IDs, quoted values, validation notes | Industry Evidence panel | Resolve recorded citations/trace; preserve exact content in JSON. |

## 4. Module 3 contracts and mappings

Active path is `app/services/bo/m3_rebuild`, not retired `bo_m3.py` hypotheses or the separate downstream structural-overview adapter. Handoff = `m3-rebuild-handoff-1.0`, `workflow=m3-rebuild`; fields `module`, `workflow`, `schema_version`, `status`, `agent_ids`, `findings` (empty), `m3_rebuild`, `source_manifest`, `source_run_id`, `missing_information`, `consumption_instruction` (unavailable block instead carries `case_id`). Each `m3_rebuild.structure|management` component is `{status, validation_status, artifact, error}`. Manifest = `m3-rebuild-manifest-1.0`, with case/run, filenames, schema versions, statuses, diagnostics and artifact SHA-256; loader validates hashes, schema/status agreement and path containment. Context validation checks company/management period/cutoff.

Structure input = `corporate_structure_onboarding`, schema `1.0`: `company_name`, `data_status`, `corporate_tree`; tree nodes require `id`, `name`, `role`, boolean `is_guarantor`; each child requires numeric `ownership_percent_from_parent`, optional `record_type`, `children`. No SEC/legal verification is inferred.

Structure artifact = schema `2.0`, type `llm_reproducible_corporate_structure_diagrams`. Contract is checked by `structure.validate_structure()` and geometry rules (not a Pydantic object). Retain the **entire** artifact, including `purpose`, `simulation_disclaimer`, `how_to_use`, `visual_spec`, `companies`, `provenance`, `completion_status`, revision metadata. Exactly one company `C` has `company_display_name`, `simulation_status`, `root_node_id`, `nodes`, `ownership_links`, `plain_text_tree`, `layout_note`, `connector_paths`. Nodes: `id`, `display_name`, `role`, `is_guarantor`, `box`, optional `record_type`; links: `parent_id`, `child_id`, `ownership_percent`. Diagram uses existing `render_svg(artifact)` only; IDs/geometry/labels remain source-defined.

Management artifact supported versions = `m3-management-assessment-1.0|2.0|3.0`, type `senior_management_assessment`; current reviewed path emits 3.0, missing-source path may emit 1.0 partial. Common fields: `company`, `filing_period`, `source{path,sha256,section_ids}`, `roster_date`, `roster_citation_id`, `citations`, `review_window`, `profiles`, `observations`, `overall_assessment`, `coverage`, `rejected_profiles`, `limitations`, `completion_status`. Versions 2/3 add `facts`, `model_assessment`, `validation`; 3.0 extends citation locations/matching and review outcomes.

- Profiles: `name`, `position`, `roster_position`, `appointment_date`, `appointment_precision`, `recency`, `prior_internal_roles`, `succession`, `citation_ids`, `semantic_support_check`; v2/3 permit `tenure`.
- Observations: `observation_id`, `executive`, `rule`, `direction`, `category`, `text`, `citation_ids`; v2/3 also `signal`, `supporting_fact_ids`, `uncertainties`; v3 also `review_outcome`, `review_reason`. Categories = `transition|integration|continuity|information_gap`; directions = `positive|negative|neutral|unavailable`.
- Final overall: `outcome`, `information_gaps`, `policy`, `information_direction`. In v3 `policy` is the surviving reviewed overall wording. **Do not use raw `model_assessment.explanation` as the approved overall.**
- Validation includes `claim_results`, `judgment_results`, `rejected_facts`, `rejected_judgments`, `overall_references_valid`, `validator_7`, `explicit_review_corrections`; original/qualified/unsupported judgments remain distinguishable. Citations include source identity/hash, quote/check and, in v3, canonical location/matching metadata. `contracts.validate_management()` defines the exact nested schema and cross-reference checks; no schema changes proposed.

| Exact source | Proposed output | Initial rendering |
|---|---|---|
| `MC.M3.m3_rebuild.structure.artifact` | `S[0].structure.content` | `render_svg()` at left; disclaimer visible. Whole object copied unchanged. |
| Structure component `status`, `validation_status`, `error`; artifact `simulation_disclaimer`, `provenance` | Structure status/reference wrapper, `S[0].visible_warnings` | Simulation/unverified status and missing input visible; source hashes/detail in Evidence. |
| `MC.M3.m3_rebuild.management.artifact` | `S[1].content` | Entire artifact copied; source-aware rendering below. |
| `.overall_assessment.policy`, `.outcome` | Management lead | Exact final wording; preserve unavailable/qualification. |
| `.observations[*].text`, `.executive`, `.direction`, `.category`, `.uncertainties` | Management analysis | All surviving observations, unchanged; use `management_claims()`/`validate_claims()` for identity checking, retaining richer artifact fields. |
| `.profiles[*]` | Management profile table | Exact names/positions/appointment/recency/succession; no competence inference. |
| `.limitations`, `.coverage`, component error/status | `S[1].visible_warnings` | Coverage and substantive limitations visible, including partial/offline review provenance. |
| `.citations`, `.facts`, `.validation`, source details | Management Evidence panel | Keep citation namespace separate from M1 evidence IDs; rejected facts/judgments do not re-enter the body. |

## 5. Module 4 debt contract and complete table mapping

Debt agent = `module4_debt_structure_specialist`, debt validator = `validator_8_debt_structure`. Strategy agent = `m4_strategy_capital`, validator identity `validator_8` (different from debt validation). Preserve both. `M4DebtResult.to_module_conclusion()` yields version `bo-m4-debt-assessment-1.0` with `agent_id`, `validator_id`, `status`, `validated`, `assessment`, `validator_report`, `validator_issues`, `escalation_id`, `evidence_ids`, `reason`, `model_invoked`, `reconciliation_followup`, `dropped_reconciling_items`.

`assessment` is strict `Module4Output` from `app/schemas/module4.py`:

| Deliverable | Exact fields |
|---|---|
| `deliverable_1` | `extraction_source`, `senior_notes_schedule`, `non_note_obligations_schedule`, `creditor_priority_framework`, `reconciling_items` |
| `deliverable_2` | `extraction_source`, `refinancing_log`, `metrics`, `refinancing_capacity_discipline_verdict` |
| `deliverable_3` | `extraction_source`, `capital_deployment_reconciliation`, `debt_utilisation_matrix`, `debt_utilisation_leverage_verdict` |
| `deliverable_4` | `evidence_synthesis_narrative`, `core_credit_assessment`, `synthesis_matrix`, `executive_credit_summary_box` |

`MC.M4.m4_analysis` (version `bo-m4-analysis-1.0`) retains D1–D3 unchanged and adds strategy findings to D4 via `m4_output.assemble_m4_output()`. Top-level fields include `artifact_kind`, `module`, `contributors`, `requires_human_review`, `forced_outcome`, `note`, deliverables, `strategy_context`, `status`, and missing information when needed. D4's added `strategy_capital_supplement` makes it a superset of strict `Module4Output`; do not validate assembled D4 with the raw specialist schema.

**Designated debt source:** `D1 = MC.M4.m4_analysis.deliverable_1`. Require `MC.M4.m4_debt_status == validated`, debt block `validated == true`, passing recorded report and canonical equality of D1 to `MC.M4.m4_debt_assessment.assessment.deliverable_1`. If the assembled copy is absent but validated assessment exists, a versioned adapter may copy the assessment's D1 with an explicit recorded source path. Conflicting copies fail closed. No fallback to strategy findings, SO output, FO debt estimates or arbitrary files.

Copy D1 whole to `S[0].debt_obligations.content`. The right-side debt table comprises these two labelled schedules; keeping two subtables avoids a lossy new normalized debt schema. No rows are filtered, merged, deduplicated or summed by the assembler.

| Senior-note source column | Visible column |
|---|---|
| `senior_note_series` | Senior note series / description |
| `legal_borrower` | Legal borrower |
| `principal_amount_m` | Principal (US$ million) |
| `coupon_interest_rate` | Coupon / interest rate |
| `maturity_year` | Maturity year |
| `collateral_security_status` | Security status |
| `guarantors_credit_support` | Guarantors & credit support |
| `priority_ranking_tier` | Priority tier |

| Non-note source column | Visible column |
|---|---|
| `obligation_facility` | Obligation / facility |
| `legal_borrower` | Legal borrower |
| `principal_drawn_m` | Principal / drawn (US$ million) |
| `available_facility_limit_m` | Facility limit (US$ million); null shown unavailable, never zero |
| `interest_rate_terms` | Interest terms |
| `maturity` | Maturity |
| `collateral_security_status` | Security status |
| `guarantors_credit_support` | Guarantors / credit support |
| `priority_ranking_tier` | Priority tier |

All schedules retain source order, including zero-drawn facilities. `_m` fields use US$ millions under this contract; do not infer another currency or convert units. Source principal and drawn balances must remain distinct from facility limits.

D1 `creditor_priority_framework` is copied without recalculation: `tier_1_direct_opco_secured_m`, `tier_2_senior_unsecured_guaranteed_m`, `tier_3_unguaranteed_holdco_m`, `consolidated_total_indebtedness_m`, `structural_subordination_drag_ratio`, `prospective_loan_secured_placement`, `prospective_loan_senior_unsecured_placement`. Show amounts/ratio as existing source context; put prospective-loan assumption commentary in module details, not a newly written recommendation. Security enum = `secured|unsecured`; priority enum = `tier_1_direct_opco_secured|tier_2_senior_unsecured_guaranteed|tier_3_unguaranteed_holdco`.

`reconciling_items[*]` = `kind`, `label`, signed `amount_m`, `quote`, `evidence_id`; show label/amount under the table and quotation/reference in Evidence. `extraction_source` = `narrative`, `item_references`, `page_references`, all in Evidence. Preserve whole D1 in JSON, including hidden fields. Empty schedules mean no supplied rows, not established zero debt: show completeness warning and the recorded debt context. Aggregated rows remain explicitly aggregated.

D2–D4, strategy findings, validator checks/follow-up and escalation stay in existing module/audit detail. Removing a separate Refinancing History heading does not remove those artifacts or their material governance warnings.

## 6. Proposed assembled memo envelope

Required top-level fields: `document`, `schema_version`, `design_basis`, `example_only`, `identity`, `governance`, `sources`, `sections`, `evidence_ui`, `content_hash`. `design_basis` records inspected commit and assembler/selection versions. Production `example_only=false`; `identity` carries exact case, analysis, evidence version/hash and conclusion/producer IDs. `content_hash` is a real canonical hash in production; design examples may use null and cannot claim integrity validation.

Each source wrapper carries `artifact_id`, `source_path` (JSON Pointer), `schema_version` where known, `sha256` of source file/stage, and `binding` (`same_run_verified|example_only|unavailable`). Do not mix raw-byte file hashes with canonical-object hashes: production uses the stage recorder's declared canonical hash and M3 manifest's declared byte hash in their respective fields. Source pointers resolve against the recorded source artifact, never a mutable local latest file.

For production, the artifact/stage identifier pins the exact source root. Thus the Industry pointer is `/module_conclusions/M2/findings` into the frozen audit; M3 pointers are `/module_conclusions/M3/m3_rebuild/structure/artifact` and `/module_conclusions/M3/m3_rebuild/management/artifact`; primary M4 pointer is `/module_conclusions/M4/m4_analysis/deliverable_1`. The M1 conclusion pointer uses the actual recorded array index of the matching conclusion entry, not a guessed first/last index. Optional `file_path` is a recorded location, not an identity fallback. Evidence may use an additional source wrapper for the same audit root with a different pointer.

Sections are exactly four and have literal `id`/`title`, `status`, `visible_warnings`. First section has `layout=structure_left_debt_right`, `structure` and `debt_obligations` wrappers (`status`, `source_ref`, `content`). Others have `source_ref` and `content`. Management content is the unchanged artifact; Industry content is `{findings:[exact M2 projections]}`; Competitive Positioning content is `{conclusion_id, orchestrator_run_id, assessment, key_drivers, material_risks}` containing exact validated claims. Nullable contents represent absence. `status` = `complete|partial|unavailable`. All four component statuses are retained separately from memo completeness/review.

`governance` separates `memo_completeness`, `conclusion_status`, `validators_enforced`, `independent_challenge_status`, `human_review_status`, `visible_warnings`. Production statuses come from records, not the model. `evidence_ui` specifies closed panels and which source fields are details; it never strips those fields from canonical data. Evidence text is escaped; safe source links and existing redaction apply. Required visible qualifications override any generic hide-details rule.

Status mapping: an eligible component with recorded complete status is `complete`; surviving eligible content with recorded incomplete/partial scope is `partial`; absent, corrupt, advisory-only or invalid content is `unavailable` and is not copied into the validated memo body. First-section status is complete only when both structure and debt are complete, partial when at least one has eligible content, otherwise unavailable. Management and Industry follow their respective source status. Competitive Positioning requires the exact challenged current conclusion; if available with recorded M1 gaps it is partial. For approved production records, review state is only an overlay from the bound handoff. Design examples may leave `validators_enforced`, identity and `content_hash` null, and must always be `example_only=true` and non-approvable.

The [example](four-section.example.v1.json) is explicitly `example_only` with null run IDs. Its M4 data are copied exactly from the committed illustrative sample, with a real file hash; no M1–M3 outputs are invented and no company analysis is newly generated. It must be rejected as a production/governed input. A later offline acceptance fixture must supply a genuine same-run scripted pipeline package to demonstrate successful M1/Agent 6 selection and all four populated sections.
