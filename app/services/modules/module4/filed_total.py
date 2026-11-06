"""The filing's own total debt, read from its tagged XBRL facts (no LLM).

Module 4's reconciliation used to test the debt schedule against a total the
model picked, and the model picked different lines on different runs (the face
total, the carrying total, long-term debt less current maturities, the fair
value table). The total is a tagged figure, so it is read here instead and the
schedule is tested against it.

Filers tag the same figures under different concepts, so the carrying total
(net of issuance costs and discounts, what the debt note calls "Total debt") is
taken from the first of :data:`TOTAL_CONCEPTS` with an undimensioned figure at
the latest period end:

* HCA FY2025: ``DebtLongtermAndShorttermCombinedAmount`` 46,492 (its
  ``LongTermDebt`` 44,285 leaves out commercial paper, hence the order);
* CYH FY2025: ``DebtAndCapitalLeaseObligations`` 10,396;
* UHS FY2025: ``LongTermDebt`` 4,752.551 (also tagged 4,800 from prose; the
  bridge below picks the figure);
* EHC FY2025: ``DebtAndCapitalLeaseObligations`` 2,490.8.

When the filing also tags the instruments' face total and the costs line
between the two, and face less costs is the carrying total, that line is the
schedule's reconciling item: HCA 46,928 less 436, CYH 10,613 less 217, UHS
4,768.261 less 15.71. Filers tag the face total as ``DebtInstrumentCarryingAmount``
as often as ``DebtInstrumentFaceAmount``, so either counts, and only the
three-way tie confirms it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.module4 import ReconcilingItem, ReconcilingItemKind

# In priority order: the first with a figure is the total.
TOTAL_CONCEPTS = (
    "DebtLongtermAndShorttermCombinedAmount",
    "DebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "LongTermDebt",
)
FACE_CONCEPTS = ("DebtInstrumentCarryingAmount", "DebtInstrumentFaceAmount")
COSTS_CONCEPTS = (
    "DebtInstrumentUnamortizedDiscountPremiumAndDebtIssuanceCostsNet",
    "DeferredFinanceCostsNet",
    "UnamortizedDebtIssuanceExpense",
)
# Face less costs must land within this many $M of the total to tie.
BRIDGE_TOLERANCE_M = 1.0


@dataclass(frozen=True)
class FiledDebtTotal:
    """The filing's total debt in $M, and the tagged line bridging it to the face total."""

    total_m: float
    concept: str
    fact_id: str
    period_end: str
    face_m: float | None = None
    bridge: ReconcilingItem | None = None

    def to_payload(self) -> dict:
        return {
            "total_m": self.total_m, "concept": self.concept, "fact_id": self.fact_id,
            "period_end": self.period_end, "face_m": self.face_m,
            "bridge": self.bridge.model_dump(mode="json") if self.bridge else None,
        }


@dataclass(frozen=True)
class _Fact:
    concept: str
    value_m: float
    fact_id: str
    period_end: str
    label: str


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _value_m(fact: dict) -> float | None:
    """The fact's value in $M, or None if it is not a plain dollar figure."""
    value = fact.get("normalized_value", fact.get("value"))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    unit = str(fact.get("normalized_unit") or fact.get("unit") or "").lower()
    if "million" in unit:
        return float(value)
    if unit in ("usd", "iso4217:usd"):
        return value / 1e6
    return None


def _candidates(facts) -> list[_Fact]:
    """Undimensioned dollar figures under the total, face and costs concepts."""
    wanted = {*TOTAL_CONCEPTS, *FACE_CONCEPTS, *COSTS_CONCEPTS}
    out = []
    for fact in facts or ():
        if not isinstance(fact, dict) or fact.get("dimensions"):
            continue
        concept = _local_name(str(fact.get("name") or fact.get("concept") or ""))
        value = _value_m(fact)
        fid = fact.get("fact_id") or fact.get("id")
        period = fact.get("period_end") or fact.get("period")
        if concept in wanted and value is not None and fid and period:
            out.append(_Fact(concept, value, str(fid), str(period),
                             str(fact.get("source_label") or concept)))
    return out


def _bridge(total: _Fact, faces: list[_Fact], costs: list[_Fact]):
    """(face fact, reconciling item) when face less a tagged costs line is the total."""
    for face in faces:
        for cost in costs:
            amount = abs(cost.value_m)
            for signed in (-amount, amount):  # costs and discounts reduce; a net premium adds
                if abs(face.value_m + signed - total.value_m) <= BRIDGE_TOLERANCE_M:
                    kind = (ReconcilingItemKind.ISSUANCE_COSTS_AND_DISCOUNTS if signed < 0
                            else ReconcilingItemKind.UNAMORTIZED_PREMIUM)
                    item = ReconcilingItem(
                        kind=kind, label=cost.label, amount_m=signed,
                        quote=f"XBRL {cost.concept} {cost.value_m:,.3f} ({cost.period_end})",
                        evidence_id=cost.fact_id)
                    return face, item
    return None


def filed_debt_total(facts) -> FiledDebtTotal | None:
    """The filing's total debt at its latest period end, or None when it tags no usable one.

    A concept tagged with two different figures and no bridge to settle which is
    the total is passed over for the next concept rather than guessed.
    """
    candidates = _candidates(facts)
    totals = [f for f in candidates if f.concept in TOTAL_CONCEPTS]
    if not totals:
        return None
    period = max(f.period_end for f in totals)
    at = [f for f in candidates if f.period_end == period]
    faces = [f for f in at if f.concept in FACE_CONCEPTS]
    costs = [f for f in at if f.concept in COSTS_CONCEPTS]
    for concept in TOTAL_CONCEPTS:
        tagged = [f for f in at if f.concept == concept]
        for total in tagged:
            bridged = _bridge(total, faces, costs)
            if bridged:
                face, item = bridged
                return FiledDebtTotal(total.value_m, concept, total.fact_id, period,
                                      face_m=face.value_m, bridge=item)
        if len({f.value_m for f in tagged}) == 1:
            total = tagged[0]
            return FiledDebtTotal(total.value_m, concept, total.fact_id, period)
    return None
