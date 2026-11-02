# Milestone 3 independent verification

**Final verdict: READY FOR MILESTONE 4.** All five independent proof tests passed against fresh persisted offline runs: **5 passed in 4.49s**. This verdict covers the requested assembler verification; it does not begin Milestone 4 or approve any company credit analysis.

Only the verification test and this report/evidence were updated. Application code, agents, orchestrator, assembler, specialist validation, governance and UI remain unchanged. No live model/API calls, SEC acquisition, dependencies, deployment, commits, pushes or merges were performed.

## Corrected verification criterion

The earlier Proof 2 failure concerned cross-run equality of the whole finalized conclusion, including generated identities and an existing governance escalation. It did not establish assembler corruption. This report supersedes the earlier NOT READY verdict under the user's explicitly corrected criterion.

Within each selected run, the full copied source objects still require recursive deep equality **and identical canonical JSON**, with no fields removed. Source hashing, frozen-chain verification, producer validation, exact conclusion/challenge binding and strict-reader checks remain intact.

Across the otherwise equivalent full and missing-Industry runs, the verification test now explicitly checks:

- Structure business data (`companies`) is unchanged; complete structure is also copied exactly from its own run's source, including packet provenance.
- The complete Module 4 D1 object is unchanged.
- The complete management object is unchanged except its generated Validator 7 run ID; each such ID must resolve to that run's recorded Validator 7 producer.
- Competitive Positioning is unchanged after excluding only `analysis_run_id`, `orchestrator_run_id` and `challenge_status` from the **cross-run comparison**. Both IDs must equal the selected run's actual records. Challenge status is asserted as `clean` for the populated baseline and `escalated` for missing Industry. All other payload fields, including every substantive claim, qualification and evidence reference, remain equal.
- Missing Industry retains recorded `human_review_required`, `escalated` and human review `pending`. No governance value is rewritten to manufacture equality or approval.

The comparison works on detached test copies only. Persisted artifacts are never normalized, edited or re-signed in Proof 2.

## Method and actual execution

The independently constructed fixtures instantiate `BusinessOverviewRunner` directly using existing fictional Northfield evidence, extractor/reviewer fixtures and scripted upstream outputs. They do not import illustrative memo JSON, mock assembly or patch application logic. Only the missing-Industry producer response changes in Proof 2: empty parameters/hypotheses plus an explicit missing-information reason.

Actual deterministic validators, promotion, independent challenge, source/provenance capture, StageRecorder hash chains and handoff bindings execute in isolated SQLite databases. The tests use the implemented `load_saved_inputs()`, `assemble()`, `persist()` and `bo_artifact(..., kind='four_section')`. Reporting first freezes each real run's artifact; the explicit persist calls independently recheck authoritative records and idempotency. The strict reader verifies persisted artifacts, not loose documentation samples.

Executed from the repository root with the existing sibling virtualenv:

```sh
BO_INDEPENDENT_PROOFS=/private/tmp/bo-independent-proofs-corrected PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -x -vv --tb=short tests/integration/test_bo_four_section_independent.py
```

| Executed test in `tests/integration/test_bo_four_section_independent.py` | Result |
|---|---|
| `test_independent_proof1_lossless_persisted_roundtrip` | PASS |
| `test_independent_proof2_missing_industry_producer_persists` | PASS |
| `test_independent_proof3a_same_company_foreign_component` | PASS |
| `test_independent_proof3b_root_chain_tamper` | PASS |
| `test_independent_proof3c_persistence_reloads_authority` | PASS |

**5 passed in 4.49s; no failures or skips.** No application changes were needed. Full captured source/component hashes, identities, statuses and adversarial errors are in [the evidence JSON](milestone-3-independent-verification.evidence.json).

## Proof 1 — Lossless preservation: PASS

Populated run identity:

```text
case: NFH_BO
analysis_run_id: ar_cc15842c33194156
company: Northfield Health Systems
snapshot_version: 1
as_of_date: 2025-12-31
cutoff: 2026-03-01T00:00:00+00:00
conclusion_id: tc_6de7a313ca2c4545
orchestrator_run_id: 0eaceaed-4a0e-440f-a6e8-080dac4291c7
```

Original pointers resolve into verified StageArtifact `bo_audit:ar_cc15842c33194156`. Output pointers resolve into the assembled memo and its strict-read persisted copy.

| Original source JSON pointer | Assembled JSON pointer | Deep equality before / after persistence |
|---|---|---|
| `/module_conclusions/M3/m3_rebuild/structure/artifact` | `/sections/0/structure/content` | PASS / PASS |
| `/module_conclusions/M3/m3_rebuild/management/artifact` | `/sections/1/content` | PASS / PASS |
| `/module_conclusions/M4/m4_analysis/deliverable_1` | `/sections/0/debt_obligations/content` | PASS / PASS |
| `/conclusions/0/payload` | `/sections/2/content` | PASS / PASS |
| `/orchestrator/editorial_selection` | `/sections/2/editorial_selection` | PASS / PASS |
| `/module_conclusions/M2/findings` | `/sections/3/content/findings` | PASS / PASS |

The source conclusion index is located by the exact handoff conclusion ID. The copied whole conclusion also equals the current TopicConclusion payload. Final independent challenge, editorial ledger, conclusion and orchestrator IDs agree; the ledger hash matches the exact-run handoff. Every emitted source reference resolves to the selected audit stage, its recorded SHA and matching component content hash.

| Copied object | Source hash = assembled object hash |
|---|---|
| `/sections/0/structure/content` | `dd1a2f0df24c2c365eb5680b85483e6a8987923bed4308a665dadec299400e6d` |
| `/sections/1/content` | `1c3abcc710af209b3007218bdfc77d191e17129dd6474c927fb6145b164ccefc` |
| `/sections/0/debt_obligations/content` | `6854da9c5843ad87a99faf51e0209c864b66e677af4888f7b94106ccd13c3a40` |
| `/sections/2/content` | `5220fe043811cab8ee3883a3a478f559e43e37cfe4f3ebf0b8af59b9c1d87043` |
| `/sections/2/editorial_selection` | `8a6d7f920dea7dffa40006fb0da9b53e3975c9ff91015b409b02a01d637d04be` |
| `/sections/3/content/findings` | `ee0279d50547d8f1c12f1ff876eda31cb17d96050ae8660f0e9051d9d6c58ae7` |

| Root/output record | Hash |
|---|---|
| Frozen audit stage | `eb806fcfde27e5d46ebd513e3f6e6c671c3fa38aeba98555a6b24fe167999386` |
| Canonical snapshot | `0deddce06532bf20294d4092d89a78da034da2e434395c049335da2c5c76188b` |
| Frozen provenance stage | `c2d4dd74321142d17fb6d05bcf42c4c8749589dbf84fb1a6899afebbde960845` |
| Memo analytical content | `4714dbd611e2b7788cbad74657bde0cf5faaebcecedd5fb024652da35bdd5e1b` |
| Frozen memo StageArtifact | `21a4220b9399d17b3bc84a03aec0ac000b25e6254868baae110037e421e069c0` |

Memo content and whole-stage hashes intentionally differ: the content hash excludes its own field; the stage SHA covers the entire serialized memo.

Additional assertions verified six senior-note rows, four non-note rows, zero-drawn facilities, a null facility limit, a signed negative reconciling item and guarantee/security/priority fields on every debt row. Whole D1 equality includes all rows, creditor-priority framework, nested values, source precision and original ordering. Full management/structure equality includes qualifications, limitations and simulation/provenance metadata. Explicit repeated persistence returned the identical stage; the output file, assembled object and strict-reader result were identical.

## Proof 2 — Partial availability: PASS

| Observation | Populated baseline | Missing Industry |
|---|---|---|
| Analysis run ID | `ar_4bf81b6a90294cfa` | `ar_c85e6e9f1e0e441a` |
| Snapshot hash | `0deddce06532bf20294d4092d89a78da034da2e434395c049335da2c5c76188b` | `0deddce06532bf20294d4092d89a78da034da2e434395c049335da2c5c76188b` |
| Section statuses | complete / complete / complete / complete | complete / complete / complete / unavailable |
| Overall memo completeness | complete | incomplete |
| Conclusion status | accepted | human_review_required |
| Exact source conclusion challenge status | clean | escalated |
| Human review | pending | pending |
| Industry content | governed findings | null |

Both runs persisted and returned through the strict reader. All six baseline source-object comparisons and all five available partial-run source-object comparisons passed with complete recursive and canonical equality. Source/component hashes and final conclusion/ledger/challenge bindings resolved correctly for each run. Missing Industry produced this explicit visible warning:

```text
industry: No governed M2 industry findings are available.
```

The other valid components remained complete and retained unchanged substantive claims and business data under the narrowly defined cross-run checks above. No neutral industry narrative, synthetic substitute or latest-run fallback appeared. The full baseline artifact remained identical when strictly read again after the partial run existed.

The more restrictive result remains recorded exactly: whole partial-run source conclusion `challenge_status=escalated`, memo `conclusion_status=human_review_required`, human review `pending`, overall completeness `incomplete`. The existing all-module finalization rule remains unchanged.

Partial-run audit SHA: `17831951226b0e5c0c496b7744eff8fc7531afad4617f392a5ca7a6b03d5495f`. Partial-run provenance SHA: `377fa0ef1db13d01a981f34f23e9a0b9186992b267036d273c4c3e31e2b58d9f`. Partial memo content hash: `89841fbaf2b6dc9b7f13128122a17a70ec17a2bba465ff60c5c2d6bb0d1aebd9`. All five available component source/copy hashes and baseline hashes are captured in the evidence JSON.

## Proof 3 — Exact-run integrity and tamper rejection: PASS

### A. Same-company foreign debt binding: PASS

Two valid persisted frozen runs for the same Northfield company have distinct analysis IDs: A `ar_a99928a462554c3d` and B `ar_819fa7b232494055`. A detached adversarial input supplies B's full Module 4 envelope, its correctly hashed D1 binding and recorded producer references to A. The detached envelope hashes are recomputed to isolate identity checks from a trivial bad-digest failure; authoritative DB stages are not modified.

B's D1 component hash is `6854da9c5843ad87a99faf51e0209c864b66e677af4888f7b94106ccd13c3a40`. The identical scripted business data can legitimately have the same content hash across runs; the retained B run identity still causes rejection. Debt becomes unavailable with null content and warning:

```text
debt: debt: component identity differs from the selected root.
```

A's structure block and other three sections remain exactly unchanged. Overall completeness becomes incomplete. A's authoritative persisted memo remains unchanged through the strict reader; no historical/latest-run substitution occurs. This test establishes component isolation for the detached hostile input; it does not overwrite a frozen A stage to publish a replacement partial memo. Persistence of mismatched detached inputs is independently rejected in subtest C.

### B. Root audit/hash-chain tampering: PASS

In a disposable database, raw SQL corrupts audit stage `bo_audit:ar_697c87d959964ea9` below the ORM immutability guard without repairing its recorded hash chain. Loading for assembly, strict artifact reading and attempting persistence from an earlier saved copy each raise `ArtifactIntegrityError` with:

```text
Recorded artifact integrity check failed: bo_audit:ar_697c87d959964ea9
```

No new output file is published, stage count does not increase and the pre-existing frozen memo bytes are unchanged. A detached valid object can still be transformed purely in memory, but cannot bypass the authoritative reload needed for publication. The strict reader refuses the previously frozen memo once its source chain is corrupt.

### C. Modified/detached persistence bypass: PASS

For run `ar_07b362b59b754f4e`, persistence rejects a modified, internally rehashed SavedInputs object after reloading authoritative stages:

```text
Provided assembly inputs differ from the authoritative frozen stages.
```

A valid detached SavedInputs/memo pair supplied to a separate empty database also fails:

```text
Selected BO run does not exist.
```

No rejected output file or detached stage is created. The existing memo's payload bytes, SHA and chain hash are unchanged, and its authoritative strict read still equals the original. Its recorded stage SHA is `06243385fd450d780c6f2db84b423c95eb6f9a055ccc3db1a93fccade2b5c9bc`.

## Preservation, earlier failures and limits

Before editing, SHA-256 hashes were captured for all 626 existing files under `app`, `tests` and this design documentation directory. Before updating this report/evidence, the only changed file was `tests/integration/test_bo_four_section_independent.py`; all application files and other tests retained their prior bytes. The final intended changes are that test, this report and its evidence JSON. Existing uncommitted Milestones 1–3 work remains preserved. No branch/commit operation was performed.

The prior verification stopped on an overly strict cross-run equality assertion. The present user-authorized criterion corrects that test interpretation; it does not repair or alter application governance. Historical observations are summarized in the evidence JSON, and the current proof results come from this fresh execution.

The implementation report's two earlier M4 regression failures (acceptance despite absent M3; all-validator advisory expectations) were not rerun in this scoped verification. Their earlier classification is not new verification evidence. This execution has no new failing tests; it does not claim the entire repository suite is green.

The runs are fictional and scripted with real recorded upstream validation/challenge metadata. They establish the requested assembly, partial availability, source identity and bounded persistence behavior, not live analytical quality or exhaustive real-world debt coverage. No UI/rendering, live ingestion, production deployment, concurrency or broad FO/RMS regression was tested. Subtest B covers detectable raw audit/hash-chain corruption, not an attacker replacing the entire database and all trust anchors.

**READY FOR MILESTONE 4** under the corrected verification criterion. Milestone 4 has not been implemented or started.
