# FO visibility in a recorded end-to-end workflow

The saved HCA FO results existed throughout the run. The supplied link selected the BO's `ar_b66059ab02864a03` stage run, so FO stage nodes appeared as architecture-only placeholders. The graph now distinguishes an **Entire workflow** from an **Individual stage run**.

The entire-workflow view reads BO, FO and RMS run bindings from the selected durable job record using a read-only SQLite connection. It does not initialize or modify a database, regenerate results, join by case name, or choose the latest stage run. Individual-run graph URLs retain their original semantics. When the old UI link names a run belonging to exactly one recorded workflow, the UI opens that workflow; ambiguous bindings require explicit selection. Choosing an individual run is preserved on reload with `scope=run`.

Saved HCA workflow:

- Workflow: `11cf252529624e38a90e3b22eb4a8908`
- BO: `ar_b66059ab02864a03`
- FO: `fo-10c3c998d77144db`
- RMS: `rms-6f22d8a09ce34b03`
- [Combined graph](http://127.0.0.1:8018/pipeline?case=HCA_E2E_20261105T074500Z&workflow_id=11cf252529624e38a90e3b22eb4a8908)

Pre-checks, seven financial measures, triggers, provisional scoring and the FO overview all resolve to the same saved FO run in the combined view. Existing validation qualifications and review escalations are retained.

Changes: `workflow_scope.py` adds read-only job reference discovery; graph/explorer/API accept an explicit workflow scope; the selector and URL distinguish workflows from individual runs. No analytical artifact schemas, model outputs, scores or review decisions changed.

Verification: 121 focused regressions passed, including nine new workflow-scope cases covering all five FO stage reports, explicit individual-run scope, unrelated and missing FO outputs, conflicting/foreign workflow references, RMS/source reference disagreement, ambiguous workflow choices, and read-only access. Browser checks at desktop and mobile widths confirm the old deep link opens the recorded workflow, FO Seven Measures opens a substantive report, all three tabs work, and explicit FO-only selection survives reload. The original saved archive's 248 checksums remain unchanged. No models were run.
