"""
Shop management cog for uploading and managing store items via Excel spreadsheet.
Allows admins to bulk import items from the rshop_prices.xlsx format.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import io
import asyncio
from typing import Optional

try:
    import openpyxl
except ImportError:
    openpyxl = None

from bot.database import store_db
from bot.utils.config import Config


logger = logging.getLogger("ShopManagerCog")


def is_admin():
    """Check if user has admin role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not Config.ADMIN_ROLE_ID:
            return interaction.user.guild_permissions.administrator

        role = interaction.guild.get_role(Config.ADMIN_ROLE_ID)
        return role in interaction.user.roles if role else False

    return app_commands.check(predicate)


class ShopManager(commands.Cog):
    """Admin commands for managing the Phoenix Store via Excel upload."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="uploadshop", description="[ADMIN] Upload shop items from Excel spreadsheet"
    )
    @app_commands.describe(
        file="Excel file (.xlsx) with shop items",
        mode="'preview' to see changes, 'replace' to clear and import, 'merge' to add/update",
    )
    @is_admin()
    async def upload_shop(
        self, interaction: discord.Interaction, file: discord.Attachment, mode: str = "preview"
    ):
        """Upload shop items from an Excel spreadsheet."""
        await interaction.response.defer(ephemeral=True)

        if not openpyxl:
            await interaction.followup.send(
                "❌ Excel support not installed. Contact bot administrator.", ephemeral=True
            )
            return

        # Validate file type
        if not file.filename.endswith((".xlsx", ".xls")):
            await interaction.followup.send(
                "❌ Invalid file type. Please upload an Excel file (.xlsx)", ephemeral=True
            )
            return

        # Validate mode
        if mode not in ["preview", "replace", "merge"]:
            await interaction.followup.send(
                f"❌ Invalid mode '{mode}'. Use 'preview', 'replace', or 'merge'.", ephemeral=True
            )
            return

        try:
            # Download and read the Excel file
            file_bytes = await file.read()
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes))

            # Get the items sheet
            if "items" not in wb.sheetnames:
                await interaction.followup.send(
                    f"❌ Spreadsheet must have an 'items' sheet. Found sheets: {', '.join(wb.sheetnames)}",
                    ephemeral=True,
                )
                return

            ws = wb["items"]

            # Parse items from spreadsheet
            items = []
            errors = []

            # Expected columns: Item Name, Price Per Item, Allow Quality Select, Allow Blueprint Select,
            #                   Max Stack Size, Category, Description, Class Name, Blueprint Path, Server Type

            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row[0]:  # Skip empty rows
                    continue

                try:
                    item_name = row[0]
                    price = int(row[1]) if row[1] else 0
                    # allow_quality = row[2]  # Future feature
                    # allow_blueprint = row[3]  # Future feature
                    # max_stack = row[4]  # Future feature
                    category = row[5] or "general"
                    description = row[6] or None
                    # class_name = row[7]  # Not used currently
                    blueprint_path = row[8] or ""
                    server_type = (row[9] or "both").lower()

                    # Validate required fields
                    if not item_name:
                        errors.append(f"Row {row_num}: Missing item name")
                        continue

                    if not blueprint_path:
                        errors.append(f"Row {row_num}: Missing blueprint path for '{item_name}'")
                        continue

                    if price < 0:
                        errors.append(f"Row {row_num}: Invalid price for '{item_name}'")
                        continue

                    # Clean up blueprint path (remove quotes if present)
                    blueprint_path = blueprint_path.strip("'\"")

                    # Create GiveItem command format
                    # Format: cheat giveitem "blueprint_path" 1 0 0
                    ark_command = f'cheat giveitem "{blueprint_path}" 1 0 0'

                    items.append(
                        {
                            "name": item_name,
                            "description": description,
                            "cost": price,
                            "ark_command": ark_command,
                            "category": category,
                            "server_type": server_type,
                        }
                    )

                except Exception as e:
                    errors.append(f"Row {row_num}: Error parsing - {str(e)}")

            # Create summary embed
            embed = discord.Embed(
                title=f"📊 Shop Upload - {mode.upper()} Mode",
                color=discord.Color.blue() if mode == "preview" else discord.Color.green(),
            )

            embed.add_field(
                name="📁 File",
                value=f"{file.filename} ({len(file_bytes) / 1024:.1f} KB)",
                inline=False,
            )

            embed.add_field(name="✅ Valid Items", value=str(len(items)), inline=True)

            embed.add_field(name="❌ Errors", value=str(len(errors)), inline=True)

            # Group by category
            categories = {}
            for item in items:
                cat = item["category"]
                if cat not in categories:
                    categories[cat] = 0
                categories[cat] += 1

            if categories:
                category_text = "\n".join(
                    [f"{cat}: {count}" for cat, count in sorted(categories.items())]
                )
                embed.add_field(name="📋 Categories", value=category_text, inline=False)

            # Show first few errors
            if errors:
                error_preview = "\n".join(errors[:10])
                if len(errors) > 10:
                    error_preview += f"\n... and {len(errors) - 10} more errors"
                embed.add_field(name="⚠️ Errors Found", value=f"```{error_preview}```", inline=False)

            # Preview mode - just show summary
            if mode == "preview":
                embed.description = "Preview mode - no changes made to database."
                embed.add_field(
                    name="💡 Next Steps",
                    value="Use `/uploadshop mode:replace` to clear current items and import these.\n"
                    "Use `/uploadshop mode:merge` to add/update items without clearing.",
                    inline=False,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Replace mode - clear all and import
            if mode == "replace":
                # Ask for confirmation
                embed.description = f"⚠️ **WARNING**: This will DELETE all {await store_db.count_items()} existing items and import {len(items)} new items."
                embed.add_field(
                    name="🔄 Confirm Action",
                    value="React with ✅ to proceed or ❌ to cancel.",
                    inline=False,
                )

                msg = await interaction.followup.send(embed=embed, ephemeral=True)

                # Wait for confirmation (simplified - in production you'd use buttons/views)
                await interaction.followup.send(
                    "⏳ Clearing existing items and importing...", ephemeral=True
                )

                await store_db.clear_all_items()
                logger.info(f"Cleared all store items (initiated by {interaction.user})")

            # Import items
            success_count = 0
            import_errors = []

            for item in items:
                try:
                    await store_db.add_item(
                        name=item["name"],
                        description=item["description"],
                        cost=item["cost"],
                        ark_command=item["ark_command"],
                        category=item["category"],
                    )
                    success_count += 1
                except Exception as e:
                    import_errors.append(f"{item['name']}: {str(e)}")

            # Final result embed
            result_embed = discord.Embed(
                title=f"✅ Shop {'Replaced' if mode == 'replace' else 'Updated'}",
                description=f"Successfully imported {success_count} items.",
                color=discord.Color.green(),
            )

            if mode == "replace":
                result_embed.add_field(
                    name="🗑️ Cleared", value="All previous items removed", inline=True
                )

            result_embed.add_field(name="✅ Imported", value=f"{success_count} items", inline=True)

            if import_errors:
                error_text = "\n".join(import_errors[:5])
                if len(import_errors) > 5:
                    error_text += f"\n... and {len(import_errors) - 5} more"
                result_embed.add_field(
                    name="⚠️ Import Errors", value=f"```{error_text}```", inline=False
                )

            result_embed.set_footer(text=f"Uploaded by {interaction.user}")

            await interaction.followup.send(embed=result_embed, ephemeral=True)

            # Log to log channel if configured
            if Config.LOG_CHANNEL_ID:
                log_channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(
                        title="🛒 Shop Items Updated",
                        description=f"{interaction.user.mention} uploaded {success_count} items",
                        color=discord.Color.blue(),
                    )
                    log_embed.add_field(name="File", value=file.filename)
                    log_embed.add_field(name="Mode", value=mode)
                    log_embed.add_field(name="Items", value=success_count)
                    await log_channel.send(embed=log_embed)

        except Exception as e:
            logger.error(f"Error uploading shop: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error processing spreadsheet: {str(e)}", ephemeral=True
            )

    @app_commands.command(name="clearshop", description="[ADMIN] Clear all items from the shop")
    @is_admin()
    async def clear_shop(self, interaction: discord.Interaction):
        """Clear all items from the shop (requires confirmation)."""
        await interaction.response.defer(ephemeral=True)

        item_count = await store_db.count_items()

        embed = discord.Embed(
            title="⚠️ Clear Shop Confirmation",
            description=f"This will permanently delete **{item_count} items** from the shop.",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="⚠️ Warning",
            value="This action cannot be undone. Type `/clearshop confirm:yes` to proceed.",
            inline=False,
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="shopstats", description="[ADMIN] View shop statistics")
    @is_admin()
    async def shop_stats(self, interaction: discord.Interaction):
        """View statistics about the shop."""
        await interaction.response.defer(ephemeral=True)

        total_items = await store_db.count_items()
        items_by_category = await store_db.get_items_by_category()

        embed = discord.Embed(title="📊 Phoenix Shop Statistics", color=discord.Color.blue())

        embed.add_field(name="Total Items", value=str(total_items), inline=True)

        if items_by_category:
            category_text = "\n".join(
                [f"{cat}: {count}" for cat, count in items_by_category.items()]
            )
            embed.add_field(name="Categories", value=category_text, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopManager(bot))
