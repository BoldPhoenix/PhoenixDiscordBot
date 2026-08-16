"""EOS ID validation, and the two failures it exists to prevent.

2026-08-11: Deez_Knutz721 bought five store items and received none of them. His stored EOS ID was
`00020a296f5a40bead8da6875daeb0e` — the real one, `00020a296f5a40bead8da6875d6aeb0e`, with a single
`6` dropped at index 26. A MIDDLE truncation, so it starts and ends correctly and reads as valid.

Everything downstream matches EOS exactly, so `shop.try_deliver()` never found him on login, his
purchases queued with `server_name='unknown'`, and the queue never drained. No error was raised
anywhere: the bot did exactly what it should for a player it cannot find.

The link modal let it through because it only set `max_length=32`. A maximum is not a format.
"""
import pytest

from bot.utils.eos import EOS_LENGTH, InvalidEosId, is_valid_eos_id, normalize_eos_id

REAL = "00020a296f5a40bead8da6875d6aeb0e"      # what the server reports
TRUNCATED = "00020a296f5a40bead8da6875daeb0e"  # what was in the database, 31 chars


def test_the_actual_bad_id_is_rejected():
    """The regression, named. This is the exact string that cost a player five purchases."""
    assert len(TRUNCATED) == 31
    with pytest.raises(InvalidEosId) as e:
        normalize_eos_id(TRUNCATED)
    assert "31" in str(e.value), "the error must state the length — 31 vs 32 is invisible otherwise"


def test_the_real_id_is_accepted():
    assert normalize_eos_id(REAL) == REAL
    assert is_valid_eos_id(REAL)


def test_a_max_length_check_alone_would_not_have_caught_it():
    """Guards the actual design point, not just the symptom.

    The modal's max_length=32 accepted the bad ID because 31 <= 32. Any replacement that only
    bounds the upper end reintroduces the bug, so assert the LOWER end is enforced too."""
    assert len(TRUNCATED) <= EOS_LENGTH, "premise: the bad value passes a max-length check"
    assert not is_valid_eos_id(TRUNCATED), "a max-length check is not enough; length must be exact"


@pytest.mark.parametrize(
    "raw",
    [
        f"  {REAL}  ",          # padded paste
        f"`{REAL}`",            # pasted out of Discord code formatting
        f'"{REAL}"',            # quoted
        REAL.upper(),           # upper-case hex from an overlay
        f"{REAL[:16]} {REAL[16:]}",   # a space introduced mid-paste
    ],
)
def test_shapes_people_actually_paste_are_accepted(raw):
    assert normalize_eos_id(raw) == REAL


@pytest.mark.parametrize(
    "raw,why",
    [
        ("", "empty"),
        (None, "missing"),
        ("g" * 32, "non-hex characters"),
        (REAL + "0", "one too many"),
        (REAL[:-1], "one too few"),
        ("00020a296f5a40bead8da6875d6aeb0z", "trailing non-hex"),
    ],
)
def test_bad_input_is_rejected(raw, why):
    assert not is_valid_eos_id(raw), f"should reject: {why}"


def test_non_hex_error_names_the_offending_characters():
    """A player has to be able to act on the message without asking an admin."""
    with pytest.raises(InvalidEosId) as e:
        normalize_eos_id("00020a296f5a40bead8da6875d6aebZZ")
    assert "z" in str(e.value).lower()


def test_the_error_is_safe_to_show_a_player():
    """These strings go straight into a Discord reply, so they must not leak internals."""
    for bad in (TRUNCATED, "nope", "", "g" * 32):
        try:
            normalize_eos_id(bad)
        except InvalidEosId as e:
            msg = str(e)
            assert "Traceback" not in msg and "None" not in msg
            assert len(msg) < 300
