import unittest

import discord
from discord.ext import commands

from bot.cogs.help_commands import HelpCommands


class HelpCommandsEmbedTest(unittest.TestCase):
    def test_all_commands_embed_field_lengths(self):
        # Create a minimal bot; no connection to Discord needed for embed generation
        intents = discord.Intents.none()
        bot = commands.Bot(command_prefix="!", intents=intents)

        cog = HelpCommands(bot)
        embed = cog.create_all_commands_embed()

        # Discord embed limits: each field value <= 1024, max 25 fields
        self.assertLessEqual(len(embed.fields), 25)
        for field in embed.fields:
            self.assertLessEqual(len(field.value), 1024)


if __name__ == "__main__":
    unittest.main()
