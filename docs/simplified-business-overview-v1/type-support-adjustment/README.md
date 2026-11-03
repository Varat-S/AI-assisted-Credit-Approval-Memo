# Statement type and evidence support

Presentation policy: `bo-finding-display-2.0.0`. Replaces the display mapping at local checkpoint `Before-Inference-Assumption-Adj` (`ad7d618`). No canonical finding, analytical wording, validation disposition, source binding or review outcome is rewritten.

Future specialist prompts also define Assumption as an explicitly adopted unverified premise, replacing the old "not evidenced" definition. Weak analytical conclusions remain Inference with evidence limitations recorded through the existing disposition and explanation fields. Prompt hashes change for future executions; no new execution or historical rewrite is performed here.

The main memo shows statement type only: Fact, Inference or Assumption. Evidence → Validation Assessment independently shows Supported, Qualified or Unsupported and the reason for each field. Missing field-level validation is disclosed rather than invented.

- Fact and calculated-fact records retain Fact. Management statements describe reported statements, not independent confirmation of their underlying outcome; attribution qualifies support.
- A recorded quote-coverage flag identifies a conclusion not stated by the quotation: display Inference, with support not established by that cited record. The flag is explicitly identified as a heuristic, and the original validator disposition is retained. A literal verified quotation retains Fact, with the conflicting flag disclosed as Qualified.
- Hypothetical risk language qualifies the disclosure's context; it does not automatically become Assumption.
- Assumption requires the specialist's explicit assumption type, or credit text explicitly marked `Assumption:` throughout that field. Ordinary future/conditional language is insufficient.
- Credit Implication is classified independently: direct verified quotation can be Fact; explicitly adopted premises can be Assumption; analytical credit effects are Inference. A finding labelled Assumption does not automatically make its credit conclusion an Assumption.
- A credit inference with no separate field-level review remains Qualified; a conclusion dependent on an unsupported finding, with no separately recorded support, is Unsupported in this display assessment. This is not a new semantic or specialist validation.

## Offline replay

Read five persisted runs through the strict selected-run reader. Compare the checkpoint's assessment function with the revised read-only view. No model calls or historical artifact writes.

The [replay results](offline-replay.json) cover 39 selected findings. Before: 17 Fact, 16 Inference, 6 Assumption. After: 18 Fact, 21 Inference, 0 Assumption. The sample contains no selected finding explicitly recorded as an assumption. Support: 22 Supported, 14 Qualified, 3 Unsupported. These counts are observations, not quotas.

`M1S5-H002` in `ar_888bced33fbd43b9` now displays Inference / Unsupported for Finding and Credit Implication. Its frozen `claim_type: fact` and validator disposition `qualified` are preserved for audit.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 ../alan-branch-test/.venv/bin/python -m pytest -q -x --tb=short tests/unit/test_bo_finding_assessment.py tests/unit/test_bo_competitive_presentation.py tests/unit/test_bo_evidence_presentation.py tests/unit/test_bo_original_highlight.py tests/integration/test_business_overview_browser_e2e.py tests/integration/test_bo_four_section_renderer.py
```

72 passed. Classification tests cover direct disclosures, calculations, hypothetical risks, management attribution, explicit premises, independent field types, quote-coverage conflicts and immutable source records. Existing integration tests retain frozen-artifact equality, source integrity and read-without-inference checks. The classification unit suite passed again after clarifying the explanation for an unverified/rejected record without a quote-coverage flag (13 passed).

After updating future specialist prompt definitions, reran the command above with `tests/unit/test_bo_source_selection.py` added: **88 passed**.
