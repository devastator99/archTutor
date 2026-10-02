"""Measurement engine tests.

These pin the numerical correctness of the component the whole product rests
on. Every example in the specification is asserted verbatim, and the invalid
input cases matter as much as the valid ones: a measurement engine that
silently coerces bad input is worse than one that refuses it, because the
result would be a confidently wrong drawing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.measurement import (
    DRAWING_READING_RESOLUTION_MM,
    SUPPORTED_SCALES,
    SUPPORTED_UNITS,
    InvalidDimensionError,
    InvalidScaleError,
    InvalidToleranceError,
    InvalidUnitError,
    actual_to_drawing,
    calculate_scale,
    convert_unit,
    drawing_to_actual,
    format_scale,
    mm,
    to_actual_mm,
    to_decimal,
    validate_scale,
    within_tolerance,
)


class TestSpecificationExamples:
    """The exact examples from the engineering specification."""

    @pytest.mark.parametrize(
        ("actual_mm", "denominator", "expected"),
        [
            (4200, 50, "84.0"),
            (3600, 50, "72.0"),
            (230, 50, "4.6"),
            (900, 50, "18.0"),
        ],
    )
    def test_stated_examples(self, actual_mm, denominator, expected):
        assert actual_to_drawing(actual_mm, denominator) == Decimal(expected)

    def test_the_230_wall_is_4_6_and_not_5(self):
        """The single most important assertion in this file.

        A 230 mm wall at 1:50 is 4.6 mm on the sheet. Rounding it to 5 mm would
        fail a correct drawing by 0.4 mm of paper, which is 20 mm of building.
        """
        assert actual_to_drawing(230, 50) == Decimal("4.6")
        assert actual_to_drawing(230, 50) != Decimal("5")


class TestUnitConversion:
    @pytest.mark.parametrize(
        ("value", "from_unit", "to_unit", "expected"),
        [
            (4200, "mm", "cm", "420"),
            (420, "cm", "mm", "4200"),
            (4.2, "m", "mm", "4200"),
            (4200, "mm", "m", "4.2"),
            (4200, "mm", "mm", "4200"),
            (230, "mm", "cm", "23"),
            (230, "mm", "m", "0.23"),
            (1, "m", "cm", "100"),
            (1, "cm", "m", "0.01"),
        ],
    )
    def test_conversions(self, value, from_unit, to_unit, expected):
        assert convert_unit(value, from_unit, to_unit) == Decimal(expected)

    def test_supported_units_are_exactly_mm_cm_m(self):
        assert SUPPORTED_UNITS == ("mm", "cm", "m")

    def test_conversion_is_exact_not_approximate(self):
        # A float implementation gives 419.99999999999994 here.
        assert convert_unit("0.29", "m", "mm") == Decimal("290")
        assert convert_unit("4.2", "m", "mm") == Decimal("4200")

    def test_zero_is_a_valid_length(self):
        assert convert_unit(0, "mm", "cm") == Decimal(0)

    def test_negative_lengths_are_rejected(self):
        with pytest.raises(InvalidDimensionError):
            convert_unit(-1, "mm", "cm")

    def test_negative_may_be_explicitly_allowed_for_offsets(self):
        assert convert_unit(-1, "mm", "cm", allow_negative=True) == Decimal("-0.1")

    @pytest.mark.parametrize("bad", ["ft", "inch", "MM", "", "metres"])
    def test_invalid_units_are_rejected(self, bad):
        with pytest.raises(InvalidUnitError):
            convert_unit(10, bad, "mm")  # type: ignore[arg-type]
        with pytest.raises(InvalidUnitError):
            convert_unit(10, "mm", bad)  # type: ignore[arg-type]

    def test_invalid_unit_error_names_the_supported_units(self):
        with pytest.raises(InvalidUnitError, match="mm, cm, m"):
            convert_unit(1, "furlong", "mm")  # type: ignore[arg-type]

    def test_non_numeric_values_are_rejected(self):
        with pytest.raises(InvalidDimensionError):
            convert_unit("not a number", "mm", "cm")

    def test_non_finite_values_are_rejected(self):
        with pytest.raises(InvalidDimensionError):
            convert_unit(Decimal("NaN"), "mm", "cm")
        with pytest.raises(InvalidDimensionError):
            convert_unit(Decimal("Infinity"), "mm", "cm")

    def test_booleans_are_not_lengths(self):
        with pytest.raises(InvalidDimensionError):
            convert_unit(True, "mm", "cm")

    def test_to_actual_mm_normalises_any_unit(self):
        assert to_actual_mm(4.2, "m") == Decimal("4200")
        assert to_actual_mm(420, "cm") == Decimal("4200")
        assert to_actual_mm(4200) == Decimal("4200")


class TestScaleConversion:
    @pytest.mark.parametrize("denominator", SUPPORTED_SCALES)
    def test_every_supported_scale_converts(self, denominator):
        assert actual_to_drawing(4200, denominator) == Decimal(4200) / Decimal(
            denominator
        )

    def test_supported_scales_are_the_documented_set(self):
        assert SUPPORTED_SCALES == (20, 50, 100, 200, 500)

    @pytest.mark.parametrize(
        ("denominator", "expected"),
        [(20, "210.0"), (50, "84.0"), (100, "42.0"), (200, "21.0"), (500, "8.4")],
    )
    def test_4200_at_each_supported_scale(self, denominator, expected):
        assert actual_to_drawing(4200, denominator) == Decimal(expected)

    def test_uncommon_scales_are_accepted_not_rejected(self):
        # Scale is rarely 20/50/100. An odd assignment must still compute.
        assert actual_to_drawing(4200, 7) == Decimal("600")
        assert actual_to_drawing(4200, 137) > Decimal("30.656")
        assert actual_to_drawing(4200, 137) < Decimal("30.657")

    def test_one_to_one_is_the_identity(self):
        assert actual_to_drawing(4200, 1) == Decimal("4200")

    def test_division_is_exact_and_never_rounded(self):
        """Regression: rounding a quotient invents building that does not exist.

        A 230 mm wall at 1:500 is 0.46 mm. Rounding to 0.5 mm tells the student
        their wall is 250 mm -- a 20 mm error in the real building, produced
        entirely by the measurement engine.
        """
        assert actual_to_drawing(230, 500) == Decimal("0.46")
        assert actual_to_drawing(230, 200) == Decimal("1.15")
        assert drawing_to_actual(actual_to_drawing(230, 500), 500) == Decimal("230")

    def test_a_non_terminating_quotient_is_not_rounded_to_a_tidy_value(self):
        """The engine returns the real quotient, not a display-friendly one."""
        result = actual_to_drawing(4200, 137)
        assert result != Decimal("30.7")
        assert result != Decimal("30.66")
        # Full context precision is retained rather than truncated early.
        assert -result.as_tuple().exponent >= 20


class TestReverseConversion:
    def test_drawing_to_actual_is_the_multiplicative_inverse(self):
        assert drawing_to_actual(84, 50) == Decimal("4200")
        assert drawing_to_actual(4.6, 50) == Decimal("230.0")
        assert drawing_to_actual(18, 50) == Decimal("900")

    def test_reverse_is_not_quantised_so_deviations_survive(self):
        # 4.7 mm is 235 mm. Rounding to 230 would erase the student's mistake,
        # which is the entire thing the validator must detect.
        assert drawing_to_actual("4.7", 50) == Decimal("235.0")

    @pytest.mark.parametrize("denominator", SUPPORTED_SCALES)
    def test_round_trip_is_exact_at_every_supported_scale(self, denominator):
        for actual in (4200, 3600, 230, 900, 100, 125, 2000):
            drawing = actual_to_drawing(actual, denominator)
            assert drawing_to_actual(drawing, denominator) == Decimal(actual)

    @pytest.mark.parametrize("actual", [4200, 3600, 230, 900])
    def test_the_specification_round_trip(self, actual):
        drawing = actual_to_drawing(actual, 50)
        assert drawing_to_actual(drawing, 50) == Decimal(actual)

    def test_round_trip_is_exact_at_every_supported_scale(self):
        """Lossless, and provably so.

        20, 50, 100, 200 and 500 all divide into powers of ten, so every
        quotient terminates and no context rounding can occur. This is the
        guarantee the product actually relies on.
        """
        for denominator in SUPPORTED_SCALES:
            for actual in (4200, 3600, 230, 900, 100, 125, 2000):
                drawing = actual_to_drawing(actual, denominator)
                assert drawing_to_actual(drawing, denominator) == Decimal(actual)

    def test_round_trip_at_a_non_terminating_scale_is_accurate(self):
        """Decimal division is context-rounded, and the engine admits it.

        1:7 does not always divide into a power of ten, so 900 / 7 cannot be
        represented in 28 significant digits. The residual is ~1e-28 relative:
        reported honestly, never rounded away to a false exact match. Note that
        4200 / 7 is exactly 600 and does round trip exactly -- termination, not
        the denominator, is what decides.
        """
        for actual in (900, 4200, 3600, 230):
            drawing = actual_to_drawing(actual, 7)
            back = drawing_to_actual(drawing, 7)
            assert abs(back - actual) / actual < Decimal("1e-20")
            assert within_tolerance(back, actual, "0.001")

    def test_a_non_terminating_round_trip_is_reported_as_inexact(self):
        # 900 / 7 = 128.5714... needs 28 significant digits to hold, and the
        # multiplication back is not quite exact. It must not be rounded to
        # claim a perfect match.
        drawing = actual_to_drawing(900, 7)
        back = drawing_to_actual(drawing, 7)
        assert back != Decimal(900)
        assert back == Decimal("900.0000000000000000000000002")

    def test_a_terminating_quotient_round_trips_exactly(self):
        # 4200 / 7 = 600, which terminates, so nothing is rounded.
        assert actual_to_drawing(4200, 7) == Decimal(600)
        assert drawing_to_actual(actual_to_drawing(4200, 7), 7) == Decimal(4200)

    def test_round_trip_may_appear_lossy_only_if_the_student_mismeasured(self):
        # Drawing 4.7 mm instead of 4.6 is the student's error, not the
        # engine's, and it must survive the round trip as a 235 mm wall.
        assert drawing_to_actual("4.7", 50) == Decimal("235.0")
        assert not within_tolerance(drawing_to_actual("4.7", 50), 230, 0)


class TestCalculateScale:
    def test_derives_the_scale_from_a_known_pair(self):
        assert calculate_scale(4200, 84) == 50
        assert calculate_scale(3600, 72) == 50
        assert calculate_scale(230, "4.6") == 50
        assert calculate_scale(900, 18) == 50

    @pytest.mark.parametrize("denominator", SUPPORTED_SCALES)
    def test_round_trips_against_actual_to_drawing(self, denominator):
        drawing = actual_to_drawing(4200, denominator)
        assert calculate_scale(4200, drawing) == denominator

    def test_accepts_a_drawing_within_the_resolution(self):
        assert calculate_scale(4200, "84.1") == 50

    def test_rejects_a_pair_that_no_scale_explains(self):
        # 4200 at 1:50 draws 84.0, not 80.0, so no integer scale fits.
        with pytest.raises(InvalidScaleError):
            calculate_scale(4200, 80)

    def test_rejects_zero_drawing_length(self):
        with pytest.raises(InvalidDimensionError):
            calculate_scale(4200, 0)

    def test_rejects_zero_actual_length(self):
        with pytest.raises(InvalidDimensionError):
            calculate_scale(0, 84)

    def test_rejects_negative_lengths(self):
        with pytest.raises(InvalidDimensionError):
            calculate_scale(4200, -84)
        with pytest.raises(InvalidDimensionError):
            calculate_scale(-4200, 84)

    def test_rejects_an_implied_scale_below_one_to_one(self):
        # Drawing larger than the building is a magnification, not a scale.
        with pytest.raises(InvalidScaleError):
            calculate_scale(100, 400)


class TestInvalidScales:
    @pytest.mark.parametrize("denominator", [0, -1, -50])
    def test_non_positive_denominators_are_rejected(self, denominator):
        with pytest.raises(InvalidScaleError):
            actual_to_drawing(4200, denominator)
        with pytest.raises(InvalidScaleError):
            drawing_to_actual(84, denominator)

    def test_non_integer_denominators_are_rejected(self):
        with pytest.raises(InvalidScaleError):
            actual_to_drawing(4200, 50.5)  # type: ignore[arg-type]
        with pytest.raises(InvalidScaleError):
            actual_to_drawing(4200, Decimal(50))  # type: ignore[arg-type]

    def test_booleans_are_not_scales(self):
        with pytest.raises(InvalidScaleError):
            actual_to_drawing(4200, True)  # type: ignore[arg-type]

    def test_optional_strict_mode_rejects_uncommon_scales(self):
        # Off by default; offered so a course can restrict to its own set.
        with pytest.raises(InvalidScaleError, match="unsupported scale"):
            validate_scale(137, restrict_to_supported=True)
        assert validate_scale(50, restrict_to_supported=True) == 50

    def test_format_scale(self):
        assert format_scale(50) == "1:50"
        assert format_scale(137) == "1:137"
        with pytest.raises(InvalidScaleError):
            format_scale(0)


class TestNegativeDimensions:
    @pytest.mark.parametrize("actual", [-1, -4200, Decimal("-0.1")])
    def test_negative_actual_is_rejected(self, actual):
        with pytest.raises(InvalidDimensionError):
            actual_to_drawing(actual, 50)

    @pytest.mark.parametrize("drawing", [-1, -84])
    def test_negative_drawing_is_rejected(self, drawing):
        with pytest.raises(InvalidDimensionError):
            drawing_to_actual(drawing, 50)


class TestWithinTolerance:
    def test_identical_values_are_within_zero_tolerance(self):
        assert within_tolerance(84, 84, 0)

    def test_deviation_equal_to_tolerance_passes(self):
        assert within_tolerance(84, "84.1", "0.1")

    def test_deviation_beyond_tolerance_fails(self):
        assert not within_tolerance(84, "84.2", "0.1")

    def test_tolerance_is_absolute_not_percentage(self):
        # 1 mm on a 4200 mm room and 1 mm on a 4.2 mm detail are equally valid.
        assert within_tolerance(4201, 4200, 1)
        assert within_tolerance("5.2", "4.2", 1)

    def test_a_deviation_at_the_drawing_resolution_is_reported(self):
        # 4.6 and 4.7 differ by a tenth of a millimetre, which is a real
        # difference on the sheet. Forgiving it would invent agreement.
        assert not within_tolerance("4.6", "4.7", 0)

    def test_float_input_never_carries_binary_noise_into_a_comparison(self):
        # to_decimal routes floats through str, so the float nearest 4.6 is
        # compared as exactly 4.6 and a genuine zero-tolerance match holds.
        assert within_tolerance(4.6, 4.6, 0)
        assert within_tolerance(0.1, 0.1, 0)
        assert within_tolerance(2.3, 2.3, 0)

    def test_negative_tolerance_is_rejected(self):
        with pytest.raises(InvalidToleranceError):
            within_tolerance(84, 84, -1)

    def test_a_tiny_tolerance_still_rejects_a_real_mistake(self):
        assert not within_tolerance("4.6", "4.7", 0)


class TestPrecision:
    def test_decimal_input_never_becomes_a_binary_float_artefact(self):
        assert to_decimal(0.1) == Decimal("0.1")
        assert to_decimal(0.1) != Decimal(0.1)
        assert to_decimal(4.6) == Decimal("4.6")

    def test_float_input_is_routed_through_str(self):
        assert to_decimal(0.1) == Decimal("0.1")
        assert to_decimal(4.6) == Decimal("4.6")

    def test_string_input_is_accepted_exactly(self):
        assert to_decimal("4.6") == Decimal("4.6")
        assert to_decimal(" 4200 ") == Decimal("4200")

    def test_arithmetic_is_exact_where_it_can_be(self):
        total = Decimal("0.1") + Decimal("0.2")
        assert total == Decimal("0.3")
        assert convert_unit("0.1", "m", "mm") + convert_unit(
            "0.2", "m", "mm"
        ) == Decimal("300")

    def test_booleans_are_rejected_by_to_decimal(self):
        with pytest.raises(InvalidDimensionError):
            to_decimal(True)

    def test_mm_rounds_to_whole_actual_millimetres(self):
        assert mm(230.0) == 230
        assert mm("4.6") == 5
        assert mm("5.5") == 6
        assert mm("4.4") == 4

    def test_mm_rejects_negative(self):
        with pytest.raises(InvalidDimensionError):
            mm(-1)
