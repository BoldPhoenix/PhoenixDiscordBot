"""A delivered item has to show up in the shop log channel, not just in a DM and journald.

Carl, 2026-08-12: "give me some logging in the same shop log channel telling me the stuff showed up
on their doorstep."

The gap: a purchase that could not be delivered immediately logged "🕐 queued for delivery" and then
nothing, ever. Both delivery paths DM'd the player and wrote to journald, but neither posted to the
log channel — so from the admin's side a queued purchase and a permanently stuck one looked
identical. Deez_Knutz721's five items sat that way for two days.

These tests drive _log_delivery directly with a fake channel and assert what actually reaches
Discord: the count, the readable item names, the server, and — the part that matters — that the
embed does NOT claim more certainty than ARK gives us.
"""
import asyncio
from types import SimpleNamespace

import pytest

from bot.cogs import shop as shop_module


class _Channel:
    def __init__(self):
        self.sent = []

    async def send(self, embed=None):
        self.sent.append(embed)


@pytest.fixture
def make_cog(monkeypatch):
    """A ShopCog with just enough wired to run _log_delivery.

    monkeypatch, not direct assignment: these patch module-level shop_db functions, and setting
    them permanently would leak into every other test that imports shop_db in the same run.
    """
    def _build(channel, item_names=None):
        cog = shop_module.ShopCog.__new__(shop_module.ShopCog)
        cog.bot = SimpleNamespace(get_channel=lambda _id: channel)

        async def _cfg(_guild_id):
            return {"log_channel_id": 123}

        async def _name(_guild_id, cmd):
            return (item_names or {}).get(cmd)

        monkeypatch.setattr(shop_module.shop_db, "get_shop_config", _cfg)
        monkeypatch.setattr(shop_module.shop_db, "get_item_name_by_command", _name)
        return cog

    return _build


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


BOSS_BP = ("Blueprint'/CybersStructures/Crafting/TributeTerminal/Recipes/Boss/"
           "PrimalItemCraftable_OverseerAlphaPack_CS.PrimalItemCraftable_OverseerAlphaPack_CS'")


def _deliveries(n=1):
    return [
        {"id": 70 + i, "item_blueprint": BOSS_BP, "quantity": 1, "quality": 1}
        for i in range(n)
    ]


def test_a_delivery_posts_to_the_shop_log_channel(make_cog):
    """The regression: this channel previously saw the purchase and never the delivery."""
    ch = _Channel()
    cog = make_cog(ch, {BOSS_BP: "Overseer Alpha Pack"})
    member = SimpleNamespace(mention="<@555555555555555556>")
    _run(cog._log_delivery(1, member, "Extinction", _deliveries(1), "Deez_Knutz"))
    assert ch.sent, "nothing reached the shop log channel"


def test_it_names_the_player_the_server_and_the_item(make_cog):
    ch = _Channel()
    cog = make_cog(ch, {BOSS_BP: "Overseer Alpha Pack"})
    member = SimpleNamespace(mention="<@555555555555555556>")
    _run(cog._log_delivery(1, member, "Extinction", _deliveries(1), "Deez_Knutz"))
    text = ch.sent[-1].description
    assert "<@555555555555555556>" in text
    assert "Deez_Knutz" in text
    assert "Extinction" in text
    assert "Overseer Alpha Pack" in text, "logged the raw blueprint instead of the item name"


def test_five_items_are_one_embed_not_five(make_cog):
    """Five items arriving at once is a single event to someone reading the channel."""
    ch = _Channel()
    cog = make_cog(ch, {BOSS_BP: "Overseer Alpha Pack"})
    member = SimpleNamespace(mention="<@1>")
    _run(cog._log_delivery(1, member, "Extinction", _deliveries(5), "Deez_Knutz"))
    assert len(ch.sent) == 1, f"expected one batched embed, got {len(ch.sent)}"
    assert "**5**" in ch.sent[-1].description


def test_an_unknown_blueprint_still_gets_logged_readably(make_cog):
    """An item renamed or pulled from the shop after purchase must not silence the log."""
    ch = _Channel()
    cog = make_cog(ch, item_names={})           # lookup finds nothing
    member = SimpleNamespace(mention="<@1>")
    _run(cog._log_delivery(1, member, "Extinction", _deliveries(1), None))
    text = ch.sent[-1].description
    assert "PrimalItemCraftable_OverseerAlphaPack_CS" in text
    assert "Blueprint'/CybersStructures" not in text, "dumped the whole blueprint path"


def test_the_embed_does_not_overclaim_receipt(make_cog):
    """The honesty guard, and the reason this test file exists at all.

    ARK answers GiveItemToPlayer with 'Server received, But no response!!' whether the item landed
    or not — delivery_loop's own comment says it "silently drops items for offline players but
    returns success". What we can prove is that the player was in the live RCON scan when the
    command was accepted. The footer must say that, so this embed is never mistaken for proof the
    item is in someone's inventory."""
    ch = _Channel()
    cog = make_cog(ch, {BOSS_BP: "Overseer Alpha Pack"})
    _run(cog._log_delivery(1, SimpleNamespace(mention="<@1>"), "Extinction", _deliveries(1), None))
    footer = ch.sent[-1].footer.text.lower()
    assert "confirmed online" in footer, "no evidence of the doorstep check"
    assert "does not acknowledge" in footer, "reads as proof of receipt, which ARK cannot give"


def test_nothing_delivered_means_nothing_logged(make_cog):
    """An empty sweep must not post 'delivered 0 items' every five minutes."""
    ch = _Channel()
    cog = make_cog(ch)
    _run(cog._log_delivery(1, SimpleNamespace(mention="<@1>"), "Extinction", [], None))
    assert not ch.sent


def test_a_logging_failure_never_breaks_a_completed_delivery(make_cog):
    """The item is already in the player's hands by this point; a broken channel must not raise."""
    class _Boom:
        async def send(self, embed=None):
            raise RuntimeError("channel is gone")

    cog = make_cog(_Boom())
    _run(cog._log_delivery(1, SimpleNamespace(mention="<@1>"), "Extinction", _deliveries(1), None))
