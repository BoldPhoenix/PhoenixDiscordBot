"""Parsing Gemini's reply must never raise, and a bad payload must never be reported as a dead network.

2026-08-12. The extraction was one chained line:

    parts = (data.get('candidates') or [{}])[0].get('content', {}).get('parts', [])
    text = '\\n'.join(p.get('text', '') for p in parts if p.get('text'))

It survives a missing/empty/null `candidates`, then raises on three shapes the API genuinely
returns — because `.get(key, default)` yields None for an EXPLICIT null instead of falling back:

    content is null    -> AttributeError
    parts is null      -> TypeError
    parts holds a str  -> AttributeError

Those landed in a bare `except Exception` whose message was
"Error: Unable to reach the Gemini API." So a payload-shape bug was reported to the player, AND
logged for the admin, as a network failure — sending whoever debugged it after the network and the
API key while Gemini was answering perfectly well. Misattributed errors cost more than loud ones.

This is a third-party payload whose shape we do not control and cannot test against upstream, which
is exactly the place not to assume a shape.
"""
import pytest

from bot.utils.phoenix_ai import extract_gemini_text


def _ok(text="hello"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_the_happy_path_still_works():
    assert extract_gemini_text(_ok("hello")) == "hello"


def test_multiple_parts_are_joined():
    data = {"candidates": [{"content": {"parts": [{"text": "a"}, {"text": "b"}]}}]}
    assert extract_gemini_text(data) == "a\nb"


@pytest.mark.parametrize(
    "data,why",
    [
        ({"candidates": [{"content": None}]}, "content explicitly null — used to AttributeError"),
        ({"candidates": [{"content": {"parts": None}}]}, "parts explicitly null — used to TypeError"),
        ({"candidates": [{"content": {"parts": ["oops"]}}]}, "a part that is a bare string"),
        ({"candidates": [{"content": {"parts": [None]}}]}, "a part that is null"),
        ({"candidates": [None]}, "a null candidate"),
        ({"candidates": ["nope"]}, "a candidate that is a string"),
        ({"candidates": []}, "empty candidates"),
        ({"candidates": None}, "null candidates"),
        ({}, "no candidates key at all"),
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked on safety, no candidates"),
        (None, "not a dict at all"),
        ("garbage", "a bare string instead of JSON object"),
    ],
)
def test_bad_shapes_return_empty_instead_of_raising(data, why):
    """Every one of these must come back as "" so the caller can say 'I couldn't generate a
    response' — the honest message — rather than raising into the transport handler."""
    assert extract_gemini_text(data) == "", f"should have returned empty for: {why}"


def test_the_three_shapes_that_used_to_raise():
    """Named explicitly, because these are the regression. Previously AttributeError/TypeError."""
    for data in (
        {"candidates": [{"content": None}]},
        {"candidates": [{"content": {"parts": None}}]},
        {"candidates": [{"content": {"parts": ["oops"]}}]},
    ):
        assert extract_gemini_text(data) == ""


def test_a_usable_part_survives_alongside_junk():
    """Partial garbage must not throw away the real answer."""
    data = {"candidates": [{"content": {"parts": [None, "junk", {"text": "the answer"}, {}]}}]}
    assert extract_gemini_text(data) == "the answer"


def test_empty_text_fields_are_dropped_not_joined_as_blanks():
    data = {"candidates": [{"content": {"parts": [{"text": ""}, {"text": "real"}]}}]}
    assert extract_gemini_text(data) == "real"


def test_transport_and_parse_failures_are_reported_differently():
    """The misattribution guard: the parse handler must not claim the API was unreachable.

    Reads the source rather than driving aiohttp, because the distinction lives in which except
    clause catches what — and the whole defect was that one clause caught both."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "bot" / "utils" / "phoenix_ai.py"
    body = src.read_text(encoding="utf-8", errors="replace")
    assert "except (aiohttp.ClientError, OSError)" in body, \
        "transport failures are no longer caught narrowly; a payload bug can be reported as a " \
        "network failure again"
    # Count the RETURN, not the prose: the docstring and comment above the handler both name the
    # string deliberately, and counting those made the first version of this test fail on its own
    # documentation.
    returns = body.count('return f"Error: Unable to reach the Gemini API')
    assert returns == 1, \
        f'the "unreachable" message is returned from {returns} places — it must belong to the ' \
        "transport handler alone, or a payload bug can wear a network failure's message again"
