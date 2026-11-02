# Milestone 4 — Corporate structure and debt print layout correction

Verified 3 November 2026. Scope: HTML/CSS/print presentation and a focused regression test only. No Milestone 5 activation, live inference, SEC retrieval, dependencies, deployment, commits, pushes or merges.

## Cause

The original HTML already placed Corporate Structure and Debt Obligations inside the same two-column wrapper. The website's desktop layout was correct. The primary PDF cause was the explicit print override:

```css
@media print {
  .bo-four-section .memo-columns { display: block; }
}
```

Both PDF wrappers also selected portrait A4. Portrait width was a secondary readability constraint: fitting the entire eight/nine-column schedules beside a diagram would require overly small text. The original mobile media query was not screen-qualified, but the deliberate `display:block` print override was the direct reason for stacking.

## Small correction implemented

- Preserve the existing desktop grid, complete schedules, scroll regions, mobile stacking and native evidence controls.
- Qualify the mobile breakpoint with `@media screen` so print cannot accidentally use a narrow-screen layout.
- Use landscape A4 for the new four-section print document; retain portrait A4 and original margins for legacy documents.
- Put a readable diagram on the left and a concise source-faithful debt summary on the right. The summary directly copies the existing three priority-tier balances, consolidated indebtedness, structural subordination ratio and signed reconciling items. No totals, ratios or assessments are calculated.
- Start complete, full-width debt schedules on the next page. Preserve every instrument, column, guarantor/support field, security/priority classification, zero, null, reconciliation and creditor-priority context. Table text is 9 pt, rather than the previous 7 pt; headers repeat across page breaks.
- Frame the existing safe SVG around its recorded node geometry for print. The original SVG remains nested intact: no diagram generator, ownership link, node label or guarantor indicator is redrawn. The original surrounding decorative canvas is not squeezed into the column. The printed caption retains the recorded guarantor-symbol explanation, the exact ownership tree remains visible and the simulation notice remains prominent.
- Keep full structure limitations with the complete schedules as well as the simulation notice on the overview. Tighten print-only header/status spacing to keep the overview on the first page; there is no header-only introductory page.

Files changed:

| File | Reason |
|---|---|
| `app/api/templates/bo_four_section.html.j2` | PDF-only side-by-side summary, framing of the existing diagram and subsequent full schedules |
| `app/api/templates/bo_four_section_style.html.j2` | Explicit print columns, readable table sizes, pagination and screen-only responsive breakpoint |
| `app/api/templates/analysis_review.html.j2` | Landscape/margin choice conditional on the new artifact; legacy portrait retained |
| `app/api/templates/bo_four_section_page.html.j2` | Matching standalone PDF page orientation |
| `tests/integration/test_bo_four_section_renderer.py` | Exact source-value summary/full-row checks and legacy orientation check |

All service/agent/orchestrator/assembler/validation/governance code remains unchanged. A file-hash comparison against the start of this correction found only those five previously existing files changed. Earlier preview JSON, HTML, PDF, source identity and milestone reports are preserved; corrected visual artifacts are in a separate directory.

## Desktop and laptop verification

Local Chrome rendered the updated HTML at 1440, 1366, 1280 and 1024 px. All four screenshots were visually inspected. Structure remains on the left, with debt at the same top coordinate on the right. The existing grid computed approximately 371/611 px at the wider sizes and 334/552 px at 1024. No body-width overflow occurred, and no print-only summary appears on the website.

- [1440 px screenshot](milestone-4-layout-correction/desktop-1440.png)
- [1366 px screenshot](milestone-4-layout-correction/desktop-1366.png)
- [1280 px screenshot](milestone-4-layout-correction/desktop-1280.png)
- [1024 px screenshot](milestone-4-layout-correction/desktop-1024.png)
- [1280 px with the senior-note table scrolled right](milestone-4-layout-correction/desktop-1280-columns-right.png)

The last screenshot was captured after a native horizontal wheel interaction. The guarantee/security/priority columns remain visible and readable when scrolled; they are not clipped away or dropped. The website intentionally retains an inner table scroll region rather than shrinking the complete schedules to fit its right column. Evidence panels begin closed and actual native summary clicks still expand/collapse them. External HTTP/HTTPS requests were blocked in the visual checks. [Browser measurements](milestone-4-layout-correction/browser-checks.json) record the results.

## PDF verification

[Corrected landscape PDF](milestone-4-layout-correction/memo-landscape.pdf) · [print HTML](milestone-4-layout-correction/print.html)

The actual local Chrome print output was rasterized with Poppler and inspected. Page 1 now contains the diagram on the left and debt figures on the right. Page 2 begins the complete schedules; page 3 continues with repeated headers and includes all four non-note obligations. Creditor-priority and reconciliation context follows. All six analytical-body pages and the start of the evidence appendix were visually inspected.

Automated PDF checks verified:

- Landscape dimensions: approximately 842 × 595 points, replacing the previous 595 × 842 portrait output.
- Both the structure and debt-summary headings are on page 1; no header-only first page.
- All **84 instrument-field values** (six notes × eight fields, four non-note obligations × nine fields) are present in the analytical body, not merely recoverable from the appendix.
- All seven creditor-priority framework values remain in the analytical body.
- All-page text bounding checks found no horizontal text outside the page.
- Complete debt tables use 9 pt text. Actual page inspection confirmed readable wrapping, intact guarantee/security/priority columns, repeated headers and unsplit obligation rows.
- Supporting evidence remains available in the complete static appendix, which begins on page 7. The document has 62 pages because its full evidence records are retained at 8 pt in landscape rather than truncated.

[PDF checks](milestone-4-layout-correction/pdf-checks.json) contain the field-by-field verification results. The application virtualenv still lacks its optional WeasyPrint/xhtml2pdf backend; the existing native-export test remains skipped. This PDF verifies actual rendering of the application's print template in local Chrome. Backend-specific WeasyPrint/xhtml2pdf pagination is not newly certified.

## Source preservation

The visual preview reuses the prior verified example, without creating a new analysis run or rebuilding its memo. Its existing canonical JSON and previously rendered evidence were replayed at the presentation boundary only; no database import or historical backfill was added.

```text
Analysis run: ar_30fa71dcfe4d4e91
Original JSON file SHA-256:
62bab98bdeda28f3e1e27f400f1bd3472e7e40bc97655bb69c00aea58bb7e447
Unchanged memo analytical content hash:
c85a809e9d19188fe13906dab0aedd8c1cba367e395eb2627e80f84b7e00f132
Current human review: pending
Completeness: incomplete
```

The JSON bytes, underlying D1 values, claims, source references, provenance and review status were not modified. The right-hand summary is a print-only repetition of explicitly designated source fields; the complete D1 object and schedules remain unchanged. [Source identity](milestone-4-layout-correction/source-identity.json) records the original file/hash.

## Regression tests

Actual command:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q --tb=short tests/integration/test_bo_four_section_renderer.py tests/integration/test_analysis_review_workspace.py tests/integration/test_analysis_review_financial.py tests/integration/test_bo_four_section_independent.py
```

**45 passed, 1 skipped in 15.86s**, with the existing Starlette/httpx deprecation warning. The skip is the previously unavailable optional application PDF backend.

The new `test_landscape_print_summary_and_full_schedules_preserve_sources` checks both PDF wrappers, verifies summary values against their exact source fields, checks every rendered schedule row/cell against the complete source objects, proves screen rendering has no print summary, confirms unchanged canonical saved content and verifies legacy PDFs retain portrait A4/margins. Existing tests cover collapsed evidence, historical selection, partial/missing components, current-review overlays, redaction/escaping, legacy rendering, FO presentation and the independent integrity proofs. `git diff --check` passes.

Correction complete. No Milestone 5 work was performed.
