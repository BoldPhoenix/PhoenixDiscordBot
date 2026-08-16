"""`dict.get(key, default)` does NOT protect against a SQL NULL, and the codebase must not pretend it does.

2026-08-11: /listlinkedplayers hung on "thinking…" forever. The cause was one expression:

    eos_id = player.get("eos_id", "N/A")[:20]      ->  None[:20]  ->  TypeError

`get(key, default)` falls back only when the KEY IS ABSENT. Rows from a SELECT always contain
every selected key, so a SQL NULL arrives as Python None and the default never fires. The slice
then raises — and because it raised after `interaction.response.defer()`, Discord had already been
told a reply was coming, so it presented as a permanent spinner rather than an error.

2026-08-12, sweeping for siblings: fourteen more instances of the same idiom, none of them firing
YET. That is the point of this file. These bugs are DATA-triggered, not code-triggered: the code
has been wrong the whole time, and what changed for `players` was a migration on 2026-03-01 that
inserted 38 rows with a NULL where the code assumed a string. "It has never happened" is not
evidence the code is correct — it is evidence that the row has not arrived yet.

So this is a guard, not a unit test. It reads the source and fails if the idiom comes back, because
these sites are buried in Discord UI callbacks that only misbehave against particular data.

The correct idiom is `or`, which handles the missing key AND the NULL:

    (player.get("eos_id") or "Not linked")[:20]
"""
import re
from pathlib import Path

import pytest

BOT = Path(__file__).resolve().parents[1] / "bot"

# .get(key, default) whose result is immediately subscripted — the /listlinkedplayers shape.
SUBSCRIPTED = re.compile(r"\.get\(\s*[^()]*?,\s*[^()]*?\)\s*\[")
# len() of a .get(key, default) — same trap, len(None) instead of None[...]
LEN_OF_GET = re.compile(r"len\(\s*[\w.\[\]'\"]+\.get\(\s*[^()]*?,\s*[^()]*?\)\s*\)")


def _offenders():
    hits = []
    for path in sorted(BOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if SUBSCRIPTED.search(line) or LEN_OF_GET.search(line):
                rel = path.relative_to(BOT.parent).as_posix()
                hits.append(f"{rel}:{lineno}: {stripped[:110]}")
    return hits


def test_no_get_with_default_is_subscripted_or_measured():
    """The regression guard for the whole class.

    If this fails, the listed line assumes `.get(key, default)` shields it from None. It does not:
    a SQL NULL, or a JSON null, comes back as None and the default never fires. Use `or`:

        (row.get("col") or "fallback")[:20]
    """
    hits = _offenders()
    assert not hits, (
        "`.get(key, default)` result subscripted or passed to len() — this raises TypeError the "
        "first time the value is NULL, and (behind a deferred interaction) shows as a permanent "
        '"thinking…" spinner rather than an error:\n  ' + "\n  ".join(hits)
    )


# --------------------------------------------------------------------------- why, in one place

def test_get_default_does_not_fire_for_a_none_value():
    """The premise, pinned. Everything above depends on this being true of Python dicts."""
    row = {"eos_id": None}                      # what dict(sqlite3.Row) gives for a NULL column
    assert row.get("eos_id", "N/A") is None, "the default fired — premise of this file is wrong"
    with pytest.raises(TypeError):
        row.get("eos_id", "N/A")[:20]


def test_the_or_idiom_handles_both_null_and_missing():
    present_null = {"eos_id": None}
    absent = {}
    assert (present_null.get("eos_id") or "Not linked")[:20] == "Not linked"
    assert (absent.get("eos_id") or "Not linked")[:20] == "Not linked"
    assert ({"eos_id": "abc"}.get("eos_id") or "Not linked")[:20] == "abc"


def test_the_or_idiom_also_survives_an_empty_list():
    """Why `or` is the right tool for len() too: it absorbs [] as well as None, so an empty
    collection cannot become an IndexError downstream."""
    assert len({"items": None}.get("items") or []) == 0
    assert (({"candidates": []}.get("candidates") or [{}])[0]) == {}
