# Corrected Business Overview previews — illustrative offline replay

These examples are **not live company analysis**. Module 1/3 evidence is fictional and
Module 4 replays an existing reduced HCA-shaped test fixture unchanged. Production Module 3
acquisition was not executed in the replay; governance remains incomplete/human review required.

Open `gallery.html` for all requested real browser captures. `newly-completed.html` and
`historical.html` are standalone renderings of the corresponding persisted JSON; adjacent
audit JSON files preserve their complete source findings and candidate decisions.
`diagnosis.json` traces the previous sparse sample without rewriting it.

The actual app preview, while its local server remains running, is:
http://127.0.0.1:8771/analysis/editorial-newly-completed/review

It serves the real Execution, Credit Memos, Review, Audit and report routes against isolated
persisted stores. Its read-only middleware rejects submissions/approval writes. Live providers
and SEC acquisition are blocked. The rich fixture is declared in `tests/fixtures/bo_editorial.py`.

To reproduce from the repository root using existing project dependencies:

    python examples/bo_corrective/preview_server.py
    python examples/bo_consolidated/offline_check.py tests/integration/test_bo_editorial.py tests/integration/test_bo_consolidated.py -q

The preview creates only temporary fixture databases/output and local illustrative exports.
It does not connect to the production/local historical database or perform paid inference.
The test-only PDF import stub fails if PDF extraction is attempted; PDF parsing/pagination
are outside these checks. No PDF or live model quality claim is made.

See `docs/bo-corrective-report.md` for the diagnosis, navigation evidence, test failures and
reference-image limitation. No reference screenshots were included with the task attachment.
