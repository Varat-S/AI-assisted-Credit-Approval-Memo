# Native UI Business Overview

Open `gallery.html` for the actual existing Workspace/Setup reference pages and revised
Business Overview desktop/mobile screenshots. `newly-completed.html` and `historical.html`
render the previously saved artifacts using the same workspace/memo design tokens.
No analytical JSON, audit or prior run was regenerated for this presentation change.

The read-only app preview uses existing isolated offline fixture stores:

    python examples/bo_native_style/preview_server.py /path/to/existing/bo-corrective-fixture-store

It listens on localhost:8772, blocks write requests and forbids live inference/acquisition.
It does not seed or run analyses. Current sample metadata clearly labels synthetic/example
sources and human review requirements. The original structure diagram's colours/content
remain intact; surrounding report styling follows the site's own light/dark theme.

See `docs/bo-native-style-report.md` for modified files, token mappings, test results,
navigation evidence and preservation checks. Verification logs include the initial aborted
single-process test run and both successfully completed isolated groups.
