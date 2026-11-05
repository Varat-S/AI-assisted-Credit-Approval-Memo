# Offline Pipeline Viewer fixtures

These files support presentation and integrity tests. They do not establish live-model analytical accuracy.

- BO and RMS records are explicitly synthetic teaching records. The unresolved challenge, pending review, RMS blocking gate and accepted-review warning are deliberate recorded states.
- The M4 assessment reproduces `examples/bo_m4/m4_analysis.sample.json`; its illustrative schedule and conclusions are not independently verified by the viewer.
- FO reproduces the trimmed recorded excerpt in `tests/fixtures/rms/hca_fy2025_fo.json`. A disclosure identifies the fixture run identity; no measures or scores were recomputed.
- M3 contains byte-stable outputs from the existing offline registry fixture: the deterministic educational structure and scripted, reviewed management assessment. The M3 manifest records the component file hashes.
- Run IDs are intentionally distinct. Selecting an RMS run exposes only its explicitly named BO/FO source artifacts. A shared case name never joins other runs automatically.

The viewer reads these files directly. Opening a node does not seed a database, generate artifacts, invoke a backend, reassess RMS or record review decisions. Downloads preserve the exact fixture bytes; normalized slices are labelled separately.
