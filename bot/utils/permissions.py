"""
Permission checking utilities for bot commands.
"""

import discord
from bot.database import server_config_db


async def is_admin(interaction: discord.Interaction) -> bool:
    """
    Check if user is an admin (has Administrator permission or admin role).

    Args:
        interaction: The Discord interaction

    Returns:
        bool: True if user is admin, False otherwise
    """
    if interaction.user.guild_permissions.administrator:
        return True

    config = await server_config_db.get_server_config(interaction.guild_id)
    if config and config.get("admin_role_id"):
        admin_role = interaction.guild.get_role(config["admin_role_id"])
        if admin_role and admin_role in interaction.user.roles:
            return True

    return False


async def is_verified_user(interaction: discord.Interaction) -> bool:
    """
    Check if user is verified (has user role or admin role).

    Admins always pass this check.
    If no user role is configured, all users pass.

    Args:
        interaction: The Discord interaction

    Returns:
        bool: True if user is verified, False otherwise
    """
    # Admins bypass user role check
    if await is_admin(interaction):
        return True

    config = await server_config_db.get_server_config(interaction.guild_id)

    # If no user role configured, everyone is verified
    if not config or not config.get("user_role_id"):
        return True

    # Check if user has the user role
    user_role = interaction.guild.get_role(config["user_role_id"])
    if user_role and user_role in interaction.user.roles:
        return True

    return False


async def require_admin(interaction: discord.Interaction) -> bool:
    """
    Check admin permission and send error message if unauthorized.

    Args:
        interaction: The Discord interaction

    Returns:
        bool: True if authorized, False if not (message already sent)
    """
    if await is_admin(interaction):
        return True

    await interaction.response.send_message(
        "❌ You need Administrator permission or the admin role to use this command.",
        ephemeral=True,
    )
    return False


async def require_verified_user(interaction: discord.Interaction) -> bool:
    """
    Check verified user permission and send error message if unauthorized.

    Args:
        interaction: The Discord interaction

    Returns:
        bool: True if authorized, False if not (message already sent)
    """
    if await is_verified_user(interaction):
        return True

    config = await server_config_db.get_server_config(interaction.guild_id)
    role_mention = (
        f"<@&{config['user_role_id']}>"
        if config and config.get("user_role_id")
        else "the verified user role"
    )

    embed = discord.Embed(
        title="🔒 Verification Required",
        description=f"You need {role_mention} to use this feature.",
        color=discord.Color.orange(),
    )

    embed.add_field(
        name="📝 How to Get Verified",
        value=(
            "To access bot features, you need to:\n"
            "1️⃣ Contact a server administrator or moderator\n"
            "2️⃣ Request the verified user role\n"
            "3️⃣ Once you have the role, you can use all bot features!"
        ),
        inline=False,
    )

    embed.add_field(
        name="✨ What You'll Unlock",
        value=(
            "• 🎮 Link your Discord to your ARK character\n"
            "• 📦 Claim starter kits and rewards\n"
            "• 🛒 Shop for items and creatures\n"
            "• 📊 View your stats and progress"
        ),
        inline=False,
    )

    embed.set_footer(text="This helps us keep the community safe and prevent abuse")

    await interaction.response.send_message(embed=embed, ephemeral=True)
    return False
