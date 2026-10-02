"""The mistake taxonomy: what kind of thing a student got wrong.

WHY A TAXONOMY
--------------
A :class:`~app.validation.findings.Finding` says *what* is wrong -- a room
width of 42 mm where 84 mm was required. That is the evidence. It does not say
what the student *misunderstood*, because that is an inference, and the
validation engine is not allowed to make inferences about a person.

The taxonomy is where that inference is made, once, in one place, and stored as
structured data. A student's recurring errors become countable:

    {"SCALE_CONVERSION": 2, "WALL_THICKNESS": 4, "ROOM_DIMENSION": 1}

which is the foundation adaptive learning needs. It cannot be derived later from
a pile of prose, because prose does not survive being counted.

DETERMINISTIC
-------------
Every mapping here is a total function of the finding. No model, no guess. The
same finding always produces the same category, so the stored history stays
honest: a category count can always be traced back to the findings behind it.

WHY A FINDING GETS *ONE* CATEGORY
---------------------------------
Some findings are tempting to file twice. A student who drew the room at 1:100
has both a scale problem and a room-size problem. The scale check and the room
check each report their own finding; those are separate findings and each is
filed on its own merits.

But a *single* finding gets a single category, so that summing categories
reproduces the finding count. A student with five errors has five categorised
findings, and a dashboard that says otherwise is lying.
"""

from __future__ import annotations

import enum
from collections import Counter
from typing import Any, Iterable, Mapping

from app.validation.codes import FindingCode
from app.validation.findings import Finding


class MistakeCategory(str, enum.Enum):
    """What the student misjudged, as distinct from what is wrong.

    The member name and the value are identical, as with finding codes: these
    strings are stored in the database and asserted in tests.
    """

    SCALE_CONVERSION = "SCALE_CONVERSION"
    """Drew the sheet at a scale other than the one asked for."""

    UNIT_CONFUSION = "UNIT_CONFUSION"
    """Confused the two unit systems: real-world millimetres and sheet
    millimetres. Distinct from using the wrong scale, and diagnosed
    differently -- see :func:`category_for`."""

    ROOM_DIMENSION = "ROOM_DIMENSION"
    WALL_THICKNESS = "WALL_THICKNESS"
    OPENING_WIDTH = "OPENING_WIDTH"
    OPENING_PLACEMENT = "OPENING_PLACEMENT"
    DIMENSION_PLACEMENT = "DIMENSION_PLACEMENT"
    ALIGNMENT = "ALIGNMENT"
    MISSING_ELEMENT = "MISSING_ELEMENT"
    UNEXPECTED_ELEMENT = "UNEXPECTED_ELEMENT"
    """Drew more of something than the brief asked for.

    Beyond the nine categories the brief enumerates, and present because the
    validator can already report it. Filing it under MISSING_ELEMENT would be
    a false record -- a student who drew a second door has not drawn a missing
    element -- and a wrong category in a learning record is worse than an extra
    one, because it will later be counted as evidence about the student.
    """


CODE_TO_CATEGORY: Mapping[FindingCode, MistakeCategory] = {
    FindingCode.SCALE_ERROR: MistakeCategory.SCALE_CONVERSION,
    FindingCode.ROOM_DIMENSION_ERROR: MistakeCategory.ROOM_DIMENSION,
    FindingCode.WALL_THICKNESS_ERROR: MistakeCategory.WALL_THICKNESS,
    FindingCode.DOOR_WIDTH_ERROR: MistakeCategory.OPENING_WIDTH,
    FindingCode.WINDOW_WIDTH_ERROR: MistakeCategory.OPENING_WIDTH,
    FindingCode.DOOR_PLACEMENT_ERROR: MistakeCategory.OPENING_PLACEMENT,
    FindingCode.OPENING_PLACEMENT_ERROR: MistakeCategory.OPENING_PLACEMENT,
    FindingCode.DIMENSION_ERROR: MistakeCategory.DIMENSION_PLACEMENT,
    FindingCode.ALIGNMENT_ERROR: MistakeCategory.ALIGNMENT,
    FindingCode.MISSING_ELEMENT: MistakeCategory.MISSING_ELEMENT,
    FindingCode.UNEXPECTED_ELEMENT: MistakeCategory.UNEXPECTED_ELEMENT,
}

assert set(CODE_TO_CATEGORY) == set(FindingCode), (
    "every finding code must be categorised; a new code with no category would "
    "vanish from the learning record instead of being counted"
)

ONE_TO_ONE_SCALE = 1
"""The implied scale of a sheet drawn in real-world millimetres.

A student who skips the conversion entirely draws 4200 mm for a 4200 mm room.
The validator measures that as 1:1, which is the fingerprint of unit confusion
rather than a wrong scale choice: nobody drafts a 1:1 room on purpose, but
forgetting to divide by 50 is one of the most common first-year mistakes.

The 1:1 case is therefore reported as UNIT_CONFUSION and *not* as
SCALE_CONVERSION, even though both arrive as ``SCALE_ERROR``. The correction is
different -- "divide by 50" is not advice you give someone who merely picked
the wrong scale.
"""


def category_for(
    code: FindingCode, metadata: Mapping[str, Any] | None = None
) -> MistakeCategory:
    """The single category a finding is filed under.

    Takes the code and its metadata rather than a :class:`Finding`, because the
    stored form of a finding is exactly that pair. Working from the persisted
    shape means a category can be recomputed for an attempt recorded months ago,
    under a taxonomy that has since been revised -- which is what makes the
    stored counts auditable instead of merely historical.

    A scale finding is refined into UNIT_CONFUSION when the sheet measures as
    1:1, which means the student drew real-world millimetres on the sheet. Every
    other code maps straight through.
    """
    category = CODE_TO_CATEGORY[code]

    if code is FindingCode.SCALE_ERROR:
        implied = (metadata or {}).get("implied_scale_denominator")
        if implied == ONE_TO_ONE_SCALE:
            return MistakeCategory.UNIT_CONFUSION

    return category


def categorise(findings: Iterable[Finding]) -> list[MistakeCategory]:
    """Categories for findings, in the order the findings arrived."""
    return [category_for(f.code, f.metadata) for f in findings]


def categories_of_dicts(rows: Iterable[Mapping[str, Any]]) -> list[MistakeCategory]:
    """Categories for findings in their stored, serialised form."""
    from app.validation.codes import FindingCode

    return [
        category_for(FindingCode(row["code"]), row.get("metadata") or {})
        for row in rows
    ]


def category_counts(findings: Iterable[Finding]) -> dict[str, int]:
    """Count findings per category, as stored structured data.

    Sorted by category name so the stored dict is byte-stable and two attempts
    with identical findings serialise identically, which the reproducibility
    requirement extends to everything an attempt stores.
    """
    counts = Counter(category.value for category in categorise(findings))
    return dict(sorted(counts.items()))


def worst_categories(findings: Iterable[Finding]) -> list[str]:
    """Categories ordered by how often they were hit, most frequent first.

    Ties break alphabetically so the order is stable. Used to tell a student
    what to work on rather than listing nine categories at equal volume.
    """
    counts = Counter(categorise(findings))
    return [category.value for category, _ in sorted(
        counts.items(), key=lambda item: (-item[1], item[0].value)
    )]


def describe_category(category: MistakeCategory | str) -> str:
    """A short human label for a category, for display without an AI."""
    value = category.value if isinstance(category, MistakeCategory) else category
    return _CATEGORY_LABELS.get(value, value.replace("_", " ").title())


_CATEGORY_LABELS: dict[str, str] = {
    MistakeCategory.SCALE_CONVERSION.value: "Working at the wrong scale",
    MistakeCategory.UNIT_CONFUSION.value: "Mixing up real and sheet millimetres",
    MistakeCategory.ROOM_DIMENSION.value: "Room size",
    MistakeCategory.WALL_THICKNESS.value: "Wall thickness",
    MistakeCategory.OPENING_WIDTH.value: "Opening width",
    MistakeCategory.OPENING_PLACEMENT.value: "Opening position",
    MistakeCategory.DIMENSION_PLACEMENT.value: "Dimensioning",
    MistakeCategory.ALIGNMENT.value: "Wall alignment",
    MistakeCategory.MISSING_ELEMENT.value: "Missing elements",
    MistakeCategory.UNEXPECTED_ELEMENT.value: "Extra elements",
}


def learning_record(
    findings: Iterable[Finding],
) -> dict[str, Any]:
    """The structured learning data stored against an attempt.

    Deliberately small and countable. It answers "what did this student get
    wrong, in the vocabulary of misconception" without any prose, so it can be
    aggregated across attempts later.
    """
    findings = list(findings)
    counts = category_counts(findings)
    return {
        "categories": counts,
        "category_count": len(counts),
        "primary_category": (worst_categories(findings) or [None])[0],
    }
