# Milestone 2 — Selective Business Orchestrator implementation

Completed locally on `UI_Draft_V1`, based on commit `34d61e7b3e547228d6766ec4a7e916395821a906`, 2 November 2026 (Singapore). **Milestone 2 only. No commit, push or merge.**

The Business Orchestrator can now opt into selective Competitive Positioning writing from canonical validated Module 1 Agents 1–6 findings. Selection, merging, omissions, Agent 6 interaction support and independent editorial review are recorded through the existing run/audit/conclusion/handoff infrastructure. Legacy execution remains the default.

## Versioned opt-in

Use the existing runner API with an explicit contract:

```python
from app.prompts.competitive_positioning import OUTPUT_VERSION
from app.services.bo.runner import BusinessOverviewRunner

runner = BusinessOverviewRunner(
    session,
    backend=backend,
    bo_roster="v3",
    business_orchestrator_contract=OUTPUT_VERSION,
    data_root=data_root,
    output_root=output_root,
)
```

The unchanged `run_prepared()` or `run_case()` entry points then run the workflow. This snippet is configuration guidance, not an instruction to call a live backend. Tests and the delivered example use `ScriptedBoBackend` exclusively.

The exact implemented versions are:

- Input: `bo-competitive-positioning-input-1.0.0`.
- Output: `bo-competitive-positioning-output-1.0.0`.
- Selection policy: `bo-editorial-selection-1.0.0`.
- Separate writer/challenger prompt names: `bo_competitive_positioning_writer_1_0_0` and `bo_competitive_positioning_challenger_1_0_0`.

The opt-in rejects non-v3 rosters and unknown contract versions. Existing browser/CLI defaults and legacy recorded-specialists completion are unchanged. No UI toggle, four-section memo contract or assembler is introduced.

## Implemented behavior

**Input boundary.** The builder takes canonical `HypothesisRecord` and `ParameterResult` objects. Eligibility checks current producer/run, accepted state, supported/qualified disposition, admissibility, actual roster section, validator identity and recorded validator version. Identity has a closed set of case/run/snapshot/hash/date fields. Module 2/4 findings and parameters are outside the writer packet; Module 3 artifacts and whole-module blocks are not accepted inputs. Only deterministic traces referenced by eligible M1 findings are exposed. Trace values must match their current accepted same-run results. Canonical Agent 6 mechanisms, components, materiality, quotations, counterevidence references, qualifications and gaps are retained.

**Selection and writing.** The new prompt selects by economic materiality and credit relevance without a finding or specialist quota. It permits consolidation and clear writing using existing claims, mechanisms and interpretations; it forbids replacement analysis, new hypotheses, new numerical claims, ratings and new causal relationships. `overall_assessment`, ordered drivers and risks remain compatible with `TopicConclusion`/`ConclusionClaim`. `strengths`/`weaknesses` are empty in this contract to avoid duplicate headline lists.

Every eligible finding has exactly one `selected`, `merged` or `omitted` decision. Selection/merge claim references and reasons are checked; omission cannot covertly appear as a separately presented finding. Primary component references may remain as Agent 6 lineage without forcing separate primary paragraphs. Duplicate-merge metadata must agree with the ledger. A causal interaction must identify eligible Agent 6 support and include its exact validated component IDs and mechanism. Merely consolidating two primary findings is no longer labelled a compound business risk in the opted-in memo/handoff.

**Deterministic validation.** The new gate reuses existing synthesis/provenance/double-counting validation and adds closed output shape, M1 scope, source-bound evidence/parameter/figure checks, qualifications, attribution, ledger consistency and interaction-reference checks. A model-supplied `quoted_values` entry cannot license an invented number: it must match its cited sources, including units, period and denominator. Unrelated run-wide M4 values are not available to this gate. Invalid new-contract answers are retained as rejected attempts; no automatic claim drop, coverage insertion or semantic rewrite makes them pass. The existing single writer validation-repair attempt is reused.

**Independent challenge.** The challenger receives relied-on, unused and explicitly omitted canonical findings, the complete ledger, source mechanisms, counterevidence references, scoped traces and limitations. Its versioned response adds an `editorial_review` record naming exactly which eligible/omitted hypotheses and interaction claims were examined, with explicit economic-support and material-omission review. Incomplete review cannot count as a successful independent challenge. Unsupported implications and omitted material exposures remain challengeable through the existing severity, escalation and bounded remediation path. Omission challenges with no displayed claim use `target:null`, identify the finding in the reason and name a responsible rerun scope. Modules 2–4 are not requested as an editorial fix.

**Audit and downstream preservation.** Original raw model responses and decoded responses remain in `AgentRunRow`; one ordinary typed conclusion is persisted, with no second independently editable analytical conclusion. Frozen audit records include each editorial attempt, final ledger, quoted values, merge/follow-up metadata, Agent 6 references, exact producer/conclusion binding and challenger review. The final ledger's canonical hash is included in the existing handoff's `canonical_references`, hence in its analytical content hash. Archive readers verify the workflow, ledger hash and conclusion/producer binding in addition to existing hash-chain/case/run/snapshot checks.

All governed findings remain in module conclusions and audit. The opted-in handoff retains every usable finding ID and exact source findings needed by downstream strength/vulnerability/compound-risk lists. These are marked `source_finding_only`, use reserved `source:` IDs, and do not enter writer/memo claim lists. This is necessary because RMS directly consumes `operational_vulnerabilities`; keeping data only in an audit sidecar would have silently removed an omitted exposure from that consumer. Existing mitigants, FO handoffs, module content, limitations and human-review rules remain intact.

**No reinsertion.** `include_all_validated_findings()` is bypassed only for the explicit opt-in. M1 `further_findings` are empty for that workflow, and the legacy render-time fallback cannot reconstruct them. Legacy runs retain their original all-findings behavior. Existing report schemas/routes continue to work; only additive contract provenance and the required omission suppression are added to the current report path. The new four-section memo and renderer remain future work.

## Concrete sample and omission proof

[competitive-positioning.sample.v1.json](competitive-positioning.sample.v1.json) is exported from an actual isolated, in-memory offline run of fictional Northfield Health Systems. It contains the original scripted model response, decoded validated writer output, typed conclusion, all seven selection decisions, Agent 6 interaction references, the bound independent challenge results, source records from the hash-verified frozen audit, and handoff preservation evidence.

The displayed narrative is:

> Managed-care contracts set negotiated rates and can be terminated on notice.
>
> Qualification: Contract terms do not guarantee patient volumes; renewal outcomes are not established.
>
> Multi-year managed-care agreements set negotiated rates.
>
> Competition for scarce clinical staff can raise costs and constrain service capacity.
>
> Qualification: Qualified interaction: competitor staffing data are unavailable.

The ledger selects primary findings `M1S1-H001` and `M1S3-H001`, merges `M1S1-H002` into the contract paragraph, and selects `M1A6-H001` with `M1S4-H001`/`M1S5-H001` as component lineage. It deliberately omits `M1S2-H001` (“Admissions were stable during the year.”) from the narrative. That exact source remains in the frozen audit and handoff's accepted-finding IDs, and appears in the challenger's reviewed omissions. No `COV-*` claim is inserted. The sample's `omission_proof` records these checks explicitly.

The independent challenge is `validated`/`accepted`. The overall BO remains `human_review_required` with human review pending because the fixture intentionally supplies no M3 inputs. Successful M1 writing does not upgrade all-module completeness or approve anything. Both writer and challenger are scripted simulations; this example proves infrastructure behavior, not live model analytical quality. Its run IDs belong to a disposable fixture, not production history. The saved audit hash identifies the exported source run; the complete temporary database is not distributed.

To regenerate the sample with installed dependencies, from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python - <<'PY'
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from app.core.config import Settings, get_settings
Settings.model_config['env_file'] = None
get_settings.cache_clear()
from app.models.base import create_engine_and_session, init_db
from tests.competitive_positioning_helpers import run, sample_packet
engine, factory = create_engine_and_session('sqlite://')
init_db(engine)
with factory() as session, TemporaryDirectory(prefix='bo_cp_m2_') as temp:
    result, backend = run(session, Path(temp))
    sample = sample_packet(session, result, backend)
    Path('docs/simplified-business-overview-v1/competitive-positioning.sample.v1.json').write_text(
        json.dumps(sample, ensure_ascii=False, indent=2) + '\n')
engine.dispose()
PY
```

IDs, timestamps and hashes vary between isolated executions; contract behavior and omission invariants are reproducible. An existing sibling Python environment was reused read-only for this task; no dependencies were installed.

## Files changed

| File | Change |
|---|---|
| `app/prompts/competitive_positioning.py` — new | Versioned writer/challenger prompts and output/review schemas. |
| `app/services/bo/competitive_positioning.py` — new | Canonical input builder, scoped numerical context, editorial gates, selection/review audit metadata. |
| `app/services/agents/registry.py` | Explicit v3 contract opt-in, M1 writer dependencies and distinct writer/challenger semantic definitions; specialist definitions unchanged. |
| `app/services/bo/runner.py` | New input/task routing, validation, ledger persistence, independent omission review and existing bounded repair/remediation integration. |
| `app/services/bo/reporting.py` | Freeze selection metadata, suppress opted-in M1 reinsertion, bind handoff hash, preserve source findings for downstream readers and distinguish supported Agent 6 interactions from ordinary merges. |
| `app/services/bo/workbench.py` | Verify ledger/workflow/conclusion/producer identity against the selected handoff and frozen audit. |
| `tests/competitive_positioning_helpers.py` — new | Fictional scripted fixtures and reproducible sample export from recorded outputs. |
| `tests/unit/test_bo_competitive_positioning.py` — new | Source eligibility, numbers, ledger, qualification, interaction, review and cache/legacy boundaries. |
| `tests/integration/test_bo_competitive_positioning.py` — new | Full-run selection, audit/omission proofs, retained RMS exposures, challenge/repair bounds, archive integrity, exploratory safeguards, failures and deterministic trace flow. |
| `docs/simplified-business-overview-v1/competitive-positioning.sample.v1.json` — new | Concrete exported offline output and proof package. |
| This report — new | Implementation, reproduction, verification and limitations. |

The approved Milestone 1 files are preserved. Agents 1–6 prompts, retrieval, validators, roster remits and specialist source code were not changed. The new policy is isolated in dedicated files rather than changing the shared legacy input builder or specialist/synthesis validators. No ORM/schema migration, database table, dependency or frontend file was added.

## Offline verification

Final regression run: **376 passed, 1 skipped, 1 warning**, 106.70 seconds. This includes **54 new focused cases**. The skip is an existing Review/PDF test because no PDF backend is installed. The warning is the environment's existing Starlette/httpx deprecation; no dependency change was made to address it.

```bash
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q \
  tests/unit/test_bo_competitive_positioning.py \
  tests/integration/test_bo_competitive_positioning.py \
  tests/unit/test_bo_validation.py tests/unit/test_bo_unbound_numbers.py \
  tests/unit/test_bo_registry.py tests/unit/test_bo_roster_v3.py \
  tests/unit/test_bo_orchestrator_coverage.py \
  tests/unit/test_agent_cache.py tests/unit/test_agent_registry.py \
  tests/integration/test_bo_v3_complete.py tests/integration/test_bo_pipeline.py \
  tests/integration/test_bo_governance_contract.py \
  tests/integration/test_bo_downstream_contract.py \
  tests/integration/test_bo_fo_combined.py tests/integration/test_bo_archive_identity.py \
  tests/integration/test_bo_agent6_feedback.py \
  tests/integration/test_analysis_review_workspace.py \
  tests/integration/test_analysis_review_financial.py \
  tests/integration/test_bo_cli_workbench.py \
  tests/unit/test_human_review_workflow.py tests/integration/test_review_workflow.py \
  tests/integration/test_rms_runner.py
```

Coverage includes selected/merged/omitted primary findings; a qualified supported Agent 6 interaction and exact components; rejected/unverified/superseded/wrong-producer inputs; an invented causal combination; independently challenged unsupported economic wording; source/evidence/parameter mismatch; invented or relabelled figures; a real deterministic trace through the full scripted pipeline; malformed/inconsistent ledgers; incomplete independent review; material omission with only one bounded writer rerun; no eligible input; failed primaries still blocking Agent 6; failed M2 staying outside the writer; raw/validated/frozen record preservation; unchanged specialist hashes and distinct writer cache identities; same-run provenance, tampering/binding rejection, exploratory approval rejection, legacy reports and downstream RMS/FO compatibility.

`git diff --check` passed. The branch and base HEAD remain unchanged. No live/paid inference, SEC acquisition, deployment, dependency installation, commits, pushes or merges were performed. Tests use supplied local evidence and fake/scripted responses; the test suite blocks live SEC transport.

## Limits and stop boundary

- Reference, number and selection checks do not prove arbitrary prose entailment. The causal-language precheck is conservative and can require clearer wording; independent challenge and human review remain responsible for semantic support and material omissions. Scripted results cannot establish live writer/reviewer performance or faithfulness on arbitrary filings.
- The input carries canonical verified quote fragments and counterevidence references; it does not acquire new evidence or reconstruct missing quotations. Information gaps remain limitations.
- New-contract structural/source checks remain enforced even in an Exploratory opt-in. Exploratory analyses remain ungoverned, require human review and cannot be approved under existing rules.
- The default browser/CLI experience remains legacy until explicitly configured for the new runner contract. Existing HTML retains its old layout; the delivered new narrative contract is not yet the four-section UI.
- M2–M4 specialists and their all-module completeness/governance continue to run as before, but their analysis is excluded from the new writer. No four-section deterministic assembler, new memo artifact/schema, UI redesign, citation-disclosure change or new Modules 2–4 integration was implemented.

**Stopped after Milestone 2. Milestone 3 has not started.**
