# Offline consolidated BO sample

These are scripted/synthetic infrastructure fixtures, **not live HCA credit analysis**.
`generate_offline.py` replays the existing BO pipeline over admitted test evidence, with
the existing debt specialist fixture and the new competitive selection fixture. It
blocks outbound sockets and PDF extraction, disables local .env loading, and uses an
isolated in-memory database and temporary output directory. No paid model is called.

- `consolidated.json`: validated five-section artifact with exact-run provenance.
- `audit.json`: separate full recorded specialist, selection, validation and challenge trail.
- `artifact.schema.json` / `competitive.schema.json`: typed contract exports.
- `preview.html`: standalone memo; `review-preview.html`: existing Review interface.
- `desktop.jpg` / `mobile.jpg`: browser screenshots of the static Review fixture.
- `verification/`: executed test results, including independently reproduced baseline failures.

Management and corporate structure are intentionally unavailable in this sample. The
Industry section explicitly marks the absence of a standalone industry report and
preserves all available governed findings. No missing content or approval is fabricated.
The Module 4 fixture is HCA-shaped FY2025 test data; the synthetic BO case uses the
repository's `NFH_BO` test identity. This is clearly labelled offline simulation, not a
real borrower run or evidence package.

From the repository root, with the project's existing Python dependencies:

    python examples/bo_consolidated/generate_offline.py
    python examples/bo_consolidated/offline_check.py tests/integration/test_bo_consolidated.py -q

The checker blocks network/PDF extraction because the exercised fixture slice needs
neither. The optional PDF package in the shared local environment stalled on import;
this guard is test tooling, not an application workaround. PDF parsing tests must use
an ordinary complete environment and are not covered by these results.

Open either HTML file locally, or serve this directory on localhost. Navigation links
in the static Review preview illustrate real app routes; they require the running app
and are not a second application. No live run is needed to inspect these artifacts.
