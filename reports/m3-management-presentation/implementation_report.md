# BO M3 management presentation refinement

Branch: `feat/m3-management-presentation`. Original base: `UI_Draft_V2` at `27b5ef6cb56e6654c71d7cbe3aa376542bc9d088`. Initial implementation: `d7a6c05`.

## Changes made

The web view shows the recorded overall assessment, populated credit-relevant categories, and a compact **Areas Requiring Further Assessment** list. All five categories remain in the adapter. Unclassified eligible findings appear under **Other Reviewed Observations**, which opens initially when it contains negative findings. Executive profiles, original reviewed observations, qualifications, citations, and existing audit controls remain accessible.

The print view uses the same adapter. It shows up to three accepted strengths and three concerns, qualifications, or information gaps, followed by the compact assessment-gap list. Negative findings are considered before other qualified findings and gaps, retaining source order within each group. Unclassified negatives remain eligible. If the three-item limit excludes further concerns or qualifications, a count directs readers to the selected run's interactive evidence and Audit & Review. There is no inferred impact ranking or new score.

Both views retain verbatim finding text, review status, uncertainties, and source references. Effective overall qualifications use an existing explicit review correction when recorded; original review history remains in the supporting record.

| Modified file | Purpose |
| --- | --- |
| `app/services/bo/management_view.py` | Assessment gaps, unclassified concerns in print selection, and effective overall qualifications. |
| `app/api/templates/bo_management.html.j2` | Shared management markup, dynamic cards, sources, expandable records, and compact print narrative. |
| `app/api/templates/bo_four_section.html.j2` | Include the shared management template. |
| `app/api/templates/bo_four_section_style.html.j2` | Scoped spacing and source wrapping. |
| `tests/conftest.py` | Temporary valid `DEBUG=false`, restored by monkeypatch. |
| `tests/integration/test_bo_four_section.py` | Explicit UTF-8 read without weakening equality assertions. |
| `tests/integration/test_bo_four_section_independent.py` | Isolated `tmp_path` proof outputs and explicit UTF-8; original assertions preserved. |
| `tests/unit/test_management_view.py` | Categorization, review eligibility, qualifications, deduplication, selection limits, unavailable states, corrections, and immutability. |
| `tests/integration/test_bo_four_section_renderer.py` | Dynamic categories, web/print parity, unclassified concerns, source targets, and frozen stage integrity. |
| This report directory | Diagnostics, test results, previews, screenshots, and sample PDF. |

**Analytical behavior changed: none.** The specialist, Validator 7, prompts, M3 contracts, frozen assembly/persistence, canonical artifacts/hashes, FO, RMS, and human-review rules were not modified. All generation used offline fixtures; no paid model calls were made. The branch was not pushed or merged.

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

Final broader run: **308 passed, 0 failed, 1 skipped**. This includes the final focused subset of **77 passed out of 77**, including all six original failures. The earlier standalone focused run had **76 passed**; the final broader run also includes the added print-selection-cap test. Machine-readable counts and original-test statuses are in [test summary](test_summary.json).

Final results are in [broader test output](broader_tests.txt) and [JUnit results](broader_tests.xml). Coverage includes management, M3 integration/Validator 7, four-section assembly/integrity, historical and foreign-run isolation, BO governance/workbench/review, unified memo review, and BO/FO integration/provenance. The standalone focused run is in [focused output](focused_tests.txt).

The remaining skip is `test_completed_memo_downloads_as_pdf_of_the_same_run`: the application's WeasyPrint backend lacks native libraries on this host. The Chrome sample verifies a binary print result, but does not turn that skipped application-backend test into a pass. An existing Starlette/httpx deprecation warning remains.

## Limitations and merge recommendation

- The verified M3 schema supports only a conservative subset of the five categories. Missing categories remain assessment gaps; no FO/M4 judgments or unsupported governance/expertise conclusions are imported.
- Print selection preserves reviewed direction and source order because the contract supplies no reliable materiality ranking. Complete observations remain in the existing selected-run evidence and audit views.
- The native application PDF endpoint was not verified end to end. Chrome binary printing and template behavior were verified separately.
- The relevant broader regression selection was run; the entire repository suite was not run.

**Recommendation: ready for review and merge with the documented native-PDF environment limitation.** All six original failures are explained and fixed in tests. No unresolved presentation or artifact-integrity regression remains. No merge was performed.
