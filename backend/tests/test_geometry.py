"""Tests for the geometry domain.

The wall-side mapping and the opening-overhang bug both shipped past a smoke
check, because a smoke check confirms a number came out, not that the right
number came out. These tests pin the behaviour that a drawing's meaning depends
on: which wall is which side, which way an offset runs, and what round-trips
through serialisation.

Units are millimetres, and comparisons use ``Decimal`` throughout. A float
comparison here would pass on values that are not equal.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.geometry.drawing import DrawingFormatError, StudentDrawing
from app.geometry.errors import (
    GeometryError,
    InvalidOpeningError,
    InvalidRoomError,
    InvalidWallError,
    MisalignedOpeningError,
    UnknownWallError,
)
from app.geometry.operations import (
    dimension_for,
    is_aligned_with_room,
    opening_centre_offset,
    opening_segment,
    opening_span,
    resolve_opening_wall,
    room_area,
    room_height,
    room_perimeter,
    room_width,
    wall_axis,
    wall_length,
    walls_total_length,
)
from app.geometry.primitives import Line, Point, distance, is_horizontal, is_vertical
from app.geometry.room import Dimension, Room
from app.geometry.wall import Door, Opening, OpeningKind, SwingDirection, Wall, Window

D = Decimal


def _wall(start: tuple, end: tuple, thickness="100", id_=None) -> Wall:
    # thickness is passed through unconverted on purpose: Wall accepts strings and
    # Decimals, and coercing here would bypass the very validation under test.
    return Wall(
        start=Point(D(start[0]), D(start[1])),
        end=Point(D(end[0]), D(end[1])),
        thickness_mm=thickness,
        id=id_,
    )


def _room(x0, y0, x1, y1) -> Room:
    return Room(
        [
            Point(D(x0), D(y0)),
            Point(D(x1), D(y0)),
            Point(D(x1), D(y1)),
            Point(D(x0), D(y1)),
        ]
    )


class TestPrimitives:
    def test_distance_is_hypotenuse(self):
        assert distance(Point(D(0), D(0)), Point(D(3), D(4))) == D(5)

    def test_distance_is_symmetric(self):
        a, b = Point(D(1), D(2)), Point(D(9), D(7))
        assert distance(a, b) == distance(b, a)

    def test_distance_to_self_is_zero(self):
        assert distance(Point(D(2), D(2)), Point(D(2), D(2))) == D(0)

    def test_horizontal_and_vertical_detection(self):
        assert is_horizontal(Point(D(0), D(0)), Point(D(5), D(0)))
        assert is_vertical(Point(D(0), D(0)), Point(D(0), D(5)))
        assert not is_horizontal(Point(D(0), D(0)), Point(D(0), D(5)))

    def test_line_length_ignores_winding_direction(self):
        forward = Line(Point(D(0), D(0)), Point(D(7), D(0)))
        backward = Line(Point(D(7), D(0)), Point(D(0), D(0)))
        assert forward.length == backward.length == D(7)


class TestWalls:
    def test_length_is_the_spanned_distance(self):
        assert _wall((0, 0), (4200, 0)).length_mm == D(4200)

    def test_length_is_positive_whatever_the_winding(self):
        assert _wall((4200, 0), (0, 0)).length_mm == D(4200)

    def test_axis_follows_the_segment(self):
        assert _wall((0, 0), (100, 0)).axis.value == "horizontal"
        assert _wall((0, 0), (0, 100)).axis.value == "vertical"

    def test_wall_length_and_axis_operations_agree_with_the_object(self):
        wall = _wall((0, 0), (4200, 0), thickness="230")
        assert wall_length(wall) == wall.length_mm == D(4200)
        assert wall_axis(wall).value == "horizontal"

    def test_wall_length_rejects_a_non_wall(self):
        with pytest.raises(TypeError):
            wall_length("a wall")

    def test_direction_reports_the_axis_sign(self):
        assert _wall((0, 0), (100, 0)).direction == 1
        assert _wall((100, 0), (0, 0)).direction == -1
        assert _wall((0, 0), (0, 100)).direction == 1
        assert _wall((0, 100), (0, 0)).direction == -1

    def test_a_diagonal_wall_is_rejected(self):
        """The MVP's measurements depend on the axis, so a skew wall is refused."""
        with pytest.raises(InvalidWallError, match="horizontal or vertical"):
            _wall((0, 0), (100, 100))

    def test_a_zero_length_wall_is_rejected(self):
        with pytest.raises(InvalidWallError, match="distinct"):
            _wall((5, 5), (5, 5))

    def test_thickness_must_be_positive(self):
        with pytest.raises(InvalidWallError):
            _wall((0, 0), (100, 0), thickness="0")

    def test_negative_thickness_is_rejected(self):
        with pytest.raises(InvalidWallError):
            _wall((0, 0), (100, 0), thickness="-5")

    def test_non_numeric_thickness_is_rejected(self):
        with pytest.raises(InvalidWallError):
            _wall((0, 0), (100, 0), thickness="thick")

    def test_offset_is_measured_from_start_not_from_the_minimum(self):
        """A right-to-left wall must still resolve offsets along its own direction.

        Using the smaller coordinate instead would place every opening on such a
        wall in the wrong position, and the error would only show up as a door
        that mysteriously does not fit.
        """
        wall = _wall((4200, 0), (0, 0))

        assert wall.point_at(100) == Point(D(4100), D(0))
        assert wall.point_at(4200) == Point(D(0), D(0))

    def test_wall_area_is_length_times_thickness(self):
        wall = _wall((0, 0), (4200, 0), thickness="230")
        assert wall_length(wall) * wall.thickness_mm == D(4200) * D(230)

    def test_total_length_sums_several_walls(self):
        walls = [_wall((0, 0), (4200, 0)), _wall((0, 0), (0, 3600))]
        assert walls_total_length(walls) == D(7800)

    def test_total_length_of_no_walls_is_zero_not_none(self):
        """sum() with no start would return an int and pollute a Decimal API."""
        assert walls_total_length([]) == D(0)


class TestOpenings:
    def test_end_offset_is_offset_plus_width(self):
        door = Door(host_wall_id=uuid.uuid4(), offset_mm=D(900), width_mm=D(800))
        assert door.end_offset_mm == D(1700)

    def test_negative_offset_is_rejected(self):
        with pytest.raises(InvalidOpeningError):
            Door(host_wall_id=uuid.uuid4(), offset_mm=D(-1), width_mm=D(800))

    def test_negative_width_is_rejected(self):
        with pytest.raises(InvalidOpeningError):
            Door(host_wall_id=uuid.uuid4(), offset_mm=D(0), width_mm=D(-800))

    def test_host_wall_must_be_a_uuid(self):
        with pytest.raises(InvalidOpeningError):
            Door(host_wall_id="south", offset_mm=D(0), width_mm=D(800))

    def test_fits_within_its_wall(self):
        wall = _wall((0, 0), (4200, 0))
        door = Door(host_wall_id=wall.id, offset_mm=D(900), width_mm=D(800))
        assert door.fits_in(wall)

    def test_an_opening_that_overhangs_does_not_fit(self):
        """The exact case that the validator's fit check exists to catch."""
        wall = _wall((0, 0), (4200, 0))
        door = Door(host_wall_id=wall.id, offset_mm=D(4000), width_mm=D(800))
        assert not door.fits_in(wall)

    def test_an_opening_ending_exactly_at_the_wall_end_fits(self):
        wall = _wall((0, 0), (4200, 0))
        door = Door(host_wall_id=wall.id, offset_mm=D(3400), width_mm=D(800))
        assert door.fits_in(wall)

    def test_placement_against_the_wrong_wall_is_rejected(self):
        wall = _wall((0, 0), (4200, 0))
        other = _wall((0, 5000), (4200, 5000))
        door = Door(host_wall_id=other.id, offset_mm=D(0), width_mm=D(800))

        with pytest.raises(MisalignedOpeningError):
            door.validate_placement(wall)

    def test_segment_in_follows_the_wall_direction(self):
        wall = _wall((4200, 0), (0, 0))
        door = Door(host_wall_id=wall.id, offset_mm=D(400), width_mm=D(800))

        start, end = door.segment_in(wall)

        assert start == Point(D(3800), D(0))
        assert end == Point(D(3000), D(0))

    def test_door_and_window_carry_their_own_kind(self):
        wall_id = uuid.uuid4()
        assert Door(host_wall_id=wall_id, offset_mm=0, width_mm=800).kind is OpeningKind.DOOR
        assert Window(host_wall_id=wall_id, offset_mm=0, width_mm=800).kind is OpeningKind.WINDOW

    def test_swing_direction_defaults_and_validates(self):
        wall_id = uuid.uuid4()
        assert Door(host_wall_id=wall_id, offset_mm=0, width_mm=800).swing_direction is (
            SwingDirection.LEFT
        )
        with pytest.raises(InvalidOpeningError):
            Door(
                host_wall_id=wall_id,
                offset_mm=0,
                width_mm=800,
                swing_direction="sideways",
            )


class TestOpeningOperations:
    def test_span_and_centre_offset(self):
        door = Door(host_wall_id=uuid.uuid4(), offset_mm=D(900), width_mm=D(800))
        assert opening_span(door) == (D(900), D(1700))
        assert opening_centre_offset(door) == D(1300)

    def test_resolving_the_host_wall(self):
        wall = _wall((0, 0), (4200, 0))
        other = _wall((0, 5000), (4200, 5000))
        door = Door(host_wall_id=wall.id, offset_mm=D(900), width_mm=D(800))

        assert resolve_opening_wall(door, [other, wall]) is wall

    def test_an_orphaned_opening_raises_rather_than_returning_none(self):
        """None would be indistinguishable from a legitimately absent opening."""
        door = Door(host_wall_id=uuid.uuid4(), offset_mm=D(0), width_mm=D(800))

        with pytest.raises(UnknownWallError):
            resolve_opening_wall(door, [_wall((0, 0), (4200, 0))])

    def test_opening_segment_resolves_and_validates(self):
        wall = _wall((4200, 0), (0, 0))
        door = Door(host_wall_id=wall.id, offset_mm=D(400), width_mm=D(800))

        assert opening_segment(door, [wall]) == (
            Point(D(3800), D(0)),
            Point(D(3000), D(0)),
        )

    def test_alignment_is_reported_as_a_boolean_not_an_exception(self):
        wall = _wall((0, 0), (4200, 0))
        fitted = Door(host_wall_id=wall.id, offset_mm=D(900), width_mm=D(800))
        overhanging = Door(host_wall_id=wall.id, offset_mm=D(4000), width_mm=D(800))
        orphaned = Door(host_wall_id=uuid.uuid4(), offset_mm=D(0), width_mm=D(800))

        assert is_aligned_with_room(fitted, [wall]) is True
        assert is_aligned_with_room(overhanging, [wall]) is False
        assert is_aligned_with_room(orphaned, [wall]) is False


class TestRooms:
    def test_area_and_perimeter(self):
        room = _room(0, 0, 4200, 3600)
        assert room_area(room) == D(4200) * D(3600)
        assert room_perimeter(room) == D(2) * (D(4200) + D(3600))

    def test_width_and_height_operations_agree_with_the_object(self):
        room = _room(100, 200, 4300, 3800)
        assert room_width(room) == D(4200)
        assert room_height(room) == D(3600)

    def test_extent_is_derived_not_stored(self):
        room = _room(100, 200, 4300, 3800)
        assert (room.min_x, room.max_x) == (D(100), D(4300))
        assert (room.min_y, room.max_y) == (D(200), D(3800))

    def test_winding_order_does_not_change_the_room(self):
        clockwise = Room(
            [
                Point(D(0), D(0)),
                Point(D(0), D(3000)),
                Point(D(4000), D(3000)),
                Point(D(4000), D(0)),
            ]
        )
        assert room_area(clockwise) == D(4000) * D(3000)

    def test_centre_is_the_midpoint(self):
        assert _room(0, 0, 4000, 3000).centre == Point(D(2000), D(1500))

    def test_a_triangle_is_rejected(self):
        with pytest.raises(InvalidRoomError, match="rectangular"):
            Room([Point(D(0), D(0)), Point(D(1), D(0)), Point(D(0), D(1))])

    def test_a_skewed_quadrilateral_is_rejected(self):
        """Four points is not enough; the shape must be a rectangle."""
        with pytest.raises(InvalidRoomError, match="axis-aligned"):
            Room(
                [
                    Point(D(0), D(0)),
                    Point(D(4000), D(0)),
                    Point(D(4000), D(3000)),
                    Point(D(0), D(2500)),
                ]
            )

    def test_repeated_corners_are_rejected(self):
        with pytest.raises(InvalidRoomError, match="distinct"):
            Room(
                [
                    Point(D(0), D(0)),
                    Point(D(4000), D(0)),
                    Point(D(4000), D(3000)),
                    Point(D(0), D(0)),
                ]
            )

    def test_a_collinear_boundary_is_rejected(self):
        with pytest.raises(InvalidRoomError):
            Room(
                [
                    Point(D(0), D(0)),
                    Point(D(2000), D(0)),
                    Point(D(4000), D(0)),
                    Point(D(4000), D(3000)),
                ]
            )


class TestDimensions:
    def test_measured_length_is_the_span(self):
        dimension = Dimension(
            start=Point(D(0), D(-100)),
            end=Point(D(4200), D(-100)),
            actual_value_mm=D(4200),
        )
        assert dimension.measured_mm == D(4200)

    def test_measured_length_ignores_direction(self):
        dimension = Dimension(
            start=Point(D(4200), D(-100)),
            end=Point(D(0), D(-100)),
            actual_value_mm=D(4200),
        )
        assert dimension.measured_mm == D(4200)

    def test_deviation_is_measured_minus_labelled(self):
        dimension = Dimension(
            start=Point(D(0), D(0)),
            end=Point(D(4100), D(0)),
            actual_value_mm=D(4200),
        )
        assert dimension.deviation_mm == D(-100)

    def test_a_zero_length_dimension_is_rejected(self):
        with pytest.raises(InvalidRoomError, match="distinct"):
            Dimension(
                start=Point(D(5), D(5)),
                end=Point(D(5), D(5)),
                actual_value_mm=D(100),
            )

    def test_a_negative_value_is_rejected(self):
        with pytest.raises(InvalidRoomError):
            Dimension(
                start=Point(D(0), D(0)),
                end=Point(D(100), D(0)),
                actual_value_mm=D(-1),
            )


class TestStudentDrawingSideMapping:
    """Which wall is which side.

    North and south boundaries run east-west, so their walls are *horizontal*.
    East and west boundaries run north-south, so their walls are *vertical*.
    Pairing these the other way round makes every lookup miss, and nothing else
    in the system notices.
    """

    @pytest.fixture
    def drawing(self) -> StudentDrawing:
        return StudentDrawing(
            scale_denominator=50,
            room=_room(0, 0, 84, 72),
            walls=[
                _wall((0, 0), (84, 0), id_=uuid.UUID(int=1)),
                _wall((0, 72), (84, 72), id_=uuid.UUID(int=2)),
                _wall((0, 0), (0, 72), id_=uuid.UUID(int=3)),
                _wall((84, 0), (84, 72), id_=uuid.UUID(int=4)),
            ],
        )

    @pytest.mark.parametrize(
        ("side", "index"),
        [("south", 1), ("north", 2), ("west", 3), ("east", 4)],
    )
    def test_each_side_resolves_to_its_own_wall(self, drawing, side, index):
        wall = drawing.wall_on_side(side)
        assert wall is not None
        assert wall.id == uuid.UUID(int=index)

    def test_every_side_resolves_to_a_distinct_wall(self, drawing):
        ids = {drawing.wall_on_side(s).id for s in ("north", "south", "east", "west")}
        assert len(ids) == 4

    def test_side_names_round_trip(self, drawing):
        for side in ("north", "south", "east", "west"):
            assert drawing.wall_on_side_name(drawing.wall_on_side(side)) == side

    def test_a_wall_off_the_boundary_has_no_side(self, drawing):
        stray = _wall((200, 200), (300, 200), id_=uuid.UUID(int=9))
        assert drawing.wall_on_side_name(stray) is None

    def test_a_missing_wall_resolves_to_none(self):
        drawing = StudentDrawing(
            scale_denominator=50, room=_room(0, 0, 84, 72), walls=[]
        )
        assert drawing.wall_on_side("north") is None

    def test_openings_are_grouped_by_host_wall(self, drawing):
        south = drawing.wall_on_side("south")
        north = drawing.wall_on_side("north")
        door = Door(host_wall_id=south.id, offset_mm=D(30), width_mm=D(18))
        window = Window(host_wall_id=north.id, offset_mm=D(10), width_mm=D(24))
        drawing = StudentDrawing(
            scale_denominator=50,
            room=drawing.room,
            walls=drawing.walls,
            openings=[door, window],
        )

        assert drawing.openings_on(south) == (door,)
        assert drawing.openings_on(north) == (window,)
        assert drawing.openings_of_kind(OpeningKind.DOOR) == (door,)


class TestStudentDrawingSerialisation:
    def test_round_trip_preserves_the_drawing(self):
        from tests.factories import north_star_drawing

        original = StudentDrawing.from_dict(north_star_drawing())
        restored = StudentDrawing.from_dict(original.to_dict())

        assert restored.to_dict() == original.to_dict()
        assert restored.scale_denominator == original.scale_denominator
        assert restored.room_width == original.room_width
        assert [w.id for w in restored.walls] == [w.id for w in original.walls]

    def test_millimetres_survive_as_exact_decimals(self):
        """A JSON number is a double; 4.6 would come back as 4.5999999999999996."""
        from tests.factories import north_star_drawing

        payload = StudentDrawing.from_dict(north_star_drawing()).to_dict()

        assert payload["walls"][0]["thickness_mm"] == "4.6"
        assert isinstance(payload["walls"][0]["thickness_mm"], str)
        assert StudentDrawing.from_dict(payload).room_width == D("84")

    def test_a_sub_millimetre_value_is_not_rounded_away(self):
        from tests.factories import north_star_drawing

        original = StudentDrawing.from_dict(north_star_drawing(wall_thickness_mm="4.65"))
        assert StudentDrawing.from_dict(original.to_dict()).walls[0].thickness_mm == D("4.65")

    def test_a_drawing_must_be_an_object(self):
        with pytest.raises(DrawingFormatError, match="must be an object"):
            StudentDrawing.from_dict([1, 2, 3])

    def test_unknown_nested_keys_are_rejected(self):
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        payload["walls"][0]["material"] = "brick"

        with pytest.raises(DrawingFormatError, match=r"walls\[0\].*unknown field"):
            StudentDrawing.from_dict(payload)

    def test_an_unknown_opening_kind_is_rejected(self):
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        payload["openings"][0]["kind"] = "hatch"

        with pytest.raises(DrawingFormatError, match="'door' or 'window'"):
            StudentDrawing.from_dict(payload)

    def test_a_non_numeric_value_is_rejected_with_its_path(self):
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        payload["openings"][0]["width_mm"] = "wide"

        with pytest.raises(DrawingFormatError, match=r"openings\[0\]"):
            StudentDrawing.from_dict(payload)

    def test_a_non_numeric_scale_is_rejected(self):
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        payload["scale_denominator"] = "1:50"

        with pytest.raises(DrawingFormatError, match="integer"):
            StudentDrawing.from_dict(payload)

    def test_a_boolean_scale_is_rejected(self):
        """``True`` is an int in Python; accepting it would be a silent 1:1."""
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        payload["scale_denominator"] = True

        with pytest.raises(DrawingFormatError, match="integer"):
            StudentDrawing.from_dict(payload)

    def test_an_uncommon_scale_is_still_valid(self):
        """1:137 is a real scale; rejecting it would enforce a guess about the course."""
        from tests.factories import north_star_drawing

        assert StudentDrawing.from_dict(
            north_star_drawing(scale=137)
        ).scale_denominator == 137

    @pytest.mark.parametrize("scale", [1, 0, -50])
    def test_a_scale_below_the_minimum_is_rejected(self, scale):
        """1:1 is a real scale but a useless submission: it satisfies any brief."""
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        payload["scale_denominator"] = scale

        with pytest.raises(DrawingFormatError):
            StudentDrawing.from_dict(payload)

    def test_a_one_to_one_drawing_cannot_pass_a_brief(self):
        """Otherwise the scale check could be defeated by declaring 1."""
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        # Building millimetres, presented as paper millimetres at 1:1.
        payload["scale_denominator"] = 1
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "4200", "y": "0"},
            {"x": "4200", "y": "3600"},
            {"x": "0", "y": "3600"},
        ]

        with pytest.raises(DrawingFormatError):
            StudentDrawing.from_dict(payload)

    def test_geometry_errors_surface_as_drawing_format_errors(self):
        """Callers catch one exception type, so the boundary must not leak two."""
        from tests.factories import north_star_drawing

        payload = north_star_drawing()
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "84", "y": "0"},
            {"x": "84", "y": "72"},
        ]

        with pytest.raises(DrawingFormatError):
            StudentDrawing.from_dict(payload)

    def test_derived_opening_ids_are_stable_across_parses(self):
        from tests.factories import north_star_drawing

        first = StudentDrawing.from_dict(north_star_drawing())
        second = StudentDrawing.from_dict(north_star_drawing())

        assert first.openings[0].id == second.openings[0].id

    def test_two_identical_openings_get_distinct_derived_ids(self):
        """Otherwise two doors would share one geometry_reference and be one row."""
        from tests.factories import WALL_IDS, north_star_drawing

        payload = north_star_drawing()
        payload["openings"].append(dict(payload["openings"][0]))
        drawing = StudentDrawing.from_dict(payload)

        assert len({o.id for o in drawing.openings}) == 2


class TestDimensionOperations:
    def test_dimension_for_builds_a_measured_span(self):
        dimension = dimension_for(
            Point(D(0), D(-100)), Point(D(4200), D(-100)), D(4200)
        )
        assert dimension.measured_mm == D(4200)
        assert dimension.actual_value_mm == D(4200)
        assert dimension.deviation_mm == D(0)
