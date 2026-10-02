"""HTTP contracts for the measurement engine.

Thin. Every number here is validated and computed by
:mod:`app.measurement`; these schemas exist to carry values in and out, not to
decide anything.

Note on serialisation: Pydantic emits ``Decimal`` in JSON as a **string**
(``"4.6"``), and deliberately so. A JSON number is a double, and round-tripping
4.6 through a double is exactly the loss of precision the measurement engine
exists to prevent. The strings are exact and parse to ``Decimal`` without loss.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.measurement.units import Unit

ScaleDirection = Literal["actual_to_drawing", "drawing_to_actual"]


class UnitConversionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal
    from_unit: Unit
    to_unit: Unit


class UnitConversionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal
    unit: Unit
    """The unit of ``value``."""


class ScaleConversionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal = Field(description="A length in millimetres.")
    direction: ScaleDirection
    scale_denominator: int = Field(
        gt=0, description="The N in 1:N. 50 means the drawing is 1:50."
    )


class ScaleConversionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal
    unit: Literal["mm"] = "mm"
    direction: ScaleDirection
    scale_denominator: int
