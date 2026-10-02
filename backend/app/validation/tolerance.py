"""Tolerance policy.

STRICT BY DEFAULT
-----------------
The default policy is exact: zero tolerance on every measured quantity. A
student drawing 84 mm when 84 mm is required passes; drawing 84.05 mm does not.

That is deliberately unforgiving. The product's claim is that it can tell a
student precisely what is wrong, and a default that quietly forgives half a
millimetre would undermine that claim in the one direction that matters: it
would tell a student a wrong drawing was right. Tolerance is therefore
**configurable and always reported**, never implicit.

Note the asymmetry: a drawing is a *digital* submission, so 0.05 mm of slop is
a modelling decision by the student, not the tremor of a hand. When hand-
drawn work is supported later, it gets its own policy rather than loosening this
one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class TolerancePolicy:
    """Absolute tolerances, stated in the units of the thing they judge.

    Two different units live here, and conflating them is a real bug rather
    than a naming quibble. Every field below except ``dimension_label_mm``
    judges a length **drawn on the sheet**, so it is in paper millimetres.
    ``dimension_label_mm`` judges a **typed** figure -- the number a student
    wrote inside a dimension's text -- which is a real-world millimetre value
    and is never divided by the scale.

    A 1 mm paper tolerance and a 1 mm label tolerance are different questions.
    At 1:50, 1 mm of paper is 50 mm of building; the same number in the two
    places means a fifty-fold difference in what is forgiven.
    """

    room_dimension_mm: Decimal = ZERO
    wall_thickness_mm: Decimal = ZERO
    opening_width_mm: Decimal = ZERO
    opening_placement_mm: Decimal = ZERO
    dimension_mm: Decimal = ZERO
    dimension_label_mm: Decimal = ZERO
    """Tolerance on a dimension's written number, in **real-world** millimetres.

    Defaults to strict. A label is a declared value, not a measured one, so the
    default is to hold it to exactly what the brief asked for.
    """

    @classmethod
    def strict(cls) -> "TolerancePolicy":
        """Exact comparison everywhere. The MVP default."""
        return cls()

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TolerancePolicy":
        """Build a policy from a request, defaulting every field to strict.

        Unknown keys are rejected rather than ignored: a client sending
        ``{"room_dimension_mm": 5, "room_dimention_mm": 5}`` has a typo, and
        silently honouring neither would hand back a stricter verdict than the
        client asked for.
        """
        if not payload:
            return cls.strict()
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(payload) - known
        if unknown:
            raise ValueError(
                f"unknown tolerance field(s): {', '.join(sorted(unknown))}"
            )
        values: dict[str, Decimal] = {}
        for name, raw in payload.items():
            try:
                value = Decimal(str(raw))
            except Exception as exc:  # noqa: BLE001 - re-raised as ValueError
                raise ValueError(f"tolerance {name} is not a number: {raw!r}") from exc
            if value < 0:
                raise ValueError(f"tolerance {name} cannot be negative: {value}")
            values[name] = value
        return cls(**values)

    def to_dict(self) -> dict[str, Decimal]:
        return {
            "room_dimension_mm": self.room_dimension_mm,
            "wall_thickness_mm": self.wall_thickness_mm,
            "opening_width_mm": self.opening_width_mm,
            "opening_placement_mm": self.opening_placement_mm,
            "dimension_mm": self.dimension_mm,
            "dimension_label_mm": self.dimension_label_mm,
        }
