# Credit Memo UX — progressive evidence disclosure

Implemented locally on UI_Draft_V1, 2 November 2026. No commit, push, merge, acquisition or paid/live model call. This report covers this presentation refinement; earlier consolidated-BO implementation changes remain in the working tree.

## Result

- Credit Memos has a secondary **Add Company / Manage Filings** link. It opens the existing New Analysis page's filing tools. The full acquisition form is collapsed by default; SEC results, acquisition feedback or the explicit management link open it. Existing download and manual-upload forms, endpoints and validation remain intact. The home page retains two main navigation choices.
- Each debt schedule has four summary columns: instrument/borrower, outstanding/drawn $M, maturity, security/priority. Every source record stays in its original schedule and gets a native keyboard-accessible Details control. Additional fields and exact recorded classifications are available there without repeating the whole summary row. Limits are explicitly labelled as facility limits, not outstanding debt.
- The memo keeps corporate structure, management narrative, all selected Competitive Position analysis, uncertainty/counterevidence, coverage gaps, refinancing events and conclusions, strategy findings, Industry narrative/key figures and material limitations visible. The default removes long quotations, source metadata, technical classifications and copy hashes.
- Claim-level Supporting evidence controls expose saved quotations, document/section/page/location where recorded, supporting figures and exact-run audit links. Expansion only toggles native HTML details; it makes no network or model request. Management citations use their recorded physical PDF page.
- Existing Audit & Review remains the complete specialist, selection, validator, challenger, governance and provenance interface. Source links use its evidence anchors only when the workspace job matches both case and BO run. Standalone exports link to the existing case/run audit URL without inventing an anchor.
- Mandatory simulation, incomplete-data, unresolved-challenge and human-review warnings remain visible. Known diagnostic prefixes become plain-language qualifications; their original text remains in the artifact/audit or collapsed provenance.
- On phones, the page does not overflow. Four-column debt tables have a labelled horizontal scroll region; expanded debt details fit the phone width. No truncation, ellipsis or line clamping is introduced.

## Deterministic mappings and numerical fidelity

| Recorded value | Display label |
| --- | --- |
| tier_1_direct_opco_secured | Tier 1 · Direct operating-company secured |
| tier_2_senior_unsecured_guaranteed | Tier 2 · Senior unsecured, guaranteed |
| tier_3_unguaranteed_holdco | Tier 3 · Unguaranteed holding-company debt |
| secured / unsecured | Secured / Unsecured |
| new_issuance | New issuance |
| repayment_at_maturity | Repayment at maturity |
| early_redemption | Early redemption |
| facility_amendment | Facility amendment |
| tender_exchange | Tender / exchange |

Matching is case-insensitive against these explicit mappings. An unknown ranking displays **Ranking not recognised — see details** and retains its exact code in expanded details. Other unknown classifications display **Classification not recognised — see details**; no ranking is inferred. Review status maps the contract's pending, accepted and rejected states to capitalised labels.

Amounts use decimal-based thousands grouping without rounding or stripping stored fractional digits. Examples: `2207.0` → `2,207.0`, `-436.0` stays negative, `1234.4500` → `1,234.4500`. Missing/non-finite amounts are marked Not recorded. Source wording is preserved when an amount is not numeric. No calculated totals are added; only the source's recorded consolidated indebtedness is displayed.

Known mapping ambiguities: source precision means precision available in the saved value. Decimal digits already discarded before JSON storage cannot be recovered. The illustrative source places a negative debt-cost adjustment inside its non-note schedule; this UI preserves that placement and sign rather than silently reclassifying it. Missing maturity/quotation/reference values remain missing. The illustrative Industry source lacks a standalone report; the existing incomplete notice remains. Synthetic previews contain fictional Module 1/3 evidence and a reduced HCA-shaped Module 4 fixture, as prominently disclosed.

## Print and PDF

Browser `beforeprint` opens substantive evidence/debt panels; `afterprint` restores their previous state. Print layout retains the substantive memo, limitations, supporting evidence, case/run identity and audit URL; bulky technical provenance remains available through Audit & Review. Link destinations are printed alongside expanded evidence links.

Both consolidated PDF-generation paths pass `expand_evidence=True`, so evidence is already open even when the PDF renderer does not execute JavaScript. The offline PDF-route test intercepts the HTML passed to the renderer and verifies open panels, source quotations, run identity and print hooks. No optional PDF renderer is installed in this environment (neither WeasyPrint nor xhtml2pdf); actual PDF pagination and rendering-engine differences remain unverified. No dependency was installed. Saved expanded HTML is included in the gallery for inspection.

## Files changed in this refinement

| File | Change |
| --- | --- |
| app/services/bo/memo_presentation.py | New read-only formatting, mapping, notice and exact-run link helpers |
| app/services/reporting/templates/bo_consolidated_body.html.j2 | Compact debt rows, per-record/claim disclosures, visible analysis and qualifications, print expansion |
| app/services/reporting/templates/bo_consolidated_style.html.j2 | Native-theme disclosure/table spacing, responsive layout and print rules |
| app/services/bo/reporting.py | Register presentation helpers; optionally render expanded export HTML |
| app/api/workbench.py | Request expanded evidence for consolidated PDF export |
| app/api/analysis.py | Register helpers; expose optional filing-management disclosure state |
| app/api/templates/analysis_setup.html.j2 | Collapsible filing tools using existing forms/routes |
| app/api/templates/credit_memos.html.j2 | Secondary filing-management link |
| app/api/templates/analysis_review.html.j2 | Collapse technical run identifier |
| tests/integration/test_bo_progressive.py | 14 presentation/mapping/filing/export test cases |
| tests/integration/test_bo_editorial.py | Count actual debt records separately from disclosure rows; assert formatted source amounts |

Also added this report and examples/bo_progressive: screenshot gallery, saved default/expanded HTML, rendering helper, read-only preview server, preservation manifests and test logs. Existing earlier examples were retained.

An initial helper filename collided with the pre-existing bo/presentation.py validation-policy module. That file was restored byte-for-byte, and the new helper has the distinct name memo_presentation.py. The final preservation check includes the original policy module.

## Verification

All tests ran through the existing offline runner with outbound socket connections denied and scripted fixtures. No live SEC/model/API requests were made.

- Workflow, setup, execution, worker health and presentation regression group: **111 passed**.
- Memo review, exact-run attribution, financial review, governance, workbench and combined BO/FO/acquisition regression group: **110 passed**.
- Final presentation rerun after the last layout/fidelity adjustments: **42 passed** (overlaps the 111-test group).
- Each group reports one existing warning; no test failures remain in these groups. These are selected regression suites, not a claim that the entire repository suite passed.
- Hash comparison: **297 protected prompt/schema/service/config files unchanged**, excluding the deliberately changed reporting renderer. This includes validation/presentation policy, worker execution, persistence, underlying Module 1–4, synthesizer/challenger code and Financial Overview services.
- Existing consolidated/audit JSON and the fixture analysis database are byte-for-byte unchanged. All saved terminal job payloads, statuses and exact-run references are unchanged. The existing JobStore GET implementation writes `PRAGMA user_version=1`, which changes the job-sidecar SQLite header bytes; no analysis or job was regenerated/restarted.
- Browser inspection: desktop 1440 × 1000; phone 390 × 844. Default and expanded debt/evidence screenshots captured. At 390px the page width remains 390px; debt tables scroll inside 312px regions. Keyboard Enter opens/closes both record and claim disclosures. Source navigation reached the selected job's matching evidence anchor. Historical review displayed all 10 debt records; New Analysis and the filing disclosure worked.

Verification logs and machine-readable preservation results are in examples/bo_progressive/verification. Screenshots are indexed by examples/bo_progressive/gallery.html.

## Manual browser review

1. Open the read-only preview at http://127.0.0.1:8773/credit-memos. Select the newly-completed or historical Northfield synthetic memo.
2. Confirm warnings remain visible, the debt tables use readable labels, and source quotations/hashes are initially hidden.
3. Tab to a debt Details control or a finding's Supporting evidence control; press Enter. Inspect limits, recorded classifications, source text and page/section reference.
4. Follow View source in Audit & Review; the selected saved run and evidence anchor must match.
5. From Credit Memos, choose Add Company / Manage Filings. Inspect the existing SEC download and upload controls. The preview rejects submissions and approval writes; do not use it for live acquisition or analysis.
6. Resize to a phone width; scroll each debt table horizontally, and verify expanded details remain readable.
7. For print/export inspection, open examples/bo_progressive/newly-completed-expanded.html. In a normally configured app, use the existing PDF route once an optional PDF backend is available.

No Financial Overview calculation, agent, validator, worker, persistence or approval logic was changed in this refinement. No underlying saved analytical artifact, schema, prompt, synthesis or challenge policy was modified.
