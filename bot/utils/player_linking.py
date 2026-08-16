"""
Helper utilities for player linking and verification.
"""

import discord
from bot.database import players_db


async def require_linked_player(
    interaction: discord.Interaction, defer: bool = False
) -> tuple[bool, dict]:
    """
    Check if player is linked and send helpful message if not.

    Args:
        interaction: The Discord interaction
        defer: Whether to defer the response before checking (for long operations)

    Returns:
        tuple[bool, dict]: (is_linked, player_data or None)
    """
    if defer:
        await interaction.response.defer()

    player = await players_db.get_player_by_discord_id(interaction.user.id)

    if player:
        return True, player

    # Player not linked - send helpful instructions
    embed = discord.Embed(
        title="🔗 Link Your Account First",
        description="You need to link your Discord account to your ARK character to use this feature!",
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="📋 Step 1: Find Your EOS ID",
        value=(
            "In ARK: Survival Ascended:\n"
            "• Press **Tab** to open console\n"
            "• Type: `ShowMyAdminManager`\n"
            "• Your **EOS ID** will be displayed\n"
            "• It looks like: `0002abc123def456`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔗 Step 2: Link Your Account",
        value=(
            "Back in Discord:\n"
            "• Use `/linkplayer <your_eos_id>`\n"
            "• Example: `/linkplayer 0002abc123def456`\n"
            "• You'll get a confirmation message!"
        ),
        inline=False,
    )

    embed.add_field(
        name="✨ What Linking Enables",
        value=(
            "• 🎁 Receive items and creatures in-game\n"
            "• 📦 Claim starter kits\n"
            "• 🛒 Purchase from the shop\n"
            "• 💰 Earn and spend Phoenix Coins\n"
            "• 📊 Track your stats and progress"
        ),
        inline=False,
    )

    embed.add_field(
        name="❓ Need Help?",
        value="Ask an admin if you're having trouble finding your EOS ID!",
        inline=False,
    )

    embed.set_footer(text="💡 Your EOS ID is unique to you and stays the same across all servers")

    if defer:
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

    return False, None


def create_link_success_embed(eos_id: str) -> discord.Embed:
    """Create a success embed for account linking."""
    embed = discord.Embed(
        title="✅ Account Linked Successfully!",
        description=f"Your Discord account is now linked to EOS ID: `{eos_id}`",
        color=discord.Color.green(),
    )

    embed.add_field(
        name="🎉 You Can Now",
        value=(
            "• Receive items and creatures in-game\n"
            "• Claim starter kits with `/kit`\n"
            "• Purchase from the shop\n"
            "• View your stats and linked info with `/mylink`"
        ),
        inline=False,
    )

    embed.add_field(
        name="📌 Next Steps",
        value=(
            "1️⃣ Check available kits: `/listkits`\n"
            "2️⃣ View your linked info: `/mylink`\n"
            "3️⃣ Explore the shop commands\n"
            "4️⃣ Join an ARK server and play!"
        ),
        inline=False,
    )

    embed.set_footer(text="🎮 Your account is ready for ARK rewards and features!")

    return embed


def create_eos_id_help_embed() -> discord.Embed:
    """Create a help embed for finding EOS ID."""
    embed = discord.Embed(
        title="🆔 How to Find Your EOS ID",
        description="Follow these steps to locate your Epic Online Services ID in ARK:",
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="Method 1: Admin Manager (Easiest)",
        value=(
            "1. Join any ARK server\n"
            "2. Press **Tab** to open console\n"
            "3. Type: `ShowMyAdminManager`\n"
            "4. Your EOS ID will be displayed at the top\n"
            "5. Copy the long string (starts with numbers)"
        ),
        inline=False,
    )

    embed.add_field(
        name="Method 2: Check Logs",
        value=(
            "Look in your game logs:\n"
            "• Find: `ShooterGame/Saved/Logs`\n"
            "• Open the latest log file\n"
            "• Search for: `EOS ID`\n"
            "• Your ID will be nearby"
        ),
        inline=False,
    )

    embed.add_field(
        name="What Does It Look Like?",
        value=(
            "✅ Correct: `0002abc123def456` (16 characters)\n"
            "✅ Correct: `0002a1b2c3d4e5f6`\n"
            "❌ Wrong: Your Epic Games username\n"
            "❌ Wrong: Your Steam ID"
        ),
        inline=False,
    )

    embed.add_field(
        name="Once You Have It",
        value="Use `/linkplayer <your_eos_id>` to link your account!",
        inline=False,
    )

    embed.set_footer(text="💡 Still stuck? Ask a server admin for help!")

    return embed
