"""/listlinkedplayers must survive a player row with no EOS ID.

2026-08-11: the command hung on "thinking…" forever. It was not slow and it was not RCON — it was
a TypeError, thrown after `interaction.response.defer()` had already been sent:

    eos_id = player.get("eos_id", "N/A")[:20]      ->  None[:20]

`dict.get(key, default)` only falls back when the KEY IS MISSING. `eos_id` is always present in the
SELECT, so a SQL NULL comes back as None and the default never fires. Because the failure landed
after the defer, Discord had already been told "working on it" and nothing ever followed — no error
message, no traceback in front of anyone, just a spinner.

It was not an edge case. `get_linked_players_for_guild()` filters on `discord_user_id IS NOT NULL`
and says nothing about eos_id, and the live guild had dozens of members who joined Discord without
ever linking an ARK account. One of them was enough to take the command down for every admin.

The same slice existed in the pagination view, so turning a page failed the same way.

Uses real discord.py objects, in the style of test_cog_player_management.py.
"""
import asyncio
from types import SimpleNamespace

import pytest

from bot.cogs.player_management import LinkedPlayersPaginationView


def _rows():
    """A page mixing a healthy row with the shapes that actually live in the table."""
    return [
        {
            "discord_username": "evander",
            "eos_id": "0002dfb22b27431bb286926de393dd45",
            "specimen_id": "7141017",
            "character_name": "Grampa7939",
        },
        # the row that killed it: linked to Discord, never linked to ARK
        {
            "discord_username": "Lady Sif",
            "eos_id": None,
            "specimen_id": None,
            "character_name": None,
        },
    ]


class _Response:
    def __init__(self):
        self.embeds = []

    async def edit_message(self, embed=None, view=None):
        self.embeds.append(embed)


def _interaction(user_id=12345):
    resp = _Response()
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, display_name="Admin"),
        response=resp,
        guild_id=999,
    )


def test_a_null_eos_row_does_not_crash_the_page():
    """The regression. Before the fix this raised TypeError: 'NoneType' is not subscriptable."""
    view = LinkedPlayersPaginationView(
        bot=SimpleNamespace(), guild_id=999,
        user=SimpleNamespace(id=12345), players=_rows(),
        current_page=1, total_pages=1,
    )
    interaction = _interaction()
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        view.update_message(interaction)
    )
    assert interaction.response.embeds, "no embed was produced at all"


def test_the_unlinked_player_is_shown_rather_than_dropped():
    """Silently hiding them would trade a crash for a lie: an admin looking for a member who
    'is linked' needs to see that they are NOT."""
    view = LinkedPlayersPaginationView(
        bot=SimpleNamespace(), guild_id=999,
        user=SimpleNamespace(id=12345), players=_rows(),
        current_page=1, total_pages=1,
    )
    interaction = _interaction()
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        view.update_message(interaction)
    )
    embed = interaction.response.embeds[-1]
    rendered = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    assert "Lady Sif" in rendered, "the unlinked member vanished from the list"
    assert "Not linked" in rendered, "nothing tells the admin why that row is blank"
    assert "Grampa7939" in rendered, "the healthy row stopped rendering"
