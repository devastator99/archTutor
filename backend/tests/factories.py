"""Drawing builders for tests.

These build **real submissions**, not mocks. A mock of a drawing would let a test
pass while the parser, the scale conversion and the wall-side mapping were all
broken, which is precisely the class of bug this product exists to detect.

The reference drawing is the north-star brief: a 4200 x 3600 mm room at 1:50
with 230 mm walls, a 900 mm door and no window. At 1:50 that is 84 x 72 mm of
paper with 4.6 mm walls and an 18 mm door.

Every builder returns a plain dict in ``StudentDrawing.to_dict()`` form, because
that is what crosses the API boundary, and it is the only place in the tests
where ids are invented.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from app.measurement.scale import actual_to_drawing

WALL_IDS = {
    "south": uuid.UUID("00000000-0000-4000-8000-000000000001"),
    "north": uuid.UUID("00000000-0000-4000-8000-000000000002"),
    "west": uuid.UUID("00000000-0000-4000-8000-000000000003"),
    "east": uuid.UUID("00000000-0000-4000-8000-000000000004"),
}


def _d(value: Any) -> str:
    return str(Decimal(str(value)))


def north_star_drawing(
    *,
    scale: int = 50,
    room_width_mm: Any = 84,
    room_height_mm: Any = 72,
    wall_thickness_mm: Any = "4.6",
    door_width_mm: Any = 18,
    door_side: str = "south",
    door_offset_mm: Any = 30,
    include_door: bool = True,
    include_width_dimension: bool = True,
    include_height_dimension: bool = False,
    dimension_label_mm: Any = 4200,
    wall_ids: dict[str, uuid.UUID] | None = None,
) -> dict[str, Any]:
    """A submission for the north-star brief, correct unless told otherwise.

    Every keyword is a way to make one specific thing wrong, so a test can
    isolate a single check instead of perturbing everything at once.
    """
    ids = dict(wall_ids or WALL_IDS)
    width = Decimal(str(room_width_mm))
    height = Decimal(str(room_height_mm))
    wall_t = Decimal(str(wall_thickness_mm))

    walls = [
        {
            "id": str(ids["south"]),
            "start": {"x": "0", "y": "0"},
            "end": {"x": _d(width), "y": "0"},
            "thickness_mm": _d(wall_t),
        },
        {
            "id": str(ids["north"]),
            "start": {"x": "0", "y": _d(height)},
            "end": {"x": _d(width), "y": _d(height)},
            "thickness_mm": _d(wall_t),
        },
        {
            "id": str(ids["west"]),
            "start": {"x": "0", "y": "0"},
            "end": {"x": "0", "y": _d(height)},
            "thickness_mm": _d(wall_t),
        },
        {
            "id": str(ids["east"]),
            "start": {"x": _d(width), "y": "0"},
            "end": {"x": _d(width), "y": _d(height)},
            "thickness_mm": _d(wall_t),
        },
    ]

    openings: list[dict[str, Any]] = []
    if include_door:
        openings.append(
            {
                "host_wall_id": str(ids[door_side]),
                "offset_mm": _d(door_offset_mm),
                "width_mm": _d(door_width_mm),
                "kind": "door",
            }
        )

    dimensions: list[dict[str, Any]] = []
    if include_width_dimension:
        dimensions.append(
            {
                "start": {"x": "0", "y": "-10"},
                "end": {"x": _d(width), "y": "-10"},
                "actual_value_mm": _d(dimension_label_mm),
            }
        )
    if include_height_dimension:
        dimensions.append(
            {
                "start": {"x": "-10", "y": "0"},
                "end": {"x": "-10", "y": _d(height)},
                "actual_value_mm": "3600",
            }
        )

    return {
        "scale_denominator": scale,
        "room": {
            "boundary": [
                {"x": "0", "y": "0"},
                {"x": _d(width), "y": "0"},
                {"x": _d(width), "y": _d(height)},
                {"x": "0", "y": _d(height)},
            ]
        },
        "walls": walls,
        "openings": openings,
        "dimensions": dimensions,
    }


def north_star_exercise_payload() -> dict[str, Any]:
    """The brief the reference drawing answers, as an ``ExerciseCreate`` body."""
    return {
        "slug": "bedroom-4200x3600-1-50",
        "title": "Bedroom 4200 x 3600 at 1:50",
        "description": "Draw a 4200 x 3600 mm room at 1:50 with 230 mm walls and a 900 mm door.",
        "room_width_mm": 4200,
        "room_height_mm": 3600,
        "wall_thickness_mm": 230,
        "scale_denominator": 50,
        "door_requirements": [
            {"kind": "door", "width_mm": 900, "count": 1, "wall": "south"}
        ],
        "window_requirements": [],
        "dimension_requirements": [
            {"axis": "width", "value_mm": 4200, "on_wall": "south"},
        ],
        "difficulty": "beginner",
    }


WALL_ID_BY_SIDE = {
    "south": uuid.UUID("00000000-0000-4000-8000-000000000001"),
    "north": uuid.UUID("00000000-0000-4000-8000-000000000002"),
    "west": uuid.UUID("00000000-0000-4000-8000-000000000003"),
    "east": uuid.UUID("00000000-0000-4000-8000-000000000004"),
}
"""Same fixed ids as :data:`WALL_IDS`, so both builders agree."""


def correct_drawing_for(exercise) -> dict[str, Any]:
    """Build a submission that satisfies ``exercise`` exactly.

    Used to prove the shipped briefs are actually satisfiable. A brief that no
    drawing could satisfy would look identical to a student who is stuck: the
    validator would report findings no amount of correct work could clear.
    """
    scale = exercise.scale_denominator
    width = actual_to_drawing(exercise.room_width_mm, scale)
    height = actual_to_drawing(exercise.room_height_mm, scale)
    thickness = actual_to_drawing(exercise.wall_thickness_mm, scale)
    ids = dict(WALL_ID_BY_SIDE)

    walls = [
        {"id": str(ids["south"]), "start": {"x": "0", "y": "0"},
         "end": {"x": _d(width), "y": "0"}, "thickness_mm": _d(thickness)},
        {"id": str(ids["north"]), "start": {"x": "0", "y": _d(height)},
         "end": {"x": _d(width), "y": _d(height)}, "thickness_mm": _d(thickness)},
        {"id": str(ids["west"]), "start": {"x": "0", "y": "0"},
         "end": {"x": "0", "y": _d(height)}, "thickness_mm": _d(thickness)},
        {"id": str(ids["east"]), "start": {"x": _d(width), "y": "0"},
         "end": {"x": _d(width), "y": _d(height)}, "thickness_mm": _d(thickness)},
    ]

    openings: list[dict[str, Any]] = []
    for requirements in (exercise.door_requirements, exercise.window_requirements):
        for requirement in requirements:
            side = requirement.wall or "south"
            offset = Decimal(0)
            for _ in range(requirement.count):
                opening_width = actual_to_drawing(requirement.width_mm, scale)
                openings.append({
                    "host_wall_id": str(ids[side]),
                    "offset_mm": _d(offset),
                    "width_mm": _d(opening_width),
                    "kind": requirement.kind,
                })
                offset += opening_width

    dimensions: list[dict[str, Any]] = []
    for requirement in exercise.dimension_requirements:
        if requirement.axis == "width":
            start, end = {"x": "0", "y": "-10"}, {"x": _d(width), "y": "-10"}
        else:
            start, end = {"x": "-10", "y": "0"}, {"x": "-10", "y": _d(height)}
        dimensions.append({
            "start": start,
            "end": end,
            "actual_value_mm": str(requirement.value_mm),
        })

    return {
        "scale_denominator": scale,
        "room": {
            "boundary": [
                {"x": "0", "y": "0"},
                {"x": _d(width), "y": "0"},
                {"x": _d(width), "y": _d(height)},
                {"x": "0", "y": _d(height)},
            ]
        },
        "walls": walls,
        "openings": openings,
        "dimensions": dimensions,
    }
