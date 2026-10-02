"""The tutor must never be a second source of numbers.

The tutor is the one part of this system that can say something a student will
act on, and the one part that can say it wrongly. A model is free to write
"you are 137 mm off" on a 14 mm error, and a student who believes it will chase
the wrong number for a week.

So the model is shown the engine's figures and nothing else, and whatever comes
back is checked against those figures. If it mentions a number the engine never
produced, the whole answer is discarded and the deterministic explanation is
used instead. Discarding the entire answer is deliberate: a response with one
invented number in it is not partially usable, because the student cannot tell
which part to trust.

These tests cover the guard directly rather than through a model, so they run
with no credentials and no network.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.geometry.drawing import StudentDrawing
from app.learning.feedback import build_feedback
from app.measurement.scale import InvalidDimensionError, calculate_scale
from app.schemas.exercise import ExerciseRead
from app.tutor.guard import (
    allowed_numbers,
    numbers_in,
    unsupported_numbers,
)
from app.tutor.service import (
    MAX_COMPLETION_TOKENS,
    TutorResponseError,
    _call_model,
    _content_of,
    _issue_payload,
    deterministic_explanation,
    explain_issue,
    tutor_configured,
)
from app.validation.engine import validate_drawing
from tests.factories import north_star_drawing, north_star_exercise_payload


def _exercise(**overrides) -> ExerciseRead:
    """The north-star brief, so the figures below are the ones the test expects."""
    return ExerciseRead.model_validate(
        {
            **north_star_exercise_payload(),
            "id": "00000000-0000-0000-0000-0000000000ff",
            "created_at": "2026-01-01T00:00:00+00:00",
            **overrides,
        }
    )


@pytest.fixture(scope="module")
def room_issue():
    """One ROOM_DIMENSION_ERROR with every figure the tutor would need.

    70 mm drawn where 1:50 requires 84 mm: the brief wants 4200 mm, the sheet
    currently says 3500 mm, and the difference is 14 mm.
    """
    exercise = _exercise()
    drawing = StudentDrawing.from_dict(north_star_drawing(room_width_mm=70))
    result = validate_drawing(exercise, drawing)
    return build_feedback(result.findings, drawing=drawing)[0].to_dict()


class TestNumberExtraction:
    def test_it_reads_the_numbers_a_tutor_actually_writes(self):
        found = numbers_in("At 1:50, 4200 mm becomes 84 mm on the sheet.")

        assert "1:50" in found
        assert "4200" in found
        assert "84" in found

    def test_an_ordinal_is_not_a_measurement(self):
        """Otherwise "the 1st rule" would look like an invented number."""
        assert numbers_in("Follow the 1st rule.") == []

    def test_a_list_marker_is_not_a_measurement(self):
        """Asked for steps, a model answers with a numbered list.

        This was found by running the real model against a real issue: every
        explanation that came back as a list was discarded for the invented
        numbers "2" and "3", which were only ever line numbers.
        """
        listed = (
            "Fix the room width like this.\n"
            "1. Check the scale against the brief.\n"
            "2. Convert the dimension to the sheet.\n"
            "3. Redraw the boundary.\n"
        )

        assert numbers_in(listed) == []
        assert numbers_in("  7) Redraw it at that size.") == []

    def test_a_step_reference_is_not_a_measurement(self):
        assert numbers_in("In step 2 you convert to the sheet.") == []
        assert "2" not in numbers_in("Repeat step 2, then check again.")

    def test_a_measurement_at_the_start_of_a_line_is_still_a_measurement(self):
        """The marker pattern must not swallow a real figure."""
        found = numbers_in("72 mm on the sheet is what 1:50 requires.\n3600 mm is the real size.")

        assert "72" in found
        assert "1:50" in found
        assert "3600" in found

    def test_a_grouped_number_is_one_number(self):
        """Models group thousands the way the SI standard does.

        "2 900 mm" is the engine's own 2900, written with a thin space. Read as
        two numbers, the guard reported the invented figures "2" and "900" and
        threw away an explanation that had quoted the measurement correctly.
        """
        for written, expected in (
            ("2 900 mm", "2900"),
            ("2\u2009900 mm", "2900"),
            ("2\u202f900 mm", "2900"),
            ("3 600 mm", "3600"),
        ):
            assert numbers_in(f"the real width is {written}") == [expected]

    def test_a_spaced_pair_is_not_treated_as_a_grouped_number(self):
        """The grouping rule is the convention, not any digit space digit."""
        assert numbers_in("at 1 : 50 the room is 72 mm") == ["1:50", "72"]

    def test_a_negative_number_keeps_its_sign(self):
        assert "-14" in numbers_in("that is -14 mm out")


class TestAllowedNumbers:
    def test_it_licenses_every_figure_the_engine_produced(self, room_issue):
        allowed = allowed_numbers(_issue_payload(room_issue))

        assert {"4200", "3500", "84", "70", "14"} <= allowed

    def test_a_bare_denominator_licenses_the_ratio_it_is_written_as(
        self, room_issue
    ):
        """The engine stores 50; a tutor and a student both write 1:50."""
        allowed = allowed_numbers(_issue_payload(room_issue))

        assert "1:50" in allowed

    def test_a_room_dimension_is_not_licensed_as_a_scale(self, room_issue):
        """4200 mm is a length, not a denominator, so 1:4200 is nonsense."""
        allowed = allowed_numbers(_issue_payload(room_issue))

        assert "1:4200" not in allowed

    def test_the_signed_difference_licenses_the_unsigned_mention(self, room_issue):
        """The engine stores -14; prose says "14 mm short" without the sign."""
        allowed = allowed_numbers(_issue_payload(room_issue))

        assert "-14" in allowed
        assert "14" in allowed

    def test_a_figure_in_the_engines_own_sentence_is_allowed(self):
        """Restating the issue's own wording is not inventing a number.

        Found on a real dimension issue: ``what_is_wrong`` reads "3600 mm is
        72 mm at 1:50", the metadata does not repeat the scale, and the model was
        blocked for saying "1:50" back to the student.
        """
        allowed = allowed_numbers(
            {
                "what_is_wrong": "The width dimension line spans 58 mm; 3600 mm is 72 mm at 1:50.",
                "expected": "72",
                "actual": "58",
                "metadata": {"axis": "width"},
            }
        )

        assert {"1:50", "3600", "72", "58"} <= allowed
        assert "50" in allowed

    def test_prose_does_not_license_a_number_it_does_not_contain(self):
        """Harvesting the engine's sentences must not license anything else."""
        allowed = allowed_numbers({"why_it_matters": "The room governs floor area."})

        assert allowed == set()


class TestUnsupportedNumbers:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # Correct restatements: must survive, or the guard is punishing
            # accurate teaching.
            ("Redraw the room 84 mm wide on the sheet.", []),
            ("The brief asks for 4200 mm, which is 3500 mm at 1:50.", []),
            ("Divide 4200 by 50 to get 84 mm.", []),
            ("The room is 14 mm short of the 84 mm the sheet needs.", []),
            # Inventions: must be caught.
            ("Change the wall to 137 mm.", ["137"]),
            ("The width should be 84.7 mm.", ["84.7"]),
            ("Try drawing at 1:100 instead.", ["1:100"]),
            ("You are 18 mm out.", ["18"]),
        ],
    )
    def test_it_names_only_the_numbers_the_engine_never_produced(
        self, room_issue, text, expected
    ):
        allowed = allowed_numbers(_issue_payload(room_issue))

        assert unsupported_numbers(text, allowed) == expected

    def test_a_figure_from_a_different_issue_is_still_unsupported(
        self, room_issue
    ):
        """230 mm is a real number from this exercise, but not from this issue.

        The tutor is shown one issue at a time. Letting it reach for a correct
        figure belonging to a different finding is how a confident wrong answer
        gets written.
        """
        allowed = allowed_numbers(_issue_payload(room_issue))

        assert unsupported_numbers("Use 230 mm walls.", allowed) == ["230"]


class TestDeterministicExplanation:
    def test_it_names_the_measurement_and_the_fix(self, room_issue):
        text = deterministic_explanation(room_issue)

        assert "84" in text
        assert room_issue["why_it_matters"] in text

    def test_it_never_claims_a_number_the_engine_did_not_produce(
        self, room_issue
    ):
        """The fallback is the answer of last resort, so it has to be clean.

        If the offline path ever introduces a figure, it has done the one thing
        the guard exists to prevent, with no model involved and no check.
        """
        allowed = allowed_numbers(_issue_payload(room_issue))

        assert unsupported_numbers(deterministic_explanation(room_issue), allowed) == []

    def test_it_tells_the_student_to_check_again(self, room_issue):
        """The loop closes on a verdict, not on the student's confidence."""
        assert "check again" in deterministic_explanation(room_issue).lower()


class TestExplainIssue:
    def test_it_works_with_no_credentials_configured(self, monkeypatch, room_issue):
        """The tutor is optional, so the endpoint is never allowed to fail.

        A student with no tutor configured, or an operator who never set a key,
        must still get a complete explanation rather than a 500.
        """
        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: False)

        result = explain_issue(room_issue)

        assert result.source == "deterministic"
        assert result.explanation
        assert result.model is None

    def test_a_model_answer_mentioning_an_invented_number_is_discarded(
        self, monkeypatch, room_issue
    ):
        """The guard's purpose, end to end.

        The model is stubbed to return a fluent, plausible, wrong answer. The
        whole response is dropped and the deterministic one is used, because a
        response containing a fabricated figure cannot be partially trusted.
        """
        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: True)
        monkeypatch.setattr(
            "app.tutor.service._call_model",
            lambda payload: "The room is 137 mm too wide; redraw it at 1:20.",
        )

        result = explain_issue(room_issue)

        assert result.source == "deterministic"
        assert "137" not in result.explanation
        assert result.blocked_numbers

    def test_a_model_answer_written_as_a_list_is_kept(
        self, monkeypatch, room_issue
    ):
        """The real answer from the real model, kept.

        This is the explanation Groq produced for a real room-width issue. It
        used no figure the engine had not measured, and it was thrown away
        anyway because it numbered its steps. Enumerating advice is formatting,
        not a claim about the drawing, so the guard has to see it as such --
        otherwise the tutor is switched off in practice and the fallback is the
        only thing a student ever reads.
        """
        answer = (
            "Room width is 70 mm on the sheet; 1:50 requires 84 mm.\n\n"
            "Fix it to 84 mm on the sheet, then check again.\n\n"
            "1. Check the scale you are working at against the brief.\n"
            "2. Convert the required real-world dimension to the sheet.\n"
            "3. Redraw the room boundary at that size."
        )
        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: True)
        monkeypatch.setattr("app.tutor.service._call_model", lambda payload: answer)

        result = explain_issue(room_issue)

        assert result.source == "llm"
        assert not result.blocked_numbers
        assert "Redraw the room boundary" in result.explanation

    def test_a_list_marker_does_not_excuse_an_invented_number(
        self, monkeypatch, room_issue
    ):
        """Fixing the marker false positive must not weaken the guard.

        The same list, with one fabricated figure in it, is still discarded.
        """
        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: True)
        monkeypatch.setattr(
            "app.tutor.service._call_model",
            lambda payload: (
                "Room width is 70 mm on the sheet; 1:50 requires 84 mm.\n"
                "1. Set the wall to 230 mm, which is the usual partition.\n"
                "2. Check again."
            ),
        )

        result = explain_issue(room_issue)

        assert result.source == "deterministic"
        assert "230" not in result.explanation
        assert "230" in result.blocked_numbers
        # The markers are not what did it: they are invisible to the guard.
        assert "1" not in result.blocked_numbers
        assert "2" not in result.blocked_numbers

    def test_a_model_answer_within_the_evidence_is_kept(self, monkeypatch, room_issue):
        """The guard must not be so strict that the tutor can never be used."""
        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: True)
        monkeypatch.setattr(
            "app.tutor.service._call_model",
            lambda payload: (
                "The sheet is 70 mm where 1:50 needs 84 mm. Divide the 4200 mm "
                "width by 50 to get the size you actually need to draw."
            ),
        )

        result = explain_issue(room_issue)

        assert result.source == "llm"
        assert result.blocked_numbers == []

    def test_a_model_failure_falls_back_rather_than_raising(
        self, monkeypatch, room_issue
    ):
        """A provider outage must not become a student's error page."""
        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: True)

        def _explode(payload):
            raise TimeoutError("provider did not respond")

        monkeypatch.setattr("app.tutor.service._call_model", _explode)

        result = explain_issue(room_issue)

        assert result.source == "deterministic"
        assert result.explanation

    def test_a_rate_limited_provider_falls_back(self, monkeypatch, room_issue):
        """429 is a normal event, not an outage.

        Hit for real by asking the same question ten times in a row while
        checking the guard, which is what surfaced this case. The student should
        get the deterministic explanation, not a 500.
        """
        import httpx

        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: True)

        def _limited(payload):
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=httpx.Request("POST", "https://provider.test/chat/completions"),
                response=httpx.Response(429),
            )

        monkeypatch.setattr("app.tutor.service._call_model", _limited)

        result = explain_issue(room_issue)

        assert result.source == "deterministic"
        assert result.explanation
        assert not result.blocked_numbers


class TestProviderResponseShape:
    """Reading a chat completion, which is where providers differ.

    Every shape here was seen on a real OpenAI-compatible endpoint, because the
    failure it prevents is a student being shown a provider's error text in place
    of an explanation.
    """

    def test_a_reasoning_model_answers_with_prose_and_not_its_thoughts(self):
        data = {
            "choices": [
                {
                    "message": {
                        "content": "The sheet is 70 mm where 1:50 needs 84 mm.",
                        "reasoning": "internal chain of thought, never shown",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        text = _content_of(data)

        assert text == "The sheet is 70 mm where 1:50 needs 84 mm."
        assert "chain of thought" not in text

    @pytest.mark.parametrize(
        "data",
        [
            {},
            {"choices": []},
            # What a reasoning model returns when it spends the whole budget
            # thinking: a choice with nothing to say.
            {"choices": [{"message": {"content": None}, "finish_reason": "length"}]},
            {"choices": [{"message": {"content": "   "}}]},
            {"choices": [{"message": {"content": 42}}]},
        ],
    )
    def test_a_response_without_an_explanation_is_refused(self, data):
        """Falling back is the contract. ``"None"`` shown to a student is not."""
        with pytest.raises(TutorResponseError):
            _content_of(data)

    def test_the_reasoning_effort_is_sent_when_it_is_configured(
        self, monkeypatch, room_issue
    ):
        """A reasoning model given a generous budget thinks instead of answering.

        Measured on Groq's gpt-oss family: without this, 437 of 600 tokens went
        to thinking and the sentence was still unfinished. With it, the same
        request used 141 tokens and came back whole.
        """
        seen: dict[str, object] = {}

        class _Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"choices": [{"message": {"content": "Redraw it at 84 mm."}}]}

        class _Client:
            def __init__(self, **kwargs: object) -> None:
                return None

            def __enter__(self) -> "_Client":
                return self

            def __exit__(self, *exc: object) -> bool:
                return False

            def post(self, url: str, json: dict, headers: dict) -> _Response:
                seen["body"] = json
                return _Response()

        fake = ModuleType("httpx")
        fake.Client = _Client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "httpx", fake)
        monkeypatch.setattr(
            "app.tutor.service.settings",
            SimpleNamespace(
                tutor_base_url="https://api.groq.com/openai/v1",
                tutor_api_key="test-key-not-a-real-one",
                tutor_model="openai/gpt-oss-20b",
                tutor_reasoning_effort="low",
            ),
        )

        _call_model({"code": "ROOM_DIMENSION_ERROR"})

        assert seen["body"]["reasoning_effort"] == "low"

    def test_an_empty_answer_falls_back_rather_than_being_shown(
        self, monkeypatch, room_issue
    ):
        monkeypatch.setattr("app.tutor.service.tutor_configured", lambda: True)

        def _refuse(payload):
            raise TutorResponseError("empty content (finish_reason=length)")

        monkeypatch.setattr("app.tutor.service._call_model", _refuse)

        result = explain_issue(room_issue)

        assert result.source == "deterministic"
        assert result.explanation.strip()

    def test_the_call_carries_the_budget_and_the_key(self, monkeypatch, room_issue):
        """The request is the part a provider rejects outright if it is wrong."""
        seen: dict[str, object] = {}

        class _Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"choices": [{"message": {"content": "Redraw it at 84 mm."}}]}

        class _Client:
            def __init__(self, **kwargs: object) -> None:
                seen["timeout"] = kwargs["timeout"]

            def __enter__(self) -> "_Client":
                return self

            def __exit__(self, *exc: object) -> bool:
                return False

            def post(self, url: str, json: dict, headers: dict) -> _Response:
                seen.update(url=url, body=json, headers=headers)
                return _Response()

        fake = ModuleType("httpx")
        fake.Client = _Client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "httpx", fake)
        monkeypatch.setattr(
            "app.tutor.service.settings",
            SimpleNamespace(
                tutor_base_url="https://api.groq.com/openai/v1/",
                tutor_api_key="test-key-not-a-real-one",
                tutor_model="openai/gpt-oss-20b",
                tutor_reasoning_effort=None,
            ),
        )
        monkeypatch.setattr("app.tutor.service.unsupported_numbers", lambda t, a: [])

        assert _call_model({"code": "ROOM_DIMENSION_ERROR"}) == "Redraw it at 84 mm."
        assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
        assert seen["headers"]["Authorization"] == "Bearer test-key-not-a-real-one"
        assert seen["body"]["model"] == "openai/gpt-oss-20b"
        assert seen["body"]["max_tokens"] == MAX_COMPLETION_TOKENS
        assert seen["body"]["temperature"] == 0
        # Absent unless configured: a provider that does not know the parameter
        # answers 400, and a 400 would mean never seeing a model explanation.
        assert "reasoning_effort" not in seen["body"]
        assert [message["role"] for message in seen["body"]["messages"]] == [
            "system",
            "user",
        ]


class TestScaleEdgeCases:
    def test_a_zero_length_reports_a_readable_reason(self):
        """The message has to survive being shown to a student.

        A zero length has no reciprocal scale, and the reason is reported rather
        than the failure being swallowed into a bare "no scale fits".
        """
        with pytest.raises(InvalidDimensionError) as caught:
            calculate_scale(4200, 0)

        message = str(caught.value)
        assert "4200" in message
        assert "0" in message


def test_tutor_is_not_configured_in_the_test_environment():
    """Guards the tests above: a stray .env must not make them vacuous."""
    assert tutor_configured() is False
