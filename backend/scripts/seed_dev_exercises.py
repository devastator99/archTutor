"""Seed the development database with authored beginner exercises.

Idempotent: re-running updates the existing rows by slug, so it is safe to run
on every setup and after editing a brief.

    python -m scripts.seed_dev_exercises

WHY THESE VALUES
----------------
Every number is a real, common architectural dimension, not a random one. A
student must never be told to draw a 4371 mm room: the lesson is drafting
practice, and an invented dimension teaches nothing transferable.

    3600 x 3600   a small square bedroom / study
    4200 x 3600   the north-star brief: a standard single bedroom
    4800 x 3600   a wider bedroom or a small office
    5400 x 4200   a generous bedroom
    6000 x 3600   a living room

    100 / 115     light partition walls (studwork, lightweight block)
    200 / 230     masonry walls (blockwork, brick)

    800           the standard single door leaf
    900           a standard door leaf, or a wide single
    1200          a double door / wide opening

    600 / 900     small utility windows
    1200 / 1500   standard bedroom windows
    1800          a wide living-room window

Scales 1:20, 1:50, 1:100 and 1:200 are all represented, because the mistake
students make most is carrying the wrong one, and they cannot practise that if
every brief is 1:50.

Brief 1 is deliberately the simplest one -- a square room, a door and a single
dimension -- so a student can succeed before width, height, windows and
placement are all in play at once. The difficulty then rises one variable at a
time.
"""

from __future__ import annotations

from app.db.session import get_session_factory
from app.exercises.repository import upsert_exercise
from app.models.exercise import Difficulty
from app.schemas.exercise import (
    DimensionRequirement,
    ExerciseCreate,
    OpeningRequirement,
)


def small_study() -> ExerciseCreate:
    return ExerciseCreate(
        slug="study-3600x3600-1-50",
        title="Small study, 1:50",
        description=(
            "Draw a square study 3600 x 3600 mm at 1:50 with 115 mm partition "
            "walls, one 800 mm door and one 1200 mm window."
        ),
        room_width_mm=3600,
        room_height_mm=3600,
        wall_thickness_mm=115,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1200, count=1, wall="north", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3600, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def north_star_bedroom() -> ExerciseCreate:
    """The brief the whole product is built around.

    Draw a 4200 x 3600 mm room at 1:50. Use 230 mm walls. Add a 900 mm door.
    """
    return ExerciseCreate(
        slug="bedroom-4200x3600-1-50",
        title="Bedroom 4200 x 3600 at 1:50",
        description=(
            "Draw a 4200 x 3600 mm room at 1:50. Use 230 mm walls. "
            "Add a 900 mm door."
        ),
        room_width_mm=4200,
        room_height_mm=3600,
        wall_thickness_mm=230,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=900, count=1, wall="south")
        ],
        window_requirements=[],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=4200, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=3600, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def wide_office() -> ExerciseCreate:
    return ExerciseCreate(
        slug="office-4800x3600-1-50",
        title="Office 4800 x 3600 at 1:50",
        description=(
            "Draw a 4800 x 3600 mm office at 1:50 with 115 mm partition walls, "
            "one 800 mm door and two 1200 mm windows."
        ),
        room_width_mm=4800,
        room_height_mm=3600,
        wall_thickness_mm=115,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="west")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1200, count=2, wall="north", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=4800, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def generous_bedroom() -> ExerciseCreate:
    return ExerciseCreate(
        slug="bedroom-5400x4200-1-100",
        title="Bedroom 5400 x 4200 at 1:100",
        description=(
            "Draw a 5400 x 4200 mm bedroom at 1:100 with 230 mm walls, one 900 mm "
            "door and one 1500 mm window."
        ),
        room_width_mm=5400,
        room_height_mm=4200,
        wall_thickness_mm=230,
        scale_denominator=100,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=900, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1500, count=1, wall="north", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=5400, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def living_room() -> ExerciseCreate:
    return ExerciseCreate(
        slug="living-room-6000x3600-1-50",
        title="Living room 6000 x 3600 at 1:50",
        description=(
            "Draw a 6000 x 3600 mm living room at 1:50 with 200 mm walls, a "
            "1200 mm double door and one 1800 mm window."
        ),
        room_width_mm=6000,
        room_height_mm=3600,
        wall_thickness_mm=200,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=1200, count=1, wall="west")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1800, count=1, wall="north", sill_height_mm=450
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=6000, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def utility_room() -> ExerciseCreate:
    return ExerciseCreate(
        slug="utility-3600x2400-1-200",
        title="Utility room 3600 x 2400 at 1:200",
        description=(
            "Draw a 3600 x 2400 mm utility room at 1:200 with 100 mm walls, one "
            "800 mm door and one 600 mm window."
        ),
        room_width_mm=3600,
        room_height_mm=2400,
        wall_thickness_mm=100,
        scale_denominator=200,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=600, count=1, wall="north", sill_height_mm=1500
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3600, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=2400, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def compact_study_1_20() -> ExerciseCreate:
    return ExerciseCreate(
        slug="study-2400x2400-1-20",
        title="Compact study 2400 x 2400 at 1:20",
        description=(
            "Draw a 2400 x 2400 mm study at 1:20 with 100 mm walls, one 800 mm "
            "door and one 900 mm window."
        ),
        room_width_mm=2400,
        room_height_mm=2400,
        wall_thickness_mm=100,
        scale_denominator=20,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=900, count=1, wall="west", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=2400, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def cabin_3600x3000_1_100() -> ExerciseCreate:
    return ExerciseCreate(
        slug="cabin-3600x3000-1-100",
        title="Cabin 3600 x 3000 at 1:100",
        description=(
            "Draw a 3600 x 3000 mm cabin at 1:100 with 115 mm walls, one 800 mm "
            "door and one 900 mm window."
        ),
        room_width_mm=3600,
        room_height_mm=3000,
        wall_thickness_mm=115,
        scale_denominator=100,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=900, count=1, wall="north", sill_height_mm=800
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3600, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=3000, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def twin_bedroom_3600x3300_1_50() -> ExerciseCreate:
    return ExerciseCreate(
        slug="twin-bedroom-3600x3300-1-50",
        title="Twin bedroom 3600 x 3300 at 1:50",
        description=(
            "Draw a 3600 x 3300 mm twin bedroom at 1:50 with 115 mm walls, one "
            "800 mm door and one 1500 mm window."
        ),
        room_width_mm=3600,
        room_height_mm=3300,
        wall_thickness_mm=115,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="east")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1500, count=1, wall="north", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3600, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def kitchen_3900x3600_1_50() -> ExerciseCreate:
    return ExerciseCreate(
        slug="kitchen-3900x3600-1-50",
        title="Kitchen 3900 x 3600 at 1:50",
        description=(
            "Draw a 3900 x 3600 mm kitchen at 1:50 with 200 mm walls, one 1000 mm "
            "door and one 1200 mm window."
        ),
        room_width_mm=3900,
        room_height_mm=3600,
        wall_thickness_mm=200,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=1000, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1200, count=1, wall="north", sill_height_mm=1100
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3900, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=3600, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def store_3000x2400_1_100() -> ExerciseCreate:
    return ExerciseCreate(
        slug="store-3000x2400-1-100",
        title="Store 3000 x 2400 at 1:100",
        description=(
            "Draw a 3000 x 2400 mm store at 1:100 with 230 mm walls and one 800 mm "
            "door. No windows: it is an unlit internal space."
        ),
        room_width_mm=3000,
        room_height_mm=2400,
        wall_thickness_mm=230,
        scale_denominator=100,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3000, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def pantry_2100x2400_1_20() -> ExerciseCreate:
    return ExerciseCreate(
        slug="pantry-2100x2400-1-20",
        title="Pantry 2100 x 2400 at 1:20",
        description=(
            "Draw a 2100 x 2400 mm pantry at 1:20 with 100 mm walls and one 800 mm "
            "door."
        ),
        room_width_mm=2100,
        room_height_mm=2400,
        wall_thickness_mm=100,
        scale_denominator=20,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=2100, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def bathroom_2700x2400_1_20() -> ExerciseCreate:
    return ExerciseCreate(
        slug="bathroom-2700x2400-1-20",
        title="Bathroom 2700 x 2400 at 1:20",
        description=(
            "Draw a 2700 x 2400 mm bathroom at 1:20 with 100 mm walls, one 800 mm "
            "door and one 600 mm window."
        ),
        room_width_mm=2700,
        room_height_mm=2400,
        wall_thickness_mm=100,
        scale_denominator=20,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=600, count=1, wall="east", sill_height_mm=1500
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=2700, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=2400, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def double_bedroom_4500x4000_1_50() -> ExerciseCreate:
    return ExerciseCreate(
        slug="double-bedroom-4500x4000-1-50",
        title="Double bedroom 4500 x 4000 at 1:50",
        description=(
            "Draw a 4500 x 4000 mm double bedroom at 1:50 with 230 mm walls, one "
            "900 mm door, one 1500 mm window and both room dimensions."
        ),
        room_width_mm=4500,
        room_height_mm=4000,
        wall_thickness_mm=230,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=900, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1500, count=1, wall="north", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=4500, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=4000, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def twin_opening_office_4800x3600_1_50() -> ExerciseCreate:
    return ExerciseCreate(
        slug="office-4800x3600-1-50-two-doors",
        title="Office 4800 x 3600 at 1:50, two doors",
        description=(
            "Draw a 4800 x 3600 mm office at 1:50 with 115 mm walls, two 800 mm "
            "doors on different walls and one 1200 mm window."
        ),
        room_width_mm=4800,
        room_height_mm=3600,
        wall_thickness_mm=115,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south"),
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="east"),
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1200, count=1, wall="north", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=4800, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def living_room_6600x4200_1_100() -> ExerciseCreate:
    return ExerciseCreate(
        slug="living-room-6600x4200-1-100",
        title="Living room 6600 x 4200 at 1:100",
        description=(
            "Draw a 6600 x 4200 mm living room at 1:100 with 200 mm walls, a "
            "1200 mm double door and two 1800 mm windows."
        ),
        room_width_mm=6600,
        room_height_mm=4200,
        wall_thickness_mm=200,
        scale_denominator=100,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=1200, count=1, wall="west")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1800, count=2, wall="north", sill_height_mm=450
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=6600, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=4200, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def laundry_3000x2700_1_50() -> ExerciseCreate:
    return ExerciseCreate(
        slug="laundry-3000x2700-1-50",
        title="Laundry 3000 x 2700 at 1:50",
        description=(
            "Draw a 3000 x 2700 mm laundry at 1:50 with 115 mm walls, one 800 mm "
            "door and one 900 mm window."
        ),
        room_width_mm=3000,
        room_height_mm=2700,
        wall_thickness_mm=115,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=900, count=1, wall="north", sill_height_mm=1000
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3000, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def workshop_7200x5400_1_200() -> ExerciseCreate:
    return ExerciseCreate(
        slug="workshop-7200x5400-1-200",
        title="Workshop 7200 x 5400 at 1:200",
        description=(
            "Draw a 7200 x 5400 mm workshop at 1:200 with 230 mm walls, a 1200 mm "
            "double door and a 2400 mm wide opening."
        ),
        room_width_mm=7200,
        room_height_mm=5400,
        wall_thickness_mm=230,
        scale_denominator=200,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=1200, count=1, wall="south")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=2400, count=1, wall="north", sill_height_mm=1200
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=7200, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def hall_4500x2400_1_50() -> ExerciseCreate:
    return ExerciseCreate(
        slug="hall-4500x2400-1-50",
        title="Hall 4500 x 2400 at 1:50",
        description=(
            "Draw a 4500 x 2400 mm hall at 1:50 with 115 mm walls, one 900 mm "
            "door and both room dimensions. Note how narrow the room is."
        ),
        room_width_mm=4500,
        room_height_mm=2400,
        wall_thickness_mm=115,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=900, count=1, wall="west")
        ],
        window_requirements=[],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=4500, on_wall="south"),
            DimensionRequirement(axis="height", value_mm=2400, on_wall="west"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


def home_office_3300x3000_1_50() -> ExerciseCreate:
    return ExerciseCreate(
        slug="home-office-3300x3000-1-50",
        title="Home office 3300 x 3000 at 1:50",
        description=(
            "Draw a 3300 x 3000 mm home office at 1:50 with 100 mm walls, one 800 mm "
            "door and one 1200 mm window."
        ),
        room_width_mm=3300,
        room_height_mm=3000,
        wall_thickness_mm=100,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=800, count=1, wall="east")
        ],
        window_requirements=[
            OpeningRequirement(
                kind="window", width_mm=1200, count=1, wall="north", sill_height_mm=900
            )
        ],
        dimension_requirements=[
            DimensionRequirement(axis="width", value_mm=3300, on_wall="south"),
        ],
        difficulty=Difficulty.BEGINNER,
    )


ALL_EXERCISES = (
    # Beginner: one variable at a time, so a first-time student can succeed
    # before scale, windows, placement and both dimensions are all in play.
    small_study,
    north_star_bedroom,
    compact_study_1_20,
    utility_room,
    cabin_3600x3000_1_100,
    wide_office,
    twin_bedroom_3600x3300_1_50,
    kitchen_3900x3600_1_50,
    store_3000x2400_1_100,
    pantry_2100x2400_1_20,
    bathroom_2700x2400_1_20,
    laundry_3000x2700_1_50,
    home_office_3300x3000_1_50,
    living_room,
    generous_bedroom,
    # Intermediate: multiple openings, both dimensions, less forgiving briefs.
    double_bedroom_4500x4000_1_50,
    twin_opening_office_4800x3600_1_50,
    living_room_6600x4200_1_100,
    workshop_7200x5400_1_200,
    hall_4500x2400_1_50,
)


def main() -> None:
    factory = get_session_factory()
    with factory() as db:
        for builder in ALL_EXERCISES:
            payload = builder()
            exercise = upsert_exercise(db, payload)
            print(
                f"{exercise.slug:32} {exercise.room_width_mm}x"
                f"{exercise.room_height_mm} mm  1:{exercise.scale_denominator:<4} "
                f"{exercise.wall_thickness_mm} mm walls"
            )
        print(f"\n{len(ALL_EXERCISES)} beginner exercises ready.")


if __name__ == "__main__":
    main()
