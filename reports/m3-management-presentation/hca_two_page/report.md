# Two-page HCA Management PDF

Saved real run: **`ar_70066e79dd954e3c`**, case `HCA_2025_M3_PRESENTATION_LIVE_20261103`, HCA FY2025 Form 10-K. No new model calls or historical analysis regeneration were performed.

## Observation inventory

| Recorded ID | Review | Direction | PDF treatment |
| --- | --- | --- | --- |
| `j_01` | Qualified | Positive | Included verbatim as a leadership-continuity supporting factor, with qualifications. |
| `j_02` | Unsupported | Not projected | Excluded. Validator 7 recorded no sufficient accepted claim basis. Original details remain in the saved audit. |

There is **one distinct eligible finding**, zero accepted/unqualified findings, and zero eligible negative findings. **Zero eligible observations were excluded by categorization.** The PDF now considers all eligible observations, including uncategorized ones; the saved HCA record cannot supply three to five distinct findings. That limitation is explicit on page 1. Executive context is not counted as additional credit findings.

The retained observation is:

> The executive team displays high levels of institutional knowledge, with several senior leaders having multi-decade careers within the company, indicating stable internal succession pipelines and established operating expertise.

Its recorded execution-quality limitation remains visible. No separate credit-implication field was recorded, so the complete reviewed wording appears under **Reviewed finding and credit implication**; no new causal conclusion was generated.

## PDF structure

- **Page 1 — Management Credit Assessment:** unchanged reviewed overall wording, prominent Qualified status, material qualifications, the eligible finding and its direction, source markers, and the explicit finding-count limitation.
- **Page 2 — Management Details & Monitoring:** all seven sourced executives, one admitted prior role per executive where available, recorded appointments and transition classifications, consolidated assessment gaps, follow-up evidence and readable sources.

Five executives have an admitted prior role available for the compact table. Cuffe and McAlevey have no admitted prior-role detail; unadmitted histories were not substituted. Transition labels use the existing **2023-02-01 to 2026-02-01** review window and the **2026-02-01** roster date, with no new tenure or recency calculation.

The record supplies no management-specific monitoring indicators or thresholds. The PDF states this and preserves the existing follow-up request for turnover/performance evidence. Financial stewardship, operational execution, governance/integrity and relevant-expertise assessment gaps remain explicit. Page 1 is naturally shorter because only one finding is supported; no extra findings or filler were added.

## Verification and deliverables

- [Management PDF — two A4 pages](management.pdf), [page 1 image](pdf_page1.png), [page 2 image](pdf_page2.png), and [print HTML](print.html).
- [Complete credit memo PDF](memo_full.pdf): management occupies consecutive pages **4–5** of the 36-page memo; the existing evidence appendix is retained.
- [Web preview](web.html): rendered HTML is byte-for-byte unchanged from `ec98e85`, SHA-256 `0c36fb49d6905b45a20a21a9c41f65cd97f4b0e933ac97597e3b68614dca0cc5`.
- [Inventory data](inventory.json), [artifact immutability checks](immutability.json), and [PDF checks](pdf_verification.json).

The browser checks verify A4 sizing, exactly two management pages, all seven executives on page 2, the original overall wording and material qualifications, correct qualified-positive classification, readable passage-offset citations, no unsupported physical-page claims, no internal fact IDs or long source hashes in the narrative, and text within page boundaries. Both rendered pages were inspected.

All **70** saved input/result files and **29** frozen stage payloads/hashes remain unchanged. The database still contains **14** model records. Approval remains pending; the existing partial analytical result is preserved.

## Tests and scope

Final relevant regression result: **326 passed, 0 failed, 1 skipped**. This includes **95 focused checks passed**, with no focused failures or skips.

Final results are in [test summary](tests.json), [test output](tests.txt), and [JUnit output](tests.xml). The broader selection includes all focused management/four-section checks, M3/Validator 7, governance, review, historical/evidence isolation and BO/FO regressions. The full repository suite was not repeated in this pass; its previously documented baseline failures remain in the main implementation report.

Production changes are confined to the read-only adapter, PDF routing in the existing management template, and the new PDF-only template. Existing web fields, markup, evidence controls and shared styling are preserved. No specialist, prompt, model setting, validator, schema, frozen record, governance rule, FO, SO or RMS output was changed.

**Recommendation:** ready for review with the recorded one-finding limitation and native-PDF environment limitation. Chrome binary rendering passed; the unavailable native application PDF backend is reported as a skip. No push or merge was performed.
