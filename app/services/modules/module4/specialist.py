"""Module 4 Specialist Agent orchestration (Business Overview Architecture V5).

Ties the three pieces together:

1. Assemble the ALLOWED inputs only -- the shared SEC 10-K evidence + structured
   financial data. Module 4 does NOT receive Modules 1/2/3 outputs.
2. Run the registered ``module4_debt_structure_specialist`` prompt through the
   single :class:`LLMClient` via its existing ``analyze`` method (same pattern
   the other Business Overview specialist prompts use -- no new client method),
   which validates the raw output against the fixed
   :data:`app.schemas.module4.MODULE4_JSON_SCHEMA` BEFORE use.
3. Run the deterministic :class:`DebtStructureValidator` over the parsed output
   and attach the report; its check 7 ties every reported amount to a figure
   the filing passages or admitted facts state. When the filing tags its total
   debt (:mod:`.filed_total`), that figure replaces the model's total, and a
   tagged line bridging it to the face total replaces the model's reconciling
   items, so only the instruments are left to the model. Reconciling items are
   dropped first when the
   instruments alone already match the reported total (they would double-count).
   When its reconciliation leaves a gap and no tagged bridge settles it, ask the model
   ONCE to explain the gap from the filing passages it was given; each item it
   returns counts only if its quote is verbatim in those passages (check 6).
   When the validator still fails, a MANDATORY escalation is raised (explicit
   rule id) so the failure is a real, queryable signal rather than silent prose.

This service never drafts term sheets, covenants or security agreements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.module4 import Module4Output, ReconciliationFollowUp
from app.services.escalation.engine import EscalationEngine
from app.services.escalation.rules import EscalationCategory, Severity
from app.services.llm.client import LLMClient, ModelRunResult
from app.services.modules.module4.prompt import MODULE4_AGENT_NAME, MODULE4_RECONCILIATION_NAME
from app.services.modules.module4.debt_structure_validator import (
    CHECK_RECONCILIATION,
    RECONCILING_ITEMS_REVIEW_SHARE,
    DebtStructureValidator,
    DebtStructureValidatorReport,
)
from app.services.modules.module4.filed_total import FiledDebtTotal

# Explicit rule id for a Validator-8 failure on Module 4 output.
RULE_VALIDATOR8_FAILURE = "R-MODULE4-VALIDATOR8-01"


class Module4RejectedError(ValueError):
    """Raised when the Module 4 LLM output fails schema validation."""

    def __init__(self, message: str, *, error_type: str | None = None) -> None:
        super().__init__(message)
        # Set when the provider call itself failed, so there was no answer at all.
        self.error_type = error_type


@dataclass
class Module4Inputs:
    """The ONLY inputs the Module 4 specialist may receive.

    These are the shared, independent inputs: the 10-K evidence snippets and the
    structured financial data (debt schedule facts, cash-flow facts, etc.). No
    Module 1/2/3 output is included -- Module 4 is independent.
    """

    sec_filing_snippets: list[dict] = field(default_factory=list)
    structured_financials: list[dict] = field(default_factory=list)
    debt_schedule_facts: list[dict] = field(default_factory=list)
    missing_critical_evidence: list[str] = field(default_factory=list)
    # Issues of a failed first attempt; set only on its one retry.
    validation_feedback: list[str] = field(default_factory=list)
    # The filing's tagged total debt, which the schedule is reconciled to.
    filed_total: FiledDebtTotal | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sec_filing_snippets": self.sec_filing_snippets,
            "structured_financials": self.structured_financials,
            "debt_schedule_facts": self.debt_schedule_facts,
            "missing_critical_evidence": self.missing_critical_evidence,
        }
        if self.filed_total is not None:
            payload["filed_debt_total"] = {
                "instruction": (
                    "The filing's tagged total debt. Report total_m as "
                    "consolidated_total_indebtedness_m. List every instrument at "
                    "its principal; when face_m is given they sum to face_m, and "
                    "the bridge line between face_m and total_m is added for you."),
                **self.filed_total.to_payload(),
            }
        if self.validation_feedback:
            payload["validation_feedback"] = {
                "instruction": (
                    "Your previous answer failed validation and was rejected. "
                    "Return your COMPLETE answer again after correcting every "
                    "listed issue, using only the filing passages and facts "
                    "provided. This is the only retry. If the schedule did not "
                    "reconcile, rebuild it row by row from the debt note's "
                    "schedule of instruments (not the fair value table) and "
                    "take the total from that same table."),
                "issues": list(self.validation_feedback),
            }
        return payload

    def filing_passages(self) -> dict[str, str]:
        """The filing text reconciling items are checked against (evidence id -> text)."""
        return {str(s["fact_id"]): s["text"] for s in self.sec_filing_snippets
                if s.get("fact_id") and s.get("text")}

    def filed_values_m(self) -> list[float]:
        """Admitted structured debt figures in $M, which reported amounts may also match."""
        values: list[float] = []
        for fact in self.structured_financials:
            value, unit = fact.get("value"), str(fact.get("unit") or "").lower()
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if "million" in unit:
                values.append(float(value))
            elif unit in ("usd", "iso4217:usd"):
                values.append(value / 1e6)
        return values

    def evidence_ids(self) -> list[str]:
        ids: list[str] = []
        for item in (
            *self.sec_filing_snippets,
            *self.structured_financials,
            *self.debt_schedule_facts,
        ):
            fid = item.get("fact_id") or item.get("id") or item.get("source_id")
            if fid:
                ids.append(str(fid))
        return ids


@dataclass
class Module4Result:
    """A completed Module 4 run: parsed output, validator report, provenance."""

    output: Module4Output
    validator8: DebtStructureValidatorReport
    run: ModelRunResult
    escalation_id: str | None = None
    # The reconciliation follow-up, when one was made (see Module4Specialist._reconcile).
    reconciliation_followup: dict[str, Any] | None = None
    # Reconciling items dropped because the instruments already matched the total.
    dropped_reconciling_items: list[dict[str, Any]] = field(default_factory=list)
    # The tagged total applied over the model's, with what the model had said.
    filed_total: dict[str, Any] | None = None

    @property
    def validated(self) -> bool:
        """True when Validator 8 passed every deterministic check."""
        return self.validator8.passed


class Module4Specialist:
    """Run the Module 4 specialist agent + Validator 8."""

    def __init__(
        self,
        client: LLMClient,
        *,
        validator: DebtStructureValidator | None = None,
        escalation_engine: EscalationEngine | None = None,
        case_id: str | None = None,
        enforce_validator: bool = True,
    ) -> None:
        self._client = client
        self._validator = validator or DebtStructureValidator()
        self._escalation = escalation_engine
        self._case_id = case_id
        # False (advisory): Validator 8 still reports, but its failure neither
        # triggers the reconciliation follow-up nor raises an escalation.
        self._enforce = enforce_validator

    def run(
        self,
        inputs: Module4Inputs,
        *,
        case_version: int | None = None,
        key: str | None = None,
    ) -> Module4Result:
        """Produce schema-validated Module 4 output + a Validator 8 report.

        Raises :class:`Module4RejectedError` if the LLM output fails schema
        validation (rejection is logged by the client). A Validator 8 failure
        does NOT raise -- it is reported on the result and raises a mandatory
        escalation so a human reviews it.
        """
        run = self._client.analyze(
            inputs.to_payload(),
            evidence_ids=inputs.evidence_ids(),
            case_id=self._case_id,
            case_version=case_version,
            prompt_name=MODULE4_AGENT_NAME,
            key=key,
        )
        if not run.is_valid or run.parsed is None:
            raise Module4RejectedError(
                "Module 4 LLM output failed schema validation and was rejected "
                "before use.",
                error_type=run.error_type,
            )

        output = _in_maturity_order(Module4Output.model_validate(run.parsed))
        output, filed = self._with_filed_total(output, inputs.filed_total)
        output, dropped = self._without_unneeded_items(output)
        passages = inputs.filing_passages()
        tagged = _tagged_items(inputs)
        report = self._validator.validate(output, filing_passages=passages,
                                          filed_values_m=inputs.filed_values_m(),
                                          tagged_items=tagged)
        followup = None
        # With a tagged bridge, a remaining gap is in the instruments, which the
        # follow-up may not change: it goes to the retry instead.
        if (self._enforce and not report.check(CHECK_RECONCILIATION).passed and passages
                and not tagged):
            output, report, followup = self._reconcile(
                inputs, output, report, case_version=case_version, key=key)
        escalation_id = self.escalate_validator_failure(report) if self._enforce else None
        return Module4Result(
            output=output,
            validator8=report,
            run=run,
            escalation_id=escalation_id,
            reconciliation_followup=followup,
            dropped_reconciling_items=dropped,
            filed_total=filed,
        )

    def _with_filed_total(self, output: Module4Output, filed: FiledDebtTotal | None):
        """Apply the tagged total, except where no tagged bridge ties it to the face total
        and the model's total is the face total its instruments reconcile to.

        EHC FY2025's debt table totals at face (2,518.5) and tags no costs line, so
        its tagged carrying total (2,490.8) would leave the model's correct schedule
        27.4 short. A total within ``RECONCILING_ITEMS_REVIEW_SHARE`` of the tagged
        one is that face total; one further off (CYH's 8,637 against 10,396, an
        incomplete schedule summed to itself) is not, and the tagged total stands.
        """
        if filed is not None and filed.bridge is None:
            model_total = output.deliverable_1.creditor_priority_framework.consolidated_total_indebtedness_m
            keep = (abs(model_total - filed.total_m) <= RECONCILING_ITEMS_REVIEW_SHARE * filed.total_m
                    and self._validator.validate(output).check(CHECK_RECONCILIATION).passed)
            return _with_filed_total(output, filed, keep_model_total=keep)
        return _with_filed_total(output, filed)

    def _without_unneeded_items(
        self, output: Module4Output,
    ) -> tuple[Module4Output, list[dict[str, Any]]]:
        """Drop reconciling items when the instruments alone already reconcile.

        Reconciling items only bridge principal to a carrying-value total. When
        the instruments' principal already matches the reported total (it is the
        face amount), any item listed would double-count, so all are dropped and
        returned for the audit trail.
        """
        d1 = output.deliverable_1
        if not d1.reconciling_items:
            return output, []
        bare = output.model_copy(update={
            "deliverable_1": d1.model_copy(update={"reconciling_items": []})})
        if not self._validator.validate(bare).check(CHECK_RECONCILIATION).passed:
            return output, []
        return bare, [i.model_dump(mode="json") for i in d1.reconciling_items]

    def _reconcile(self, inputs: Module4Inputs, output: Module4Output,
                   report: DebtStructureValidatorReport, *, case_version, key):
        """One follow-up asking the model to explain the reconciliation gap from the filing.

        Only the reconciling items it returns are taken (the schedule is never
        changed), and Validator 8 counts each one only if its quote is verbatim in
        the filing passages and states its amount. Any failure of the call keeps
        the first answer and its report as they were.
        """
        observed = report.check(CHECK_RECONCILIATION).observed
        d1 = output.deliverable_1
        payload = {
            "reported_total_m": observed["reported_total_m"],
            "tranche_sum_m": observed["tranche_sum_m"] + observed["reconciling_items_m"],
            "gap_m": observed["gap_m"],
            "debt_schedule": {
                "senior_notes_schedule": [t.model_dump(mode="json") for t in d1.senior_notes_schedule],
                "non_note_obligations_schedule": [
                    o.model_dump(mode="json") for o in d1.non_note_obligations_schedule],
                "reconciling_items": [i.model_dump(mode="json") for i in d1.reconciling_items],
            },
            "sec_filing_snippets": inputs.sec_filing_snippets,
        }
        record: dict[str, Any] = {"gap_m": observed["gap_m"]}
        try:
            run = self._client.analyze(
                payload, evidence_ids=inputs.evidence_ids(), case_id=self._case_id,
                case_version=case_version, prompt_name=MODULE4_RECONCILIATION_NAME,
                key=f"{key or 'm4_debt'}_reconcile")
        except Exception as exc:  # a provider failure leaves the first answer standing
            record.update(status="error", reason=type(exc).__name__)
            return output, report, record
        record["run_id"] = getattr(run, "run_id", None)
        if not run.is_valid or run.parsed is None:
            record.update(status="rejected", reason="The answer failed schema validation.")
            return output, report, record
        answer = ReconciliationFollowUp.model_validate(run.parsed)
        d1 = d1.model_copy(update={"reconciling_items": [*d1.reconciling_items,
                                                         *answer.reconciling_items]})
        output = output.model_copy(update={"deliverable_1": d1})
        report = self._validator.validate(output, filing_passages=inputs.filing_passages(),
                                          filed_values_m=inputs.filed_values_m())
        after = report.check(CHECK_RECONCILIATION)
        record.update(status="answered", proposed_items=len(answer.reconciling_items),
                      unexplained=answer.unexplained, reconciled=after.passed,
                      gap_after_m=after.observed["gap_m"])
        return output, report, record

    def escalate_validator_failure(
        self, report: DebtStructureValidatorReport
    ) -> str | None:
        """Raise a mandatory escalation when Validator 8 fails (explicit rule id)."""
        if report.passed or self._escalation is None:
            return None
        reason = "Validator 8 failed: " + "; ".join(
            f"[{c.check_id}] {c.detail}" for c in report.failures
        )
        escalation = self._escalation.raise_escalation(
            rule_id=RULE_VALIDATOR8_FAILURE,
            category=EscalationCategory.DATA_INTEGRITY,
            severity=Severity.MANDATORY,
            reason=reason,
            evidence_refs=[c.check_id for c in report.failures],
            case_id=self._case_id,
        )
        return escalation.escalation_id


def _tagged_items(inputs: Module4Inputs) -> tuple:
    filed = inputs.filed_total
    return (filed.bridge,) if filed is not None and filed.bridge is not None else ()


def _with_filed_total(
    output: Module4Output, filed: FiledDebtTotal | None, *, keep_model_total: bool = False,
) -> tuple[Module4Output, dict[str, Any] | None]:
    """Put the filing's tagged total (and its tagged bridge, if any) in place of the model's.

    The drag ratio is recomputed over the new total from the model's own Tier 1
    figure. Returns the record of what was replaced, for the audit trail.
    """
    if filed is None:
        return output, None
    d1 = output.deliverable_1
    framework = d1.creditor_priority_framework
    record = {**filed.to_payload(),
              "applied": not keep_model_total,
              "model_total_m": framework.consolidated_total_indebtedness_m,
              "model_reconciling_items": [i.model_dump(mode="json") for i in d1.reconciling_items]
              if filed.bridge is not None else None}
    if keep_model_total:
        return output, record
    framework = framework.model_copy(update={
        "consolidated_total_indebtedness_m": filed.total_m,
        "structural_subordination_drag_ratio": (
            framework.tier_1_direct_opco_secured_m / filed.total_m if filed.total_m > 0
            else framework.structural_subordination_drag_ratio),
    })
    update: dict[str, Any] = {"creditor_priority_framework": framework}
    if filed.bridge is not None:
        update["reconciling_items"] = [filed.bridge]
    return output.model_copy(update={"deliverable_1": d1.model_copy(update=update)}), record


def _in_maturity_order(output: Module4Output) -> Module4Output:
    """List the senior notes by maturity year (stable), as Validator 8's check 3 expects.

    The order is presentation only: the model sometimes lists tranches as the
    filing's table does, which is not always chronological.
    """
    d1 = output.deliverable_1
    ordered = sorted(d1.senior_notes_schedule, key=lambda t: t.maturity_year)
    if ordered == d1.senior_notes_schedule:
        return output
    return output.model_copy(update={
        "deliverable_1": d1.model_copy(update={"senior_notes_schedule": ordered})})
