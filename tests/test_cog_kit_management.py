"""
Tests for bot/cogs/kit_management.py

Covers:
- Modal field label length validation (Discord 45-char limit)
- View button configurations
- Kit management workflows
"""

import pytest
import discord
import inspect


class TestModalFieldLengths:
    """Test that all modal field labels are within Discord's 45-character limit."""

    def test_add_item_modal_labels(self):
        """AddItemModal labels must be <= 45 characters."""
        from bot.cogs.kit_management import AddItemModal
        
        # Check class-level TextInput definitions
        for name, value in inspect.getmembers(AddItemModal):
            if isinstance(value, discord.ui.TextInput):
                label_length = len(value.label)
                assert label_length <= 45, (
                    f"Field '{name}' label '{value.label}' is {label_length} chars, "
                    f"exceeds Discord's 45-char limit"
                )

    def test_create_kit_modal_labels(self):
        """CreateKitModal labels must be <= 45 characters."""
        from bot.cogs.kit_management import CreateKitModal
        
        for name, value in inspect.getmembers(CreateKitModal):
            if isinstance(value, discord.ui.TextInput):
                label_length = len(value.label)
                assert label_length <= 45, (
                    f"Field '{name}' label '{value.label}' is {label_length} chars, "
                    f"exceeds Discord's 45-char limit"
                )

    def test_edit_kit_modal_labels(self):
        """EditKitModal labels must be <= 45 characters."""
        from bot.cogs.kit_management import EditKitModal
        
        for name, value in inspect.getmembers(EditKitModal):
            if isinstance(value, discord.ui.TextInput):
                label_length = len(value.label)
                assert label_length <= 45, (
                    f"Field '{name}' label '{value.label}' is {label_length} chars, "
                    f"exceeds Discord's 45-char limit"
                )

    def test_edit_item_modal_labels(self):
        """EditItemModal labels must be <= 45 characters."""
        from bot.cogs.kit_management import EditItemModal
        
        for name, value in inspect.getmembers(EditItemModal):
            if isinstance(value, discord.ui.TextInput):
                label_length = len(value.label)
                assert label_length <= 45, (
                    f"Field '{name}' label '{value.label}' is {label_length} chars, "
                    f"exceeds Discord's 45-char limit"
                )


class TestModalPlaceholders:
    """Test that modal placeholders provide helpful quality examples."""

    def test_add_item_quality_placeholder(self):
        """AddItemModal quality field should have helpful placeholder."""
        from bot.cogs.kit_management import AddItemModal
        
        # Check class-level quality field
        assert hasattr(AddItemModal, 'quality'), "AddItemModal should have quality field"
        quality_field = AddItemModal.quality
        assert isinstance(quality_field, discord.ui.TextInput), "quality should be TextInput"
        assert quality_field.placeholder, "Quality field should have a placeholder"
