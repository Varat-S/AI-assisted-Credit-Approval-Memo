# Informational Business Model specialist

New browser Business Overview runs generate a brief neutral Business Model description,
including operating inputs and costs, after the analytical BO run and handoff are saved.
The approved prompt and JSON response schema live in `app/prompts/business_model.py`.
The UI displays the description before Corporate Structure & Debt Obligations, in the
combined memo, Business Overview page and print view. Each paragraph has the existing
collapsible evidence panel and verified-original-source highlighting.

## Isolation and evidence

`app/services/bo/business_model.py` selects only admitted passages from Items 1, 7 and 8
of the selected period's primary 10-K. It cannot receive another agent's output or a
proxy/exhibit. Selection preserves whole passages; omitted IDs are recorded when the
650 KB evidence budget is exceeded. The model targets 130–180 words in one or two
paragraphs; a 60–220 word display bound permits modest variation.

Every sentence requires evidence IDs and exact quotations. Schema, selected-source
membership and exact quote occurrence are checked before display. These checks do
not prove semantic entailment or neutrality; those remain model instructions and
review matters. Rejected output is withheld, never substituted with an ungrounded
fallback. Missing evidence produces an explicit unavailable state.

The model call uses the existing LLMClient, versioned prompt registry, selected
narrow model and model-run logging. A separate append-only stage named
`informational_business_model:<analysis_run_id>` binds output to the exact run and
canonical evidence hash. It is never added to the frozen analytical memo, BO
handoff, hypothesis roster, FO inputs or RMS inputs. Informational failure does
not invalidate completed credit analysis. Memo reads never call a model.

Legacy runs do not initiate paid calls on opening. An explicitly requested
backfill can call `run_description(session, analysis_run_id, backend)` and commit;
subsequent calls return the recorded artifact without paying again. Raw analytical
artifacts and scores are unchanged.

## Verification

`tests/unit/test_business_model.py` covers source selection, missing evidence,
quote/schema rejection, run binding, idempotence and input immutability.
`tests/integration/test_business_model_presentation.py` checks section order,
numbering, evidence controls, print rendering and unchanged analytical artifacts.
