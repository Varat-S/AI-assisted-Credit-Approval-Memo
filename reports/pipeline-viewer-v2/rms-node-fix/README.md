# RMS stage binding

The saved RMS assessment existed, but the graph displayed both its artifact node and a separate architecture-only RMS stage. Selecting that second node opened an empty panel.

The canonical `architecture.rms` stage now binds to the recorded `rms` producer output before extra artifact nodes are added. This keeps one visible RMS stage, preserves existing stage links and recorded artifact URLs, and retains a clearly illustrative node only when the selected scope has no RMS output.

For the saved HCA workflow, the stage opens `rms.assessment.rms-6f22d8a09ce34b03`. Its result is `capacity_only`, provisional, with pending human review and recorded RMS-G02, RMS-G05 and RMS-G06 gates. No assessment, score, policy or review status was recalculated or changed.

Verification: 124 focused tests passed, including combined-workflow, individual RMS-run and BO-only scope regressions. Browser inspection confirms the main RMS stage opens the recorded report and no duplicate RMS stage remains. All 248 original archive checksums still pass. No model calls were made.
