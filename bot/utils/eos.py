"""EOS ID validation — one definition of "is this a real EOS ID", used by every entry point.

WHY THIS EXISTS (2026-08-11)
----------------------------
Deez_Knutz721 could buy from the store and never receive anything. His row looked fine to the eye:

    server reports  00020a296f5a40bead8da6875d6aeb0e   (32 chars)
    database had    00020a296f5a40bead8da6875daeb0e    (31 chars)

One character — a `6` at index 26 — was dropped somewhere between his implant and the form. That
is a MIDDLE truncation, so the string still starts and ends correctly and reads as a valid ID at a
glance. Nobody spotted it for days.

Everything downstream keys on an exact EOS match. `shop.try_deliver()` looks the player up with
`get_player_by_eos_id(eos_id)` using the ID the SERVER reports on login; a stored ID that can never
equal it means that lookup returns None on every single login. So he was never seen as online, his
purchases queued with `server_name='unknown'`, and the queue never drained. Five items owed, money
taken, nothing delivered, and no error anywhere — the bot behaved exactly as designed for a player
it could not find.

The linking modal accepted it because it only set `max_length=32`. A maximum is not a format: it
stops 33 and waves 31 through, which is the wrong half of the problem.

RULE: an EOS ID is exactly 32 hexadecimal characters. Validate on the way IN, where the user can
still fix it, not on the way out where it is somebody's missing loot.
"""
import re

EOS_LENGTH = 32
_EOS_RE = re.compile(r"^[0-9a-f]{%d}$" % EOS_LENGTH)


class InvalidEosId(ValueError):
    """Raised with a message that is safe (and useful) to show a player."""


def normalize_eos_id(raw: str) -> str:
    """Return the canonical form of `raw`, or raise InvalidEosId with a player-readable reason.

    Accepts the shapes people actually paste: surrounding whitespace, wrapping quotes or
    backticks (Discord code formatting), and upper-case hex. Everything else is rejected.

    The error message states the length it GOT, because the failure this was written for is a
    string that looks right until you count it.
    """
    if raw is None:
        raise InvalidEosId("No EOS ID was provided.")

    cleaned = str(raw).strip().strip("`'\"").strip()
    # Players paste from overlays and Discord messages; a stray space inside is a paste artefact,
    # never part of the ID.
    cleaned = cleaned.replace(" ", "").replace("​", "")
    cleaned = cleaned.lower()

    if not cleaned:
        raise InvalidEosId("No EOS ID was provided.")

    if not re.fullmatch(r"[0-9a-f]*", cleaned):
        bad = sorted({c for c in cleaned if c not in "0123456789abcdef"})
        raise InvalidEosId(
            "That EOS ID contains characters that aren't hexadecimal: "
            + ", ".join(f"`{c}`" for c in bad[:5])
            + ". An EOS ID uses only 0-9 and a-f."
        )

    if len(cleaned) != EOS_LENGTH:
        # Naming the count is the whole point: 31 vs 32 is invisible until someone counts.
        off = len(cleaned) - EOS_LENGTH
        direction = f"{abs(off)} too many" if off > 0 else f"{abs(off)} too few"
        raise InvalidEosId(
            f"That EOS ID is {len(cleaned)} characters ({direction}). "
            f"An EOS ID is exactly {EOS_LENGTH} characters — it's easy to drop one when copying, "
            f"so please paste it rather than typing it."
        )

    return cleaned


def is_valid_eos_id(raw: str) -> bool:
    """Non-raising form, for filtering and for guarding display code."""
    try:
        normalize_eos_id(raw)
        return True
    except InvalidEosId:
        return False
