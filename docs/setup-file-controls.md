# Setup file controls

New Analysis has two equally sized cards: Download Files and Upload Documents.

## Download Files

`POST /analysis/new/download-files` reads company/reporting targets from
`config/analysis_companies.json`, including when no filings have been downloaded yet.
The current target is HCA FY2025, shown as HCA Healthcare (HCA) after download.
The existing SEC client resolves the official 10-K accession, fetches its Inline XBRL,
XBRL schema/linkbases, supported exhibits and matching proxy if available, and writes
`bundle.json` and `company.json` into the configured `edgar_filings/` folder.
This workflow does not use a ZIP bundled in the repository or export to Downloads.

A missing filing requires a contact email. The client uses `SEC_USER_AGENT` when
configured; otherwise the UI opens a small contact dialog and sends the email in
that POST only. No email is written into `.env` or placed in the page URL. No SEC
API key is required. Valid, hash-checked local filings are reused without network.
Invalid/conflicting existing filing folders are reported without overwriting them.
The page reports results per company and refreshes the available company choices.

A registry entry can set `source_package` to null to use the downloaded bundle
directly, without requiring a hand-written package.json. Existing source-package
entries and cutoff behavior remain supported. No model calls are made by downloads.

## Corporate structure JSON

`POST /analysis/new/corporate-structure` accepts one UTF-8 JSON file up to 1 MiB,
plus the selected company registry ID. It validates the existing Module 3 onboarding
schema 1.0, company name and tree before writing `m3_corporate_structure.json` to
that company's filing folder. It requires a downloaded company to be selected.

The input must declare `data_status`; simulated educational examples remain labelled
as such. The application does not infer ownership or treat user-supplied JSON as
verified SEC evidence. The existing BO Module 3 association reads the saved file
at analysis time. Different replacements preserve the previous content under
`data/corporate_structure_history/`, and the final file is replaced atomically.
Invalid uploads leave the previous file untouched. There is no automatic AI run.

Both controls require the app's custom request header to prevent browser cross-site
form submissions. Legacy filing import/list/fetch routes remain available, but the
simplified cards do not expose their multi-step controls.
