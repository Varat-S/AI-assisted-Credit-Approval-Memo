# BO M3 management presentation refinement

**Latest PDF update:** the saved real HCA management assessment now has a two-page PDF edition, while the web output remains byte-for-byte unchanged. See the [two-page PDF](hca_two_page/management.pdf) and [observation inventory / verification report](hca_two_page/report.md). Only one supported finding exists; the second page adds sourced executive context and recorded gaps, not new judgments. Relevant regressions: **326 passed, 1 skipped**, including **95 focused checks**. The sections below retain the earlier one-page milestone and full-suite baseline history.

Branch: `feat/m3-management-presentation`. Original base: `UI_Draft_V2` at `27b5ef6cb56e6654c71d7cbe3aa376542bc9d088`. Initial implementation: `d7a6c05`; previous completed refinement: `c5460a3`. The final corrections below use the saved real HCA run without new inference.

## Changes made

The web view shows the recorded overall assessment, populated credit-relevant categories, and a compact **Areas Requiring Further Assessment** list. All five categories remain in the adapter. Unclassified eligible findings appear under **Other Reviewed Observations**, which opens initially when it contains negative findings. Executive profiles, original reviewed observations, qualifications, citations, and existing audit controls remain accessible.

The print view uses the same adapter with four independent direction groups: **Supporting Factors**, **Credit Concerns**, **Mixed or Uncertain Findings**, and **Information Gaps**. Only populated groups appear, with up to three findings per group and an explicit omission count pointing to complete supporting records. Positive qualified findings remain supporting factors; qualification alone never makes a concern. Neutral findings remain context, unknown directions remain unassessed, and rejected/unsupported observations are ineligible. There is no new impact ranking or numerical score.

Both views retain verbatim finding text, direction, review status, and source/observation identities. The overall heading prominently identifies reviewed or recorded wording, its qualification status, and the recorded outcome. An effective reviewed correction takes priority when present; otherwise existing reviewed wording or the recorded paragraph is displayed without analytical rewriting. Original model wording and review history remain in supporting evidence.

Material qualifications are displayed once beside the overall assessment. Deduplication uses exact matching after whitespace normalization, preserving first wording and every observation/origin reference. Distinct limitations are retained. Detailed rejection reasons and known processing notices remain in supporting records. Structured withheld-claim/judgment counts and an evidence-basis restriction make validation failures visible without internal fact IDs. Unknown or mixed material limitations stay in the primary view rather than being guessed away as technical. Offline/demo notices have their own labelled methodology block.

Citation labels use same-run document metadata only when document identity and SHA match. HTML uses recorded passage offsets, never the synthetic page-1 value retained by older citation contracts. PDF pages are shown only for an identifiable PDF source. Duplicate quotes from one passage share a displayed source location while retaining all original citation IDs; each finding's web anchor points to one of its own supporting quotations. Missing metadata uses a neutral label. Full identities/hashes remain in the source records and HTML metadata.

| Modified file | Purpose |
| --- | --- |
| `app/services/bo/management_view.py` | Independent direction groups, effective overall wording, exact qualification deduplication/origin links, readable source locations and print limits. |
| `app/services/bo/four_section_view.py` | Supply already verified same-run documents, passages and warnings to the read-only adapter. |
| `app/api/templates/bo_management.html.j2` | Shared management markup, dynamic cards, sources, expandable records, and compact print narrative. |
| `app/api/templates/bo_four_section.html.j2` | Reuse projected management notices rather than repeat raw processing warnings in the PDF. Unknown new warnings remain visible. |
| `app/api/templates/bo_four_section_style.html.j2` | Scoped spacing and source wrapping. |
| `tests/unit/test_management_view.py` | Categorization, review eligibility, qualifications, deduplication, selection limits, unavailable states, corrections, and immutability. |
| `tests/integration/test_bo_four_section_renderer.py` | Dynamic categories, web/print parity, unclassified concerns, source targets, and frozen stage integrity. |
| This report directory | Diagnostics, test results, previews, screenshots, and sample PDF. |

The earlier portable-directory, UTF-8 and temporary `DEBUG=false` fixes in `tests/conftest.py`, `test_bo_four_section.py` and `test_bo_four_section_independent.py` are retained without modification in this pass.

**Analytical behavior changed in these corrections: none.** The specialist, Validator 7, prompts/model settings, M3 contracts, frozen assembly/persistence, canonical artifacts/hashes, FO, SO, RMS, and approval rules were not modified. This pass used synthetic tests and the existing real HCA saved records; it made zero model calls and did not regenerate an analysis. The branch was not pushed or merged.

## Real HCA before/after verification

Exact saved run: **`ar_70066e79dd954e3c`**, case `HCA_2025_M3_PRESENTATION_LIVE_20261103`, FY2025 Form 10-K. The original run contains 14 model records, seven admitted executive profiles, one qualified positive continuity observation and a withheld judgment. It remains partial and pending human review.

| Item | Previous saved HCA presentation | Corrected presentation |
| --- | --- | --- |
| Positive + Qualified | Under concerns | **Supporting Factor · Qualified** |
| Negative + Qualified | Concern | **Credit Concern · Qualified**, with limitations retained |
| Mixed / neutral / unknown | Could be omitted or treated as a concern due to qualification | Mixed findings, context or unassessed entries; original direction retained |
| Overall wording | Qualification shown after broad positive narrative | Prominent **Reviewed assessment · Qualified** before unchanged wording, with material caveats alongside |
| Sources | Full hexadecimal passage IDs and HTML page 1 | Three readable Form 10-K references at passage offsets **159626, 161626, 163626** |
| Limitations | Repeated caveats plus technical second page | Exact duplicates consolidated; detailed processing explanations retained in supporting evidence |
| Management PDF | Two pages | **One page**, preserving the assessment, finding and material qualifications |

Updated **real saved HCA** artifacts: [web section](hca_saved/web.html), [print section](hca_saved/print.html), [full web preview](hca_saved/web_full.html), [full print preview](hca_saved/print_full.html), [before screenshot](hca_saved/before.png), [desktop screenshot](hca_saved/desktop.png), [mobile screenshot](hca_saved/mobile.png), [PDF](hca_saved/management.pdf), and [PDF page image](hca_saved/pdf_page1.png).

[Recorded-run integrity checks](hca_saved/verification.json) verify all **70** saved canonical input/result files against their original hashes, all **29** frozen stage payloads/hashes, unchanged reviewer decisions, and **14** model records before/after rendering. No model call or ingestion is allowed by this gate. [Browser checks](hca_saved/browser_verification.json) verify no horizontal overflow at 1200/390 pixels and that source links expand the supporting evidence. [PDF checks](hca_saved/pdf_verification.json) verify one page, original assessment and qualifications preserved, correct supporting-factor classification, readable sources, and no unsupported physical-page claims, long source hashes or biographies in the narrative.

The original HCA database, source responses, frozen artifacts, previous presentations and durable archive were not overwritten. The overall text still contains the live review's broad governance/succession wording: this presentation change labels and qualifies it, rather than issuing a new analytical correction. Governance remains insufficiently evidenced in the category model.

### Classification examples

| Recorded direction | Recorded review | Presentation |
| --- | --- | --- |
| Positive | Accepted | Supporting Factor · Accepted |
| Positive | Qualified | Supporting Factor · Qualified, with visible material qualifications |
| Negative | Accepted | Credit Concern · Accepted |
| Negative | Qualified | Credit Concern · Qualified, with visible material qualifications |
| Mixed | Accepted / Qualified | Mixed Finding, with its independent review status |
| Neutral | Accepted / Qualified | Context, or an explicitly recorded information gap |
| Missing / unknown | Accepted / Qualified | Unassessed; remains uncategorized |
| Any | Rejected / Unsupported | Excluded from affirmative findings |

## Six original regression failures

All six reproduce on an untouched export of the original base commit. Assertions were retained; no expected snapshots were replaced.

| Original failing test | Root cause | On original base? | Resolution | Final status |
| --- | --- | --- | --- | --- |
| `test_populated_deep_equality_order_omissions_and_persistence` | Test decoded UTF-8 as Windows cp1252. | Yes | Explicit UTF-8 read. | Passed |
| `test_independent_proof1_lossless_persisted_roundtrip` | Same default-decoding mismatch. | Yes | Explicit UTF-8 read and portable proof directory. | Passed |
| `test_independent_proof2_missing_industry_producer_persists` | Proof helper attempted `/private/tmp` on Windows. | Yes | `tmp_path / 'proofs'`. | Passed |
| `test_independent_proof3a_same_company_foreign_component` | Same Unix-only proof path. | Yes | `tmp_path / 'proofs'`. | Passed |
| `test_independent_proof3b_root_chain_tamper` | Same Unix-only proof path. | Yes | `tmp_path / 'proofs'`. | Passed |
| `test_independent_proof3c_persistence_reloads_authority` | Same Unix-only proof path. | Yes | `tmp_path / 'proofs'`. | Passed |

Exactly two fields differed in both equality tests:

1. `/sections/0/structure/content/companies/Northfield_Health_Systems/plain_text_tree`: box-drawing characters and the ownership arrow were misdecoded.
2. `/sections/0/structure/content/visual_spec/footer/text`: the em dash was misdecoded.

The mismatch exists in the test's decoded copy, rather than the original frozen artifact, serialization, hash, or management projection. Production already writes and reads UTF-8. Explicit UTF-8 decoding equals the original and database artifact exactly. Diagnostics check recorded hashes, full content hashes, persisted file SHA-256, and frozen stage bytes/hashes before and after both renderers.

Both producer paths were repeated twice on each revision: four baseline runs without the adapter and four feature runs with web/print rendering. Each showed the same two misdecoded fields with the default encoding and exact equality with UTF-8. Independent runs have different run identities and hashes; integrity comparisons are within the same run. See [baseline diagnostics](baseline_serialization.json), [feature diagnostics](feature_serialization.json), [baseline equality failures](baseline_equality_tests.txt), and [baseline path failures](baseline_path_tests.txt).

The proof helper now writes inside each test's `tmp_path`, including proof 1 whose decoding failure previously occurred before its proof write. Production paths did not change. `DEBUG=false` is applied only inside the pytest process using monkeypatch and does not overwrite persistent user settings.

## Presentation verification

These are synthetic Northfield Health Systems fixture outputs, not a live company assessment. Web and print previews are produced from the same loaded presentation object.

The before image uses the original `UI_Draft_V2` template; the desktop and mobile after images use the final feature template.

- [Updated web HTML](management_web_preview.html) and [focused web HTML](management_after_focus.html).
- [Updated print HTML](management_print_preview.html) and [focused print HTML](management_print_focus.html).
- [Before screenshot](management_before.png), [updated desktop screenshot](management_after.png), and [390-pixel mobile screenshot](management_mobile.png).
- [One-page management PDF](management_sample.pdf) and [rendered PDF page](management_sample_page1.png).
- [Browser checks](browser_verification.json): no horizontal overflow at desktop/mobile widths; profiles initially collapsed; one populated card and four compact gaps; source links open the supporting disclosure.
- [Binary PDF checks](pdf_verification.json): one page; identical overall assessment after whitespace normalization; qualifications, source locators, and assessment gaps present; appointment/tenure biographies absent.

Installed Chrome worked with an isolated profile outside the restricted sandbox. It rendered the exact inline preview HTML through DevTools. Screenshots and the rasterized PDF page were inspected. No packages were installed or system configuration changed.

## Automated results

The complete repository suite was executed on the final application code. Its focused/broader subsets were selected from the same JUnit results; they were not inferred from a shorter run.

| Selection | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Focused management/four-section checks, including all previous 77 and the new cases | **93** | **0** | **0** |
| Broader relevant M3, Validator 7, BO assembly/rendering/review/governance, BO/FO and historical/evidence-isolation selection | **324** | **0** | **1** |
| Full repository | **2,559** | **36** | **136** |

The initial focused run passed 91 tests; the full run includes the two subsequently added conservative-processing and explicit-gap tests. The preview-export test also passed separately. [Final test summary](final_test_summary.json), [full output](final_full_tests.txt), and [full JUnit results](final_full_tests.xml) contain exact counts, skip reasons and every failing node. Previous `c5460a3` results remain in the historical [test summary](test_summary.json).

**All 36 full-suite failures reproduce individually on an untouched export of `c5460a3`; there are zero newly introduced failures.** Baseline probes used the same interpreter and temporary test configuration. [Baseline reproduction output](final_baseline_failures.txt) records the original assertions; the machine-readable summary maps every failed node to its baseline reproduction.

| Baseline failure family | Count | Observed failure on both revisions |
| --- | ---: | --- |
| M2 synthetic comparison harness | 25 | Generation governance rejects unresolved evidence IDs, leaving missing hypotheses/validation stages; expected four calls become one. |
| M2 saved HCA comparison | 2 | Existing expected single-pass/investigation results differ. |
| M4 dual-specialist acceptance | 2 | Expected accepted governance/advisory labels differ from recorded results. |
| BO browser tests | 2 | Windows refuses deletion of an open SQLite database; another assertion expects an executive name visible after removing all expandable profiles. |
| FO home navigation | 1 | Home page no longer has the historical `/fo` link expected by the test. |
| Upload preview | 2 | Historical home-page text expectation and passage-count expectation (157 versus 167). |
| Validator-node identity | 1 | Missing expected `validator.v7` node in that test's run. |
| Agent 6 prompt byte comparison | 1 | Windows CRLF versus normalized LF bytes. No prompt was edited. |

These tests/engines were not changed to conceal baseline results or to alter analytical behavior. All six earlier portable-path/UTF-8 regressions still pass.

The relevant subset's skip is `test_completed_memo_downloads_as_pdf_of_the_same_run`: the application's WeasyPrint backend lacks native libraries. Full-suite skips comprise 114 missing benchmark-workbook cases, 14 missing historical HCA R5 cases, two native-PDF cases, an explicitly disabled paid live-model test and five other optional source/manifest/artifact cases. Chrome binary PDFs were verified separately; skipped native-backend tests are not reported as passing. An existing Starlette/httpx deprecation warning remains.

## Limitations and merge recommendation

- The verified M3 schema supports only a conservative subset of the five categories. Missing categories remain assessment gaps; no FO/M4 judgments or unsupported governance/expertise conclusions are imported.
- Print selection preserves reviewed direction and source order because the contract supplies no reliable materiality ranking. Complete observations remain in the existing selected-run evidence and audit views.
- The native application PDF endpoint was not verified end to end. Chrome binary printing and template behavior were verified separately.
- Unknown limitations or mixed technical/material review reasons are retained verbatim in the primary view. A future record can therefore legitimately require more than one page; material content is not truncated to satisfy a page target.
- The full suite has the 36 reproduced baseline failures listed above; it is not a green repository-wide merge gate.

**Recommendation: ready for review with documented baseline/environment limitations.** The presentation's focused and broader regressions pass, and the saved real HCA PDF is one page. A team policy requiring a completely green repository suite still requires separate resolution of the baseline failures. No merge or push was performed.
