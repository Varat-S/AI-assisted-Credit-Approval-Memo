# Reviewed partial Management publication

The latest HCA run `ar_255899f2c3c1434e` produced a valid partial management artifact with seven profiles and five reviewed observations, but the producer row was labelled `rejected` solely because completion was partial. The four-section assembler already supports reviewed partial artifacts, but correctly refuses rejected producers.

The fix is in `app/services/bo/m3_rebuild/provider.py`: validate the filtered artifact schema before recording its producer status, and record a valid filtered artifact as `valid` for either complete or partial completion. Completeness remains separately recorded as `partial`, with limitations and rejected claims retained in the audit. This does not mark every raw claim accepted, change specialist reasoning or disable the management reviewer.

The assembler, exact-run source bindings, hash checks, evidence panels, review status and four-section page design are unchanged. A failed Validator 7 review still withholds Management, while supported sections remain visible. Historical frozen memos are not regenerated or backfilled. The fix applies to newly executed analyses.

Verification includes a real offline New Analysis run containing an unsupported fact and unsupported judgment alongside accepted management observations. Its final memo retains the exact filtered partial artifact, profiles and supported observations, excludes unsupported content from the initial page, preserves limitations and remains incomplete/pending review. A separate failed-review case proves Management is still withheld when Validator 7 fails.

The actual saved HCA artifact was also schema-validated and passed through the corrected producer recorder using an in-memory clone of its producer row. Its five reviewed observations remained unchanged, completion remained partial, and the corrected producer status became valid. The production database was opened read-only for this proof; no historical record was edited.

Test results and restart confirmation follow.

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/integration/test_business_overview_browser_e2e.py tests/m3_rebuild/test_validator7_claims.py tests/m3_rebuild/test_credit_specialist.py tests/integration/test_bo_four_section.py tests/integration/test_bo_four_section_renderer.py
```

**100 passed in 51.26s.**

After adding the failed-review publication regression:

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/integration/test_business_overview_browser_e2e.py tests/m3_rebuild/test_shared_input_integration.py tests/m3_rebuild/test_integration.py
```

**40 passed in 18.72s**, including 16 cases already covered by the first command: **124 distinct passing cases**. Only the pre-existing Starlette/httpx deprecation warning remains. `git diff --check` passes.

The local server was restarted on port 8000 after confirming no active analyses. No live inference, SEC acquisition, dependency installation, commits, pushes, merges or historical report writes were performed.
