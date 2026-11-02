# Milestone 4 — Four-section renderer integration

Implemented on `UI_Draft_V1` at unchanged HEAD `34d61e7b3e547228d6766ec4a7e916395821a906`, preserving the existing uncommitted Milestones 1–3 work. Milestone 4 stops at saved-artifact presentation. New Analysis execution has not been opted into the new orchestrator contract. No agents, analytical prompts, assembler/source-copy rules, FO/RMS calculations, governance rules or dependencies were changed. No live inference, SEC acquisition, external API calls, deployment, commits, pushes or merges were performed.

## Implemented behavior

The renderer uses the strict Milestone 3 reader and the selected run's recorded four-section handoff binding. A missing binding follows the existing legacy renderer. A present but invalid binding produces an integrity failure, never a silent legacy fallback. The strict reader verifies the document/schema version, stage chain, exact run/snapshot/conclusion identity, component bindings and content hashes before presentation.

The four numbered Business Overview sections retain their exact order. The desktop first section places the existing safe Module 3 SVG on the left and complete D1 tables on the right. Mobile stacks structure above debt. The diagram's original canvas and geometry remain intact; the recorded plain-text ownership tree supplies readable names/hierarchy at small sizes, and a native enlarge control exposes the full-size diagram without new rendering logic.

Both debt schedules show every supplied row and business column: borrower, principal/drawn amounts, nullable facility limits, interest terms, maturity, security, guarantees/support and priority. Aggregate rows, zero-drawn facilities, signed reconciling items and creditor-priority context remain present. Tables scroll horizontally within focusable, labeled regions; columns are not removed for narrow screens. Presentation labels replace known technical security/priority enums without changing canonical objects. Null is displayed as “Not recorded”; zero is retained as zero. There is no total recomputation.

Management displays the reviewed overall wording, profiles, appointment and disclosed prior-role information, recorded tenure, succession, surviving accepted/qualified observations, uncertainties and material limitations. Unsupported judgments are withheld from the analytical body. Full source/validation objects remain available in evidence; raw `model_assessment` is not substituted for the reviewed overall assessment.

Competitive Positioning displays the exact selected overall assessment, followed by ordered business drivers and material risks, including the selected Agent 6 interaction and its qualification. The renderer does not summarize, paraphrase, deduplicate again or invoke coverage/further-findings helpers. Deliberately omitted findings remain absent from the narrative and remain available in Audit & Review.

Expected missing Industry displays **“Industry analysis is not available in this version.”** The fourth section remains present. Other eligible sections still render, with the actual recorded incomplete/review status. When governed Industry findings exist, their original claims, credit mechanisms, interpretation and qualifications are displayed from the saved artifact. No specialist/retrieval call or industry synthesis is introduced.

## Evidence, safety and current review state

Native `<details><summary>` evidence panels start closed. Actual claims, key figures, qualifications, simulation notices, missing information and review/completeness warnings remain visible. Quotations, document references, hypothesis/parameter IDs, selection ledger, recorded challenge, detailed validation, source hashes and referenced calculation traces are inside evidence. Corporate submitted-source records and admitted debt passages resolve from the same verified saved snapshot. Source references are used to resolve evidence only; they do not reconstruct the memo body from raw specialist outputs.

Evidence panels carry the selected analysis-run ID. Native interaction changes browser visibility only. No fetch handler, calculation, inference or review write is attached. Source links use the existing safe-URL filter. Display copies use existing credential redaction and Jinja escaping. Only the existing deterministic SVG generator supplies trusted markup. Technical finding-ID prefixes are removed from visible warning labels, while the exact canonical warnings and references remain in JSON/source records. Validated analytical sentences themselves are not rewritten or stripped with citation regexes.

Current review state is loaded from the verified existing handoff/review records, rather than the immutable artifact's initial pending snapshot. Tests accept one selected run through the existing review API and confirm the page changes to Accepted while its frozen memo stays byte-for-byte unchanged and a second run stays Pending. Incomplete memo content is not relabeled complete by approval.

## Routes and compatibility

| Existing entry point | Four-section behavior |
|---|---|
| `/analysis/{job_id}/review` | Strict selected-run view inside the existing Review template; existing navigation, FO and RMS portions retained |
| `/credit-memos` | Historical links keep the explicit job/run selection and verify the bound artifact; no latest-run substitution |
| `/cases/{case_id}/bo/runs/{run_id}/memo.html` | Version-routed standalone four-section page; legacy page retained for runs without the new binding |
| Same base `/memo.json` | Exact canonical four-section artifact for new runs; no display edits or review-overlay mutations |
| `/analysis/{job_id}/memo.pdf` and BO `/memo.pdf` | Existing export infrastructure receives the new print view and static evidence appendix |
| Existing Audit & Review / BO workbench | Full specialist history, omitted findings and existing review form remain available |

There is no backfill, execution activation, source acquisition or migration. Legacy memo JSON/HTML/PDF paths remain in their original branch when the new binding is absent. FO-only and combined legacy review regressions pass. FO/RMS presentation and calculations were not replaced. The new BO body does not rely on the availability of a Competitive Positioning conclusion to display independently eligible Modules 2–4.

## Files changed and reused

Added:

- `app/services/bo/four_section_view.py` — strict selected-run presentation loader, redacted evidence resolution, safe SVG, table labels, current-review overlay and standalone rendering.
- `app/api/templates/bo_four_section.html.j2` — shared four-section body, full schedules, management/selected claims/Industry, native disclosures and print evidence appendix.
- `app/api/templates/bo_four_section_style.html.j2` — scoped layout/scroll/disclosure/print rules using existing design tokens.
- `app/api/templates/bo_four_section_page.html.j2` — standalone wrapper reusing existing website styles/navigation.
- `tests/integration/test_bo_four_section_renderer.py` — sixteen focused renderer cases, including parameterized missing and partial states.
- This report and the offline preview/visual verification files below.

Modified:

- `app/services/analysis_workspace.py` — detect and strictly load the bound new artifact; preserve the legacy branch and existing audit/FO logic.
- `app/api/templates/analysis_review.html.j2` — include the new body/style for new artifacts; retain the legacy BO branch and existing FO/RMS content.
- `app/api/workbench.py` — route exact-run BO HTML/JSON/PDF memo exports to the new renderer when bound.

Reused without modification: the Milestone 3 assembler/schema/reader and frozen-stage infrastructure; Milestone 2 writer/challenger; existing SVG generator; source redaction/safe URLs; human review; legacy report builders; website typography/colors/tables/responsive styles; PDF backend dispatch; FO/RMS services and New Analysis worker/configuration.

SHA-256 comparison against all **626 pre-existing files** in `app`, `tests` and this documentation directory confirmed that the only previously existing files changed during Milestone 4 are the three listed above. Existing Milestones 1–3 implementation, tests and reports retain their prior bytes. `git diff --check` passes.

## Offline example and visual evidence

The example was produced by a fresh isolated, fictional Northfield run with real recorded offline validation/challenge metadata, frozen stages and strict-reader verification. Industry alone is unavailable; structure, management, D1 debt and selected Competitive Positioning are populated. It is explicitly an offline simulation, not a production substitute or evidence of live analytical quality.

- [Canonical saved memo JSON](milestone-4-preview/memo.v1.json)
- [Review HTML preview](milestone-4-preview/review.html)
- [Standalone HTML preview](milestone-4-preview/standalone.html)
- [Desktop screenshot](milestone-4-preview/desktop.png)
- [Mobile first-section screenshot](milestone-4-preview/mobile.png)
- [Expanded evidence screenshot](milestone-4-preview/evidence-expanded.png)
- [Print HTML](milestone-4-preview/print.html) and [verified browser print PDF](milestone-4-preview/memo.pdf)
- [Exact-run identity and source references](milestone-4-preview/identity.json), [browser checks](milestone-4-preview/browser-checks.json) and [PDF checks](milestone-4-preview/pdf-checks.json)

Example run: `ar_30fa71dcfe4d4e91`; canonical memo content hash: `c85a809e9d19188fe13906dab0aedd8c1cba367e395eb2627e80f84b7e00f132`. Offline HTML files are inspection artifacts; their application navigation/download links require the corresponding saved-job database rather than a `file:` browser session.

Local headless Chrome at desktop width 1440 reported a two-column layout of approximately 371px/611px, with an intact 1080px debt table inside its scroll region. Mobile width 390 reported a single 312px content column and structure above debt. Neither view caused body-width overflow. Evidence panels had zero `open` attributes initially; an actual native summary click expanded a panel and a second click collapsed it. External HTTP/HTTPS requests were blocked during visual checks. Final desktop/mobile and evidence screenshots were visually inspected.

## PDF and export verification

Both existing PDF endpoints were exercised with a capture backend to verify that they receive the new four-section print HTML and evidence appendix. Canonical JSON export was compared to the exact strict-reader artifact; all frozen stage hashes/payloads remained unchanged across GETs.

The same print HTML was additionally rendered with local Chrome's PDF engine. The resulting example has **40 pages**, with the four-section analytical body on pages 1–4 and a complete static evidence appendix starting on page 5. Body and appendix were inspected through rendered PNGs; all-page text checks confirmed section names, full schedule/guarantee headings, reconciling context, expected Industry placeholder and supporting Agent 6 reference. An all-page character-bounds scan found no text extending horizontally beyond the page. Debt columns remain in print, rows wrap, table headers repeat and material warning blocks are kept together.

**Environment limitation:** neither optional WeasyPrint nor xhtml2pdf is installed in the application's test virtualenv. The existing PDF backend test therefore skips, and native application export retains its existing HTTP 501 behavior in that environment. No dependency was installed or new backend added. Backend dispatch/template content and the actual browser print PDF are verified; WeasyPrint/xhtml2pdf-specific rendering is not verified here. The provided browser PDF is visual/export evidence, not a claim that an optional application backend ran.

## Offline tests

Broader regression command:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -x -q --tb=short tests/integration/test_bo_four_section_renderer.py tests/integration/test_bo_four_section_independent.py tests/integration/test_bo_four_section.py tests/integration/test_analysis_review_workspace.py tests/integration/test_analysis_review_financial.py tests/integration/test_analysis_workspace.py tests/integration/test_bo_cli_workbench.py tests/integration/test_bo_competitive_positioning.py tests/integration/test_rms_runner.py tests/integration/test_review_workflow.py tests/unit/test_audit_immutability.py
```

**155 passed, 1 skipped in 48.18s**, with the existing Starlette/httpx deprecation warning. The skip is the optional PDF-backend test noted above. No failing regression was observed in this selected suite. The two unrelated M4 failures described in earlier milestone reports were not rerun and are not claimed resolved.

After the final evidence-detail additions, reran the directly affected renderer suite and all independent assembler proofs:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q --tb=short tests/integration/test_bo_four_section_renderer.py tests/integration/test_bo_four_section_independent.py
```

**21 passed in 13.51s**, with the same existing deprecation warning. This is a subset of the broader coverage, not 21 additional unique tests.

Focused cases verify: full content and section order; both complete debt schedules/columns/nulls/zeroes/priority labels; closed evidence and hidden source IDs/quotes; exact claims/qualifications; no omission reinsertion; independent missing Industry/structure/debt/management/Competitive Positioning using upstream scripted producers; current-review overlays; exact same-company historical selection; canonical JSON export; PDF template/route dispatch; corrupted binding rejection; retained Audit & Review and approval controls; escaping and withheld unsupported judgments; partial template states; and long debt fields without truncation. GET-time backend generation and legacy reinsertion are explicitly forbidden in the populated renderer check, and frozen payloads/hashes are unchanged afterward.

Partial wrappers and hostile/long display records are defensive template tests over detached display copies, not manufactured persisted company evidence. Missing-component tests use actual frozen runs. No claim is made that this milestone changes which partial upstream artifacts the existing assembler admits.

## Remaining limits and stopping point

The new renderer is deterministic and read-only over exact saved inputs. Evidence disclosure is source-field based: it hides designated citation/quotation/validation fields while retaining analytical sentences verbatim. Full-size diagrams can require scrolling; the unchanged source geometry is accompanied by its readable ownership tree. The detailed static evidence appendix is intentionally lengthy rather than truncated. Backend-specific PDF pagination remains subject to the optional backend limitation above.

No New Analysis activation, live HCA run, UI redesign or Milestone 5 end-to-end activation was performed. Milestone 4 implementation and offline verification are complete within those stated limits; stop here before Milestone 5.
