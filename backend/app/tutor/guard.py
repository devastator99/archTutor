"""The guard on the tutor's output.

THE FAILURE THIS EXISTS FOR
---------------------------
A student submits a drawing. The engine has measured the north wall at 3 mm
where 4.6 mm was required. The model is asked to explain it, and replies:

    "Your wall is about 235 mm thick, which is slightly over the standard 230 mm."

Both figures are invented. 235 is not in the payload. 230 is the brief's figure
but is attached to the wrong quantity -- it is the required thickness in
real-world millimetres, while 3 mm is what was drawn *on the sheet*, and
comparing them as if they share a unit is exactly the unit confusion this
product exists to catch.

The numbers look plausible. Plausibility is the problem: a student cannot tell
an invented figure from a computed one, and will correct their drawing to match
it.

THE RULE
--------
Every number in the tutor's text must be one the engine already produced and
already showed the student. If it is not, the text is discarded and the
deterministic explanation is used instead.

Discarding the whole explanation rather than the offending sentence is
deliberate. A model that has invented 235 mm is not reliable in its other
sentences either, and a partially-corrected explanation invites the student to
work out which half to believe.

WHY NOT JUST ASK THE MODEL TO CHECK ITSELF
------------------------------------------
Because it cannot. A model asked "did you make that number up?" will say no.
The check has to be done by something that knows what the payload contains,
which is not the model.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.measurement.scale import MIN_SCALE_DENOMINATOR

MAX_PLAUSIBLE_SCALE_DENOMINATOR = 1000
"""Above this, "1:N" is not a scale a drawing is made at.

Architectural plans do not run past 1:500. The bound is here to stop a bare
room dimension such as 4200 from being licensed as the ratio 1:4200, which
would let a model invent nonsense scales while passing the guard.
"""

# Numbers as they appear in prose. Deliberately conservative about what counts:
#
#   4200        an integer
#   4.6         a decimal
#   1:50        a scale ratio
#   1/50        the same ratio, written as a division
#   230mm, 4.6 mm, 20 cm   a number with a unit attached
#
# Ordinals and list markers are not quantities. "1:50" is captured by the ratio
# branch, not as the bare integer 1, because a bare 1 in prose is nearly always
# an article position rather than a measurement.
_NUMBER = re.compile(
    r"""
    (?<![\w.])                      # not mid-identifier, so "v1" and "4.6mm" edges behave
    (?P<ratio>\d+\s*[:/]\s*\d+)     # 1:50 or 1/50
    |(?P<num>\d+(?:\.\d+)?)         # 4200 or 4.6
    """,
    re.VERBOSE,
)

def numbers_in(text: str) -> list[str]:
    """Every numeric token in a piece of text, normalised.

    A token is normalised to a canonical numeric string so that ``4.60``,
    ``4.6`` and ``4.600`` compare equal. Without that, formatting differences
    would trip the guard on text that is in fact correct, and a guard that cries
    wolf gets switched off.

    A leading sign is kept. ``-14`` and ``14`` are different claims to a student
    reading "14 mm long" versus "14 mm short", so the guard needs to tell them
    apart; :func:`allowed_numbers` decides separately that the unsigned form of a
    signed difference is the same figure.
    """
    source = _join_grouped_digits(_strip_non_quantities(text or ""))
    found: list[str] = []
    for match in _NUMBER.finditer(source):
        token = match.group("ratio") or match.group("num")
        assert token is not None
        start = match.start()
        if match.group("ratio") is None and start > 0 and (source[start - 1] == "-"):
            token = f"-{token}"
        normalised = _normalise(token)
        if normalised is not None:
            found.append(normalised)
    return found


def _normalise(token: str) -> str | None:
    """Reduce a numeric token to a canonical comparable string.

    ``"1:50"``, ``"1/50"`` and ``"1 : 50"`` all become ``"1:50"``, and ``"50.0"``
    becomes ``"50"``. Anything that is not a quantity returns ``None`` so it is
    never compared as one: the caller is deciding whether a *number* was
    invented, not whether a word is spelt correctly.
    """
    compact = re.sub(r"\s+", "", token)
    if ":" in compact or "/" in compact:
        left, _, right = compact.partition(":" if ":" in compact else "/")
        try:
            return f"{int(left)}:{int(right)}"
        except ValueError:
            return None
    try:
        return _plain(Decimal(compact))
    except (InvalidOperation, ValueError):
        return None


def allowed_numbers(payload: Any) -> set[str]:
    """Every numeric value the deterministic engine produced for this issue.

    Built by walking the whole payload and harvesting anything that reads as a
    quantity, so the allowed set tracks the engine rather than a hand-maintained
    list of field names. A number the engine emitted is always permitted, and
    nothing else is.

    Every field is walked rather than a chosen few keys, because the numbers a
    tutor may restate are not confined to ``expected``/``actual``.

    The engine's own sentences are harvested too, and that is not a loosening.
    The rule is that the tutor may state a figure the engine produced *and
    showed the student*; ``what_is_wrong`` reads "3600 mm is 72 mm at 1:50", the
    student reads exactly that, and a model repeating the sentence back is
    restating. Before this, any issue whose ``metadata`` did not repeat the scale
    denied the model permission to repeat the scale out loud -- found on a real
    dimension issue, where the model was blocked for saying "1:50" in a sentence
    the engine had written.
    """
    allowed: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        else:
            if node is None or isinstance(node, bool):
                return
            text = node.strip() if isinstance(node, str) else None
            if isinstance(node, str):
                tokens = [_normalise(text)] if _is_numeric_token(text) else []
            else:
                tokens = [_plain(Decimal(str(node)))]
            # Prose: every quantity inside a sentence the engine wrote.
            if text and not tokens:
                tokens = numbers_in(text)
            for token in tokens:
                if token is None:
                    continue
                allowed.add(token)
                # "1:50" also licenses its two halves: a model writing "1:50"
                # and separately "50" is restating, not inventing.
                if ":" in token:
                    left, _, right = token.partition(":")
                    allowed.add(right)

    walk(payload)
    return allowed | _derived(allowed)


def _is_numeric_token(text: str) -> bool:
    """Whether a whole string is one quantity, such as ``"1:50"`` or ``"84"``."""
    return bool(text) and _normalise(text) is not None


def _derived(allowed: set[str]) -> set[str]:
    """Forms of an allowed figure that are the same figure, not a new one.

    Three equivalences, each of which would otherwise cause a *correct*
    explanation to be thrown away:

    * ``50`` also licenses ``1:50``. The engine stores a bare scale
      denominator; a tutor and a student both write the ratio.
    * ``-14`` also licenses ``14``. The engine records the signed difference,
      and prose says "14 mm short" without the sign.
    * ``1:50`` licenses its two halves, so a tutor may write the numerator or
      the denominator alone.

    Only scale denominators get the ratio treatment, and only for values that
    are plausible denominators, because ``1:4200`` is not a scale anybody draws
    at and licensing it would weaken the guard for no benefit.
    """
    derived: set[str] = set()
    for token in allowed:
        if token.startswith("-"):
            derived.add(token[1:])
        if ":" in token:
            left, _, right = token.partition(":")
            derived.add(left)
            derived.add(right)
    scales = {
        token
        for token in allowed
        if token.isdigit() and MIN_SCALE_DENOMINATOR <= int(token) <= MAX_PLAUSIBLE_SCALE_DENOMINATOR
    }
    derived |= {f"1:{token}" for token in scales}
    return derived


def _plain(value: Decimal) -> str:
    """A decimal as a plain number, never in exponent form.

    ``Decimal("4200").normalize()`` is ``4.2E+3``, which matches no number a
    person or a model would ever write. Normalising this way would reject the
    engine's own figures while accepting a token spelled ``4.2E+3``.
    """
    text = format(value.normalize(), "f")
    # Trailing zeros are dropped ("84.00" -> "84") so that the same quantity
    # written two ways compares equal, without losing a genuinely significant
    # digit.
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _strip_non_quantities(text: str) -> str:
    """Blank out digits that are formatting rather than measurement.

    Three things in prose carry digits that are not quantities, and each one
    costs a perfectly good explanation if the guard reads it as a figure:

    * An ordinal, as in "the 1st rule".
    * An ordered-list marker, as in "2. Redraw the boundary". This is the one
      that mattered in practice: asked for concrete steps, models answer with a
      numbered list, so every list threw its whole explanation away. Enumerating
      advice is formatting; a marker is a count of lines, not a length in mm.
    * A step reference, as in "in step 2". The system prompt asks for steps, so
      a model that refers back to one is following the instructions.

    The marker patterns require a delimiter or the word "step" around the digits,
    which is what keeps a real measurement safe: "72. " at the start of a line is
    a list marker, while "72 mm" and "1:50" are quantities and are left alone.

    Digits are replaced with spaces rather than deleted so the text keeps its
    length and a number's sign stays adjacent to the sign before it.
    """
    blanked = re.sub(
        r"\b\d+(?:st|nd|rd|th)\b",
        lambda m: " " * len(m.group()),
        text,
        flags=re.IGNORECASE,
    )
    blanked = re.sub(
        r"(?m)^([ \t]*)(\d{1,2})([.)])(?=[ \t])",
        lambda m: m.group(1) + " " * (len(m.group(2)) + 1),
        blanked,
    )
    return re.sub(
        r"\bsteps?\s+\d{1,2}\b",
        lambda m: " " * len(m.group()),
        blanked,
        flags=re.IGNORECASE,
    )


def _join_grouped_digits(text: str) -> str:
    """Rejoin a number written with digit-group spaces: "2 900" is 2900.

    Models group large figures the way the SI standard does, and a thin space is
    an ordinary space to a regex. Without this, one correctly written 2900 mm
    arrives at the guard as the two invented numbers 2 and 900, and a perfectly
    faithful restatement of the engine's own measured value is thrown away.

    The pattern is the convention rather than any digit-space-digit: a leading
    group of one to three digits followed by a group of exactly three, so "1 : 50"
    and any other spaced-out pair is left alone.
    """
    return re.sub(
        r"(?<!\d)(\d{1,3})[ \u00a0\u202f\u2009](?=\d{3}(?!\d))",
        r"\1",
        text,
    )


def unsupported_numbers(text: str, allowed: set[str]) -> list[str]:
    """Numbers in ``text`` that the engine did not produce.

    Returns them sorted and de-duplicated so the log line is stable and a
    repeated failure is recognisable as the same one.
    """
    candidates = numbers_in(text)
    found = {value for value in candidates if value not in allowed}
    return sorted(found)
