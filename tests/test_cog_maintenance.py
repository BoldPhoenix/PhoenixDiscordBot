"""
Tests for maintenance_gui.py cog
"""

import pytest
import discord
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, call, MagicMock


class TestMaintenanceDB:
    """Test cases for maintenance_db functions."""

    @pytest.mark.asyncio
    async def test_init_maintenance_tables(self, tmp_db_path):
        """Test table creation."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            import aiosqlite
            async with aiosqlite.connect(tmp_db_path) as db:
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('maintenance_config', 'maintenance_jobs', 'backup_history')"
                )
                tables = await cursor.fetchall()
                table_names = [t[0] for t in tables]

                assert "maintenance_config" in table_names
                assert "maintenance_jobs" in table_names
                assert "backup_history" in table_names

    @pytest.mark.asyncio
    async def test_get_maintenance_config_empty(self, tmp_db_path):
        """Test getting config when none exists."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            result = await maintenance_db.get_maintenance_config(999)
            assert result is None

    @pytest.mark.asyncio
    async def test_update_maintenance_config(self, tmp_db_path):
        """Test updating config."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            await maintenance_db.update_maintenance_config(
                123,
                backup_enabled=1,
                backup_schedule_type="daily",
                backup_time="02:00"
            )

            result = await maintenance_db.get_maintenance_config(123)
            assert result is not None
            assert result["backup_enabled"] == 1
            assert result["backup_schedule_type"] == "daily"
            assert result["backup_time"] == "02:00"

    @pytest.mark.asyncio
    async def test_update_maintenance_config_on_conflict(self, tmp_db_path):
        """Test updating config when row already exists (ON CONFLICT)."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            # First insert
            await maintenance_db.update_maintenance_config(
                123,
                backup_enabled=1,
                backup_time="02:00"
            )

            # Update existing row (triggers ON CONFLICT)
            await maintenance_db.update_maintenance_config(
                123,
                backup_enabled=0,
                backup_time="04:00"
            )

            result = await maintenance_db.get_maintenance_config(123)
            assert result is not None
            assert result["backup_enabled"] == 0
            assert result["backup_time"] == "04:00"

    @pytest.mark.asyncio
    async def test_backup_history(self, tmp_db_path):
        """Test backup history functions."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            await maintenance_db.add_backup_history(
                guild_id=123,
                server_name="TestServer",
                backup_path="D:\\Backups\\test.zip",
                backup_size_bytes=1000000,
                status="success"
            )

            history = await maintenance_db.get_backup_history(123)
            assert len(history) == 1
            assert history[0]["server_name"] == "TestServer"
            assert history[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_maintenance_jobs(self, tmp_db_path):
        """Test maintenance job functions."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            job_id = await maintenance_db.create_maintenance_job(
                guild_id=123,
                server_name="TestServer",
                job_type="backup"
            )
            assert job_id > 0

            await maintenance_db.update_maintenance_job(
                job_id=job_id,
                status="completed",
                backup_path="D:\\Backups\\test.zip"
            )

            jobs = await maintenance_db.get_maintenance_jobs(123)
            assert len(jobs) == 1
            assert jobs[0]["job_type"] == "backup"
            assert jobs[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_backup_history_filter_by_server(self, tmp_db_path):
        """Test backup history filtered by server."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            await maintenance_db.add_backup_history(123, "Server1", "path1.zip")
            await maintenance_db.add_backup_history(123, "Server2", "path2.zip")

            history1 = await maintenance_db.get_backup_history(123, "Server1")
            assert len(history1) == 1
            assert history1[0]["server_name"] == "Server1"

            history2 = await maintenance_db.get_backup_history(123, "Server2")
            assert len(history2) == 1
            assert history2[0]["server_name"] == "Server2"

    @pytest.mark.asyncio
    async def test_get_servers_for_backup(self, tmp_db_path):
        """Test getting servers that should be backed up."""
        with patch('bot.database.maintenance_db._db_path', return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            # Add backup history
            await maintenance_db.add_backup_history(
                guild_id=123,
                server_name="Server1",
                backup_path="D:\\Backups\\Server1.zip",
                backup_size_bytes=1000000,
                status="success"
            )

            # Get history
            history = await maintenance_db.get_backup_history(123)
            assert len(history) == 1
            assert history[0]["backup_size_bytes"] == 1000000


# ---------------------------------------------------------------------------
# Bug-fix regression tests (all should FAIL before the fix, PASS after)
# ---------------------------------------------------------------------------

class TestMaintenanceSettingsModalInit:
    """Regression tests for MaintenanceSettingsModal.__init__ crashes."""

    @pytest.mark.asyncio
    async def test_none_backup_root_does_not_crash(self):
        """backup_root_path=None from DB must not raise; field should be ''."""
        from bot.cogs.maintenance_gui import MaintenanceSettingsModal
        settings = {
            "guild_id": 123,
            "backup_enabled": 1,
            "backup_type": "essentials",
            "backup_schedule_type": "daily",
            "backup_time": "02:00",
            "backup_retention_days": 30,
            "backup_root_path": None,   # key exists, value is None
        }
        modal = MaintenanceSettingsModal(settings)
        assert modal.guild_id == 123
        # Must be empty string, not None, so Discord doesn't reject it
        assert modal.backup_root.default == ""

    @pytest.mark.asyncio
    async def test_missing_backup_root_defaults_to_empty(self):
        """Missing backup_root_path key should produce empty default."""
        from bot.cogs.maintenance_gui import MaintenanceSettingsModal
        settings = {"guild_id": 456}
        modal = MaintenanceSettingsModal(settings)
        assert modal.backup_root.default == ""

    @pytest.mark.asyncio
    async def test_backup_root_preserved_when_set(self):
        """Non-empty backup_root_path should be kept as-is."""
        from bot.cogs.maintenance_gui import MaintenanceSettingsModal
        settings = {
            "guild_id": 789,
            "backup_root_path": "D:\\ARK\\Backups",
        }
        modal = MaintenanceSettingsModal(settings)
        assert modal.backup_root.default == "D:\\ARK\\Backups"

    @pytest.mark.asyncio
    async def test_backup_type_defaults_to_essentials(self):
        """backup_type should default to 'essentials' when missing."""
        from bot.cogs.maintenance_gui import MaintenanceSettingsModal
        settings = {"guild_id": 123}
        modal = MaintenanceSettingsModal(settings)
        assert modal.backup_type.default == "essentials"


class TestUpdateSettingsButtonRefetch:
    """update_settings button must re-fetch from DB so the modal shows current values."""

    @pytest.mark.asyncio
    async def test_update_settings_refetches_from_db(self):
        """Stale in-memory settings must not pre-populate the modal — DB is the source of truth."""
        from bot.cogs.maintenance_gui import MaintenanceMainView, UpdateSettingsModal

        stale_settings = {
            "guild_id": 123,
            "update_enabled": 0,
            "update_schedule_type": "weekly",
            "update_time": "03:00",
            "enable_pre_update_backup": 1,
            "enable_saveworld": 1,
        }
        fresh_settings = {
            **stale_settings,
            "update_enabled": 1,
            "update_time": "04:30",  # user changed this and saved
        }

        cog = Mock()
        cog.is_admin = AsyncMock(return_value=True)
        view = MaintenanceMainView(cog, 123, stale_settings)

        interaction = AsyncMock()
        update_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Update Settings" in (c.label or "")
        )

        with patch("bot.database.maintenance_db.get_maintenance_config",
                   new_callable=AsyncMock, return_value=fresh_settings) as mock_fetch:
            await update_btn.callback(interaction)

        mock_fetch.assert_called_once_with(123)
        interaction.response.send_modal.assert_called_once()
        modal_arg = interaction.response.send_modal.call_args.args[0]
        assert isinstance(modal_arg, UpdateSettingsModal)
        # Modal must show the freshly-fetched time, not the stale one
        assert modal_arg.update_time.default == "04:30"


class TestImmediateBackupModalMessageOrder:
    """Regression: 'Backup Complete' appeared BEFORE 'Starting backup'."""

    def _make_cog(self, guild_id=123):
        cog = Mock()
        cog.bot.agent_manager = Mock()
        # Simulate the manager's helper (used by fixed code)
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(return_value={
            "data": {
                "backup_file": "D:\\Backups\\TestServer_backup_20260227_essentials.zip",
                "size_mb": "50.0",
                "backup_type": "essentials",
                "file_count": 42,
            }
        })
        return cog

    @pytest.mark.asyncio
    async def test_starting_message_shown_before_complete(self):
        """edit_original_response with 'Starting' must come before the embed call."""
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        cog = self._make_cog()
        modal = ImmediateBackupModal(cog, 123, "TestServer")

        call_order = []

        interaction = AsyncMock()

        async def track_edit(content=None, embed=None, view=None):
            if content and "Starting" in content:
                call_order.append("starting")
            elif embed is not None:
                call_order.append("complete")

        interaction.edit_original_response = AsyncMock(side_effect=track_edit)
        interaction.followup = AsyncMock()

        with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
            await modal._run_backup_task(interaction, "agent1", "essentials", {})

        assert "starting" in call_order, "Must show 'Starting backup' message"
        assert "complete" in call_order, "Must show 'Backup Complete' embed"
        assert call_order.index("starting") < call_order.index("complete"), (
            "Starting message must appear BEFORE Backup Complete"
        )

    @pytest.mark.asyncio
    async def test_no_separate_followup_send_for_starting(self):
        """followup.send must NOT be used for the 'Starting' message (causes ordering bug)."""
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        cog = self._make_cog()
        modal = ImmediateBackupModal(cog, 123, "TestServer")
        modal.backup_type = Mock(value="essentials")
        modal.target_path = Mock(value="")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        interaction.followup = AsyncMock()

        with patch("bot.database.maintenance_db.get_maintenance_config", new_callable=AsyncMock, return_value={}):
            with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
                await modal.on_submit(interaction)

        # followup.send must NOT be called with a "Starting" message
        for c in interaction.followup.send.call_args_list:
            args = c.args[0] if c.args else (c.kwargs.get("content") or "")
            assert "Starting" not in args, (
                "Do not use followup.send for 'Starting' — it creates a second message after the deferred slot"
            )

    @pytest.mark.asyncio
    async def test_backup_params_use_target_path_when_provided(self):
        """When user provides target_path, it must be sent as backup_path to the agent."""
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        cog = self._make_cog()
        modal = ImmediateBackupModal(cog, 123, "TestServer")

        interaction = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        params_with_path = {"essentials_only": True, "backup_path": "D:\\Custom\\Backups"}
        with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
            await modal._run_backup_task(interaction, "agent1", "essentials", params_with_path)

        send_call = cog.bot.agent_manager.send_command.call_args
        sent_params = send_call.kwargs.get("params") or (send_call.args[3] if len(send_call.args) > 3 else {})
        assert sent_params.get("backup_path") == "D:\\Custom\\Backups"

    @pytest.mark.asyncio
    async def test_backup_params_no_path_when_target_empty(self):
        """When user leaves target_path empty, backup_path must not be sent to agent."""
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        cog = self._make_cog()
        modal = ImmediateBackupModal(cog, 123, "TestServer")

        interaction = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        params_no_path = {"essentials_only": True}
        with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
            await modal._run_backup_task(interaction, "agent1", "essentials", params_no_path)

        send_call = cog.bot.agent_manager.send_command.call_args
        sent_params = send_call.kwargs.get("params") or (send_call.args[3] if len(send_call.args) > 3 else {})
        assert "backup_path" not in sent_params, "backup_path must not be sent when target_path is empty"

    @pytest.mark.asyncio
    async def test_file_count_shown_in_complete_embed(self):
        """file_count from agent response must appear in the completion embed."""
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        cog = self._make_cog()
        modal = ImmediateBackupModal(cog, 123, "TestServer")

        captured_embed = []

        async def capture_edit(content=None, embed=None, view=None):
            if embed is not None:
                captured_embed.append(embed)

        interaction = AsyncMock()
        interaction.edit_original_response = AsyncMock(side_effect=capture_edit)

        with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
            await modal._run_backup_task(interaction, "agent1", "essentials", {})

        assert len(captured_embed) == 1, "Should produce exactly one completion embed"
        embed = captured_embed[0]
        # At least one field should contain the file count (42)
        field_values = [f.value for f in embed.fields]
        assert any("42" in str(v) for v in field_values), (
            "Embed must show file_count=42 from agent response"
        )


class TestRestoreModalAgentLookup:
    """Regression: RestoreModal must use get_connected_agent_for_guild helper."""

    def _make_cog(self, agent_id="agent1"):
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value=agent_id)
        cog.bot.agent_manager.send_command = AsyncMock(return_value={
            "data": {
                "server_name": "TestServer",
                "files_restored": 100,
            }
        })
        return cog

    @pytest.mark.asyncio
    async def test_restore_finds_agent_via_helper(self):
        """RestoreModal must call get_connected_agent_for_guild (not raw loop)."""
        from bot.cogs.maintenance_gui import RestoreModal

        cog = self._make_cog()
        modal = RestoreModal(cog, 123, "D:\\Backups\\TestServer_backup_20260227.zip")
        modal.target_path = Mock(value="")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        await modal.on_submit(interaction)

        # The helper must have been called with the correct guild_id
        cog.bot.agent_manager.get_connected_agent_for_guild.assert_called_once_with(123)
        # And send_command must have been called (agent was found)
        cog.bot.agent_manager.send_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_fails_gracefully_when_no_agent(self):
        """RestoreModal must return a clear error when get_connected_agent_for_guild returns None."""
        from bot.cogs.maintenance_gui import RestoreModal

        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value=None)
        cog.bot.agent_manager.send_command = AsyncMock()

        modal = RestoreModal(cog, 123, "D:\\Backups\\test.zip")
        modal.target_path = Mock(value="")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        await modal.on_submit(interaction)

        # send_command must NOT be called when no agent is found
        cog.bot.agent_manager.send_command.assert_not_called()
        # And the user must receive an error via followup
        interaction.followup.send.assert_called_once()
        err_msg = interaction.followup.send.call_args.args[0]
        assert "❌" in err_msg

    @pytest.mark.asyncio
    async def test_restore_message_order(self):
        """Restore 'Starting' message must appear before 'Restore Complete' embed."""
        from bot.cogs.maintenance_gui import RestoreModal

        cog = self._make_cog()
        modal = RestoreModal(cog, 123, "D:\\Backups\\TestServer_backup_20260227.zip")
        modal.target_path = Mock(value="")

        call_order = []

        async def track_edit(content=None, embed=None, view=None):
            if content and "Starting" in content:
                call_order.append("starting")
            elif embed is not None:
                call_order.append("complete")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock(side_effect=track_edit)

        await modal.on_submit(interaction)

        assert "starting" in call_order
        assert "complete" in call_order
        assert call_order.index("starting") < call_order.index("complete")

    @pytest.mark.asyncio
    async def test_backup_modal_uses_helper(self):
        """ImmediateBackupModal must call get_connected_agent_for_guild (not raw loop)."""
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(return_value={
            "data": {"backup_file": "test.zip", "size_mb": "1.0",
                     "backup_type": "essentials", "file_count": 5}
        })

        modal = ImmediateBackupModal(cog, 123, "TestServer")
        modal.backup_type = Mock(value="essentials")
        modal.target_path = Mock(value="")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        # on_submit calls get_connected_agent_for_guild before scheduling the background task
        await modal.on_submit(interaction)

        cog.bot.agent_manager.get_connected_agent_for_guild.assert_called_once_with(123)


# ---------------------------------------------------------------------------
class TestExtractServerName:
    """Helper _extract_server_name parses server name from backup filename."""

    def test_extracts_simple_name(self):
        from bot.cogs.maintenance_gui import _extract_server_name
        result = _extract_server_name("D:\\Backups\\TestServer_backup_20260227_essentials.zip")
        assert result == "TestServer"

    def test_extracts_underscored_name(self):
        from bot.cogs.maintenance_gui import _extract_server_name
        result = _extract_server_name(
            "D:\\ArkTest\\asaserver_aberration\\Backups\\"
            "asaserver_aberration_backup_20260227_020000_essentials.zip"
        )
        assert result == "asaserver_aberration"

    def test_returns_empty_for_unknown_format(self):
        from bot.cogs.maintenance_gui import _extract_server_name
        result = _extract_server_name("D:\\Backups\\randomfile.zip")
        assert result == ""

    def test_handles_forward_slashes(self):
        from bot.cogs.maintenance_gui import _extract_server_name
        result = _extract_server_name("/opt/backups/MyServer_backup_20260301_full.zip")
        assert result == "MyServer"


class TestRestoreTargetView:
    """RestoreTargetView has Staging, Production, and Cancel buttons."""

    @pytest.mark.asyncio
    async def test_has_staging_button(self):
        from bot.cogs.maintenance_gui import RestoreTargetView
        view = RestoreTargetView(Mock(), 123, "D:\\Backups\\test.zip")
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Staging" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_production_button(self):
        from bot.cogs.maintenance_gui import RestoreTargetView
        view = RestoreTargetView(Mock(), 123, "D:\\Backups\\test.zip")
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Production" in l for l in labels)

    @pytest.mark.asyncio
    async def test_production_button_is_danger_style(self):
        from bot.cogs.maintenance_gui import RestoreTargetView
        view = RestoreTargetView(Mock(), 123, "D:\\Backups\\test.zip")
        btn = next(
            (c for c in view.children
             if isinstance(c, discord.ui.Button) and "Production" in (c.label or "")),
            None,
        )
        assert btn is not None
        assert btn.style == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_production_checks_server_status(self):
        from bot.cogs.maintenance_gui import RestoreTargetView
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(
            return_value={"data": {"online": False, "name": "TestServer"}}
        )
        view = RestoreTargetView(
            cog, 123, "D:\\Backups\\TestServer_backup_20260227_essentials.zip"
        )
        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        prod_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Production" in (c.label or "")
        )
        await prod_btn.callback(interaction)

        # get_status must have been called with the extracted server name
        cog.bot.agent_manager.send_command.assert_called_once()
        call = cog.bot.agent_manager.send_command.call_args
        assert call.args[1] == "get_status"
        assert call.args[2] == "TestServer"

    @pytest.mark.asyncio
    async def test_production_shows_warning_when_server_running(self):
        from bot.cogs.maintenance_gui import RestoreTargetView, ProductionRestoreWarningView
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(
            return_value={"data": {"online": True, "name": "TestServer"}}
        )
        view = RestoreTargetView(
            cog, 123, "D:\\Backups\\TestServer_backup_20260227_essentials.zip"
        )
        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        prod_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Production" in (c.label or "")
        )
        await prod_btn.callback(interaction)

        interaction.followup.send.assert_called_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert isinstance(kwargs.get("view"), ProductionRestoreWarningView)
        # Message must warn that the server is running
        assert "running" in kwargs.get("content", "").lower() or "Running" in kwargs.get("content", "")

    @pytest.mark.asyncio
    async def test_production_shows_ready_when_server_stopped(self):
        from bot.cogs.maintenance_gui import RestoreTargetView, ProductionRestoreReadyView
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(
            return_value={"data": {"online": False, "name": "TestServer"}}
        )
        view = RestoreTargetView(
            cog, 123, "D:\\Backups\\TestServer_backup_20260227_essentials.zip"
        )
        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        prod_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Production" in (c.label or "")
        )
        await prod_btn.callback(interaction)

        interaction.followup.send.assert_called_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert isinstance(kwargs.get("view"), ProductionRestoreReadyView)
        # Message must say server is stopped
        assert "stopped" in kwargs.get("content", "").lower()


class TestProductionRestoreWarningView:
    """Stop-and-restore flow when server is running."""

    @pytest.mark.asyncio
    async def test_has_stop_and_restore_button(self):
        from bot.cogs.maintenance_gui import ProductionRestoreWarningView
        view = ProductionRestoreWarningView(Mock(), 123, "a1", "Srv", "backup.zip")
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Stop" in l for l in labels)

    @pytest.mark.asyncio
    async def test_stops_server_then_restores(self):
        from bot.cogs.maintenance_gui import ProductionRestoreWarningView
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.send_command = AsyncMock(side_effect=[
            {"data": "stopped"},                                      # stop_server
            {"data": {"server_name": "TestServer", "files_restored": 50}},  # restore_server
        ])
        view = ProductionRestoreWarningView(
            cog, 123, "agent1", "TestServer",
            "D:\\Backups\\TestServer_backup_20260227.zip"
        )
        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        stop_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Stop" in (c.label or "")
        )
        await stop_btn.callback(interaction)

        calls = cog.bot.agent_manager.send_command.call_args_list
        assert len(calls) == 2
        assert calls[0].args[1] == "stop_server"
        assert calls[1].args[1] == "restore_server"

    @pytest.mark.asyncio
    async def test_shows_result_embed_after_restore(self):
        from bot.cogs.maintenance_gui import ProductionRestoreWarningView
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.send_command = AsyncMock(side_effect=[
            {"data": "stopped"},
            {"data": {"server_name": "TestServer", "files_restored": 100}},
        ])
        view = ProductionRestoreWarningView(
            cog, 123, "agent1", "TestServer",
            "D:\\Backups\\TestServer_backup_20260227.zip"
        )
        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        stop_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Stop" in (c.label or "")
        )
        await stop_btn.callback(interaction)

        final_call = interaction.edit_original_response.call_args_list[-1]
        assert final_call.kwargs.get("embed") is not None
        # Embed title must indicate success
        embed = final_call.kwargs["embed"]
        assert "Complete" in embed.title or "Restore" in embed.title

    @pytest.mark.asyncio
    async def test_aborts_restore_if_stop_fails(self):
        from bot.cogs.maintenance_gui import ProductionRestoreWarningView
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.send_command = AsyncMock(
            side_effect=Exception("Service not found")
        )
        view = ProductionRestoreWarningView(
            cog, 123, "agent1", "TestServer",
            "D:\\Backups\\TestServer_backup_20260227.zip"
        )
        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        stop_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Stop" in (c.label or "")
        )
        await stop_btn.callback(interaction)

        # restore_server must NOT have been called
        assert cog.bot.agent_manager.send_command.call_count == 1
        # Error message must be shown
        final_call = interaction.edit_original_response.call_args_list[-1]
        assert "❌" in (final_call.kwargs.get("content") or "")


class TestProductionRestoreReadyView:
    """Restore flow when server is already stopped."""

    @pytest.mark.asyncio
    async def test_has_confirm_restore_button(self):
        from bot.cogs.maintenance_gui import ProductionRestoreReadyView
        view = ProductionRestoreReadyView(Mock(), 123, "a1", "Srv", "backup.zip")
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Restore" in l for l in labels)

    @pytest.mark.asyncio
    async def test_restore_runs_and_shows_result(self):
        from bot.cogs.maintenance_gui import ProductionRestoreReadyView
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.send_command = AsyncMock(
            return_value={"data": {"server_name": "TestServer", "files_restored": 75}}
        )
        view = ProductionRestoreReadyView(
            cog, 123, "agent1", "TestServer",
            "D:\\Backups\\TestServer_backup_20260227.zip"
        )
        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        restore_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Restore" in (c.label or "")
        )
        await restore_btn.callback(interaction)

        cog.bot.agent_manager.send_command.assert_called_once()
        call = cog.bot.agent_manager.send_command.call_args
        assert call.args[1] == "restore_server"

        final_call = interaction.edit_original_response.call_args_list[-1]
        assert final_call.kwargs.get("embed") is not None


class TestRestoreStagingModal:
    """Staging restore modal sends restore with the user-provided path."""

    @pytest.mark.asyncio
    async def test_staging_restore_uses_provided_path(self):
        from bot.cogs.maintenance_gui import RestoreStagingModal
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(
            return_value={"data": {"server_name": "TestServer", "files_restored": 30}}
        )
        modal = RestoreStagingModal(
            cog, 123, "D:\\Backups\\TestServer_backup_20260227.zip"
        )
        modal.staging_path = Mock(value="D:\\Staging\\TestServer\\Saved")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        await modal.on_submit(interaction)

        call = cog.bot.agent_manager.send_command.call_args
        assert call.args[1] == "restore_server"
        params = call.kwargs.get("params") or (call.args[3] if len(call.args) > 3 else {})
        assert params.get("target_path") == "D:\\Staging\\TestServer\\Saved"

    @pytest.mark.asyncio
    async def test_staging_restore_shows_result_embed(self):
        from bot.cogs.maintenance_gui import RestoreStagingModal
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(
            return_value={"data": {"server_name": "TestServer", "files_restored": 30}}
        )
        modal = RestoreStagingModal(
            cog, 123, "D:\\Backups\\TestServer_backup_20260227.zip"
        )
        modal.staging_path = Mock(value="D:\\Staging\\TestServer\\Saved")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        await modal.on_submit(interaction)

        final_call = interaction.edit_original_response.call_args_list[-1]
        embed = final_call.kwargs.get("embed")
        assert embed is not None
        field_values = [f.value for f in embed.fields]
        assert any("Staging" in str(v) or "D:\\Staging" in str(v) for v in field_values)


# ---------------------------------------------------------------------------
# Change 1: RestoreConfirmView.confirm must use defer + followup.send
# ---------------------------------------------------------------------------

class TestRestoreConfirmViewFixedBehavior:
    """RestoreConfirmView.confirm must defer then followup (not edit_message)."""

    @pytest.mark.asyncio
    async def test_confirm_calls_defer(self):
        from bot.cogs.maintenance_gui import RestoreConfirmView
        cog = Mock()
        view = RestoreConfirmView(cog, 123, "D:\\Backups\\test.zip")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        confirm_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Confirm" in (c.label or "")
        )
        await confirm_btn.callback(interaction)

        interaction.response.defer.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_calls_followup_with_restore_target_view(self):
        from bot.cogs.maintenance_gui import RestoreConfirmView, RestoreTargetView
        cog = Mock()
        view = RestoreConfirmView(cog, 123, "D:\\Backups\\test.zip")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        confirm_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Confirm" in (c.label or "")
        )
        await confirm_btn.callback(interaction)

        interaction.followup.send.assert_called_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert isinstance(kwargs.get("view"), RestoreTargetView)
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_confirm_does_not_use_edit_message(self):
        from bot.cogs.maintenance_gui import RestoreConfirmView
        cog = Mock()
        view = RestoreConfirmView(cog, 123, "D:\\Backups\\test.zip")

        interaction = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        confirm_btn = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and "Confirm" in (c.label or "")
        )
        await confirm_btn.callback(interaction)

        interaction.response.edit_message.assert_not_called()


# ---------------------------------------------------------------------------
# Change 2: Command renamed from /maintcfg to /maintenance
# ---------------------------------------------------------------------------

class TestMaintenanceCommandRename:
    """The slash command must be named 'maintenance', not 'maintcfg'."""

    def test_command_name_is_maintenance(self):
        from bot.cogs.maintenance_gui import MaintenanceCog
        cog = MaintenanceCog.__new__(MaintenanceCog)
        # Find the command via class-level app_commands
        cmd = None
        for attr in dir(MaintenanceCog):
            obj = getattr(MaintenanceCog, attr, None)
            if hasattr(obj, "name") and obj.name == "maintenance":
                cmd = obj
                break
        assert cmd is not None, "Command named 'maintenance' not found on MaintenanceCog"

    def test_no_maintcfg_command(self):
        from bot.cogs.maintenance_gui import MaintenanceCog
        cmd = None
        for attr in dir(MaintenanceCog):
            obj = getattr(MaintenanceCog, attr, None)
            if hasattr(obj, "name") and obj.name == "maintcfg":
                cmd = obj
                break
        assert cmd is None, "Old 'maintcfg' command still exists — must be renamed to 'maintenance'"


# ---------------------------------------------------------------------------
# Change 3: Progress message format (no SteamCMD) + manual backup log
# ---------------------------------------------------------------------------

class TestProgressMessageFormat:
    """_log_progress_to_channel must not say 'SteamCMD'."""

    @pytest.mark.asyncio
    async def test_no_steamcmd_in_progress_message(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        manager = RemoteAgentManager()

        mock_bot = Mock()
        mock_channel = AsyncMock()
        mock_bot.get_channel = Mock(return_value=mock_channel)
        manager.set_bot(mock_bot)

        # Fake agent info
        manager.agents["test_agent"] = {"guild_id": 123}

        mock_config = {"server_log_channel_id": 456}
        with patch("bot.database.server_config_db.get_server_config", new_callable=AsyncMock, return_value=mock_config):
            await manager._log_progress_to_channel("test_agent", 20, "Backing up save files")

        mock_channel.send.assert_called_once()
        sent_msg = mock_channel.send.call_args.args[0]
        assert "SteamCMD" not in sent_msg, "Progress message must not contain 'SteamCMD'"

    @pytest.mark.asyncio
    async def test_progress_message_contains_percent_and_status(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        manager = RemoteAgentManager()

        mock_bot = Mock()
        mock_channel = AsyncMock()
        mock_bot.get_channel = Mock(return_value=mock_channel)
        manager.set_bot(mock_bot)
        manager.agents["test_agent"] = {"guild_id": 123}

        mock_config = {"server_log_channel_id": 456}
        with patch("bot.database.server_config_db.get_server_config", new_callable=AsyncMock, return_value=mock_config):
            await manager._log_progress_to_channel("test_agent", 60, "Compressing files")

        sent_msg = mock_channel.send.call_args.args[0]
        assert "60" in sent_msg
        assert "Compressing files" in sent_msg


class TestManualBackupCompletionLog:
    """ImmediateBackupModal must call _log_to_channel after successful backup."""

    def _make_cog(self, guild_id=123):
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(return_value={
            "data": {
                "backup_file": "D:\\Backups\\Server1_backup_20260227.zip",
                "size_mb": "100.0",
                "backup_type": "essentials",
                "file_count": 50,
            }
        })
        return cog

    @pytest.mark.asyncio
    async def test_log_to_channel_called_after_backup(self):
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        cog = self._make_cog()
        modal = ImmediateBackupModal(cog, 123, "Server1")

        interaction = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        log_calls = []

        async def capture_log(bot, guild_id, message):
            log_calls.append(message)

        with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
            with patch("bot.cogs.maintenance_gui._log_to_channel", side_effect=capture_log):
                await modal._run_backup_task(interaction, "agent1", "essentials", {})

        assert len(log_calls) == 1, "_log_to_channel must be called exactly once after manual backup"
        assert "Server1" in log_calls[0]


# ---------------------------------------------------------------------------
# Change 4: verify_backup called before RestoreConfirmView
# ---------------------------------------------------------------------------

class TestVerifyBackupBeforeRestore:
    """RestoreBackupView.select_backup must call verify_backup before RestoreConfirmView."""

    def _make_cog(self, backup_exists=True):
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(return_value={
            "data": {"exists": backup_exists, "backup_file": "D:\\Backups\\test.zip"}
        })
        return cog

    @pytest.mark.asyncio
    async def test_verify_backup_called(self):
        from bot.cogs.maintenance_gui import RestoreBackupView

        cog = self._make_cog(backup_exists=True)
        options = [discord.SelectOption(label="TestServer - 2026-02-27 (essentials)", value="D:\\Backups\\test.zip")]
        view = RestoreBackupView(cog, 123, options)

        interaction = AsyncMock()
        interaction.data = {"values": ["D:\\Backups\\test.zip"]}
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        await view.select_backup(interaction)

        # verify_backup must have been sent to the agent
        cog.bot.agent_manager.send_command.assert_called_once()
        call = cog.bot.agent_manager.send_command.call_args
        assert call.args[1] == "verify_backup"
        params = call.kwargs.get("params") or {}
        assert params.get("backup_path") == "D:\\Backups\\test.zip"

    @pytest.mark.asyncio
    async def test_error_shown_when_backup_missing(self):
        from bot.cogs.maintenance_gui import RestoreBackupView

        cog = self._make_cog(backup_exists=False)
        options = [discord.SelectOption(label="TestServer - 2026-02-27 (essentials)", value="D:\\Backups\\missing.zip")]
        view = RestoreBackupView(cog, 123, options)

        interaction = AsyncMock()
        interaction.data = {"values": ["D:\\Backups\\missing.zip"]}
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        await view.select_backup(interaction)

        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args.args[0] if interaction.followup.send.call_args.args else \
              interaction.followup.send.call_args.kwargs.get("content", "")
        assert "❌" in msg

    @pytest.mark.asyncio
    async def test_confirm_view_shown_when_backup_exists(self):
        from bot.cogs.maintenance_gui import RestoreBackupView, RestoreConfirmView

        cog = self._make_cog(backup_exists=True)
        options = [discord.SelectOption(label="TestServer - 2026-02-27 (essentials)", value="D:\\Backups\\test.zip")]
        view = RestoreBackupView(cog, 123, options)

        interaction = AsyncMock()
        interaction.data = {"values": ["D:\\Backups\\test.zip"]}
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        await view.select_backup(interaction)

        # The last followup.send should include RestoreConfirmView
        calls = interaction.followup.send.call_args_list
        # There should be a call with RestoreConfirmView
        confirm_calls = [
            c for c in calls
            if isinstance(c.kwargs.get("view"), RestoreConfirmView)
        ]
        assert len(confirm_calls) == 1, "RestoreConfirmView must be shown when backup exists"

    @pytest.mark.asyncio
    async def test_proceeds_if_verify_raises(self):
        """If verify_backup agent call fails, we proceed to confirm anyway (graceful degradation)."""
        from bot.cogs.maintenance_gui import RestoreBackupView, RestoreConfirmView

        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(side_effect=Exception("timeout"))

        options = [discord.SelectOption(label="TestServer", value="D:\\Backups\\test.zip")]
        view = RestoreBackupView(cog, 123, options)

        interaction = AsyncMock()
        interaction.data = {"values": ["D:\\Backups\\test.zip"]}
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()

        await view.select_backup(interaction)

        # Should still show confirm view
        calls = interaction.followup.send.call_args_list
        confirm_calls = [c for c in calls if isinstance(c.kwargs.get("view"), RestoreConfirmView)]
        assert len(confirm_calls) == 1, "Must show RestoreConfirmView even when verify_backup raises"


# ---------------------------------------------------------------------------
# Change 5: Multiple backup schedules — UI tests
# ---------------------------------------------------------------------------

class TestBackupSchedulesView:
    """BackupSchedulesView displays schedules and exposes CRUD buttons."""

    def _make_schedules(self):
        return [
            {"id": 1, "name": "Daily Essentials", "backup_type": "essentials",
             "schedule_type": "daily", "backup_time": "02:00", "day_of_week": 0, "enabled": 1},
            {"id": 2, "name": "Weekly Full", "backup_type": "full",
             "schedule_type": "weekly", "backup_time": "03:00", "day_of_week": 6, "enabled": 0},
        ]

    @pytest.mark.asyncio
    async def test_build_embed_shows_schedules(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        view = BackupSchedulesView(Mock(), 123, self._make_schedules())
        embed = view.build_embed()
        field_names = [f.name for f in embed.fields]
        assert "Daily Essentials" in field_names
        assert "Weekly Full" in field_names

    @pytest.mark.asyncio
    async def test_build_embed_empty_has_guidance(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        view = BackupSchedulesView(Mock(), 123, [])
        embed = view.build_embed()
        assert "Add Schedule" in embed.description or "No backup" in embed.description

    @pytest.mark.asyncio
    async def test_has_add_schedule_button(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        view = BackupSchedulesView(Mock(), 123, [])
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Add" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_edit_button(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        view = BackupSchedulesView(Mock(), 123, self._make_schedules())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Edit" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_delete_button(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        view = BackupSchedulesView(Mock(), 123, self._make_schedules())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Delete" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_select_menu_when_schedules_exist(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        view = BackupSchedulesView(Mock(), 123, self._make_schedules())
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_no_select_when_empty(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        view = BackupSchedulesView(Mock(), 123, [])
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        assert len(selects) == 0

    @pytest.mark.asyncio
    async def test_add_schedule_opens_modal(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView, AddScheduleModal
        cog = Mock()
        cog.is_admin = AsyncMock(return_value=True)
        view = BackupSchedulesView(cog, 123, [])

        interaction = AsyncMock()
        add_btn = next(c for c in view.children if isinstance(c, discord.ui.Button) and "Add" in (c.label or ""))
        await add_btn.callback(interaction)

        interaction.response.send_modal.assert_called_once()
        modal_arg = interaction.response.send_modal.call_args.args[0]
        assert isinstance(modal_arg, AddScheduleModal)

    @pytest.mark.asyncio
    async def test_delete_requires_selection(self):
        from bot.cogs.maintenance_gui import BackupSchedulesView
        cog = Mock()
        cog.is_admin = AsyncMock(return_value=True)
        view = BackupSchedulesView(cog, 123, self._make_schedules())

        interaction = AsyncMock()
        del_btn = next(c for c in view.children if isinstance(c, discord.ui.Button) and "Delete" in (c.label or ""))
        await del_btn.callback(interaction)

        # No value selected — should show error
        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0] if interaction.response.send_message.call_args.args else ""
        assert "Select" in msg or "select" in msg

    @pytest.mark.asyncio
    async def test_edit_refetches_from_db(self):
        """edit_schedule must fetch fresh data from DB so target_directory is always current."""
        from bot.cogs.maintenance_gui import BackupSchedulesView, AddScheduleModal

        # Stale in-memory schedule — target_directory is None (as loaded before user saved)
        stale_schedule = {
            "id": 1, "name": "Daily", "backup_type": "essentials",
            "schedule_type": "daily", "backup_time": "02:00", "day_of_week": 0,
            "enabled": 1, "target_directory": None,
        }
        # Fresh schedule — target_directory now set (as stored in DB after user saved)
        fresh_schedule = {**stale_schedule, "target_directory": "D:\\ARK\\Backups"}

        cog = Mock()
        cog.is_admin = AsyncMock(return_value=True)
        view = BackupSchedulesView(cog, 123, [stale_schedule])

        # Simulate schedule id 1 being selected in the dropdown
        for item in view.children:
            if isinstance(item, discord.ui.Select):
                item._values = ["1"]

        interaction = AsyncMock()
        edit_btn = next(c for c in view.children if isinstance(c, discord.ui.Button) and "Edit" in (c.label or ""))

        with patch("bot.database.maintenance_db.get_backup_schedules",
                   new_callable=AsyncMock, return_value=[fresh_schedule]) as mock_fetch:
            await edit_btn.callback(interaction)

        # DB must be queried for fresh data
        mock_fetch.assert_called_once_with(123)
        # Modal must be opened with the fresh schedule (target_directory pre-populated)
        interaction.response.send_modal.assert_called_once()
        modal_arg = interaction.response.send_modal.call_args.args[0]
        assert isinstance(modal_arg, AddScheduleModal)
        assert modal_arg.target_directory.default == "D:\\ARK\\Backups"


class TestAddScheduleModal:
    """AddScheduleModal parses schedule string and saves to DB."""

    @pytest.mark.asyncio
    async def test_valid_daily_schedule(self):
        from bot.cogs.maintenance_gui import AddScheduleModal
        cog = Mock()
        modal = AddScheduleModal(cog, 123)
        modal.sched_name = Mock(value="Daily Test")
        modal.backup_type = Mock(value="essentials")
        modal.schedule = Mock(value="daily@03:00")
        modal.enabled = Mock(value="yes")
        modal.target_directory = Mock(value="")

        interaction = AsyncMock()
        saved = []

        async def fake_add(guild_id, name, **kwargs):
            saved.append({"guild_id": guild_id, "name": name, **kwargs})
            return 1

        with patch("bot.database.maintenance_db.add_backup_schedule", side_effect=fake_add):
            await modal.on_submit(interaction)

        assert len(saved) == 1
        assert saved[0]["schedule_type"] == "daily"
        assert saved[0]["backup_time"] == "03:00"
        assert saved[0]["enabled"] == 1

    @pytest.mark.asyncio
    async def test_valid_weekly_schedule(self):
        from bot.cogs.maintenance_gui import AddScheduleModal
        cog = Mock()
        modal = AddScheduleModal(cog, 123)
        modal.sched_name = Mock(value="Weekly Full")
        modal.backup_type = Mock(value="full")
        modal.schedule = Mock(value="weekly@sun@04:00")
        modal.enabled = Mock(value="yes")
        modal.target_directory = Mock(value="")

        interaction = AsyncMock()
        saved = []

        async def fake_add(guild_id, name, **kwargs):
            saved.append(kwargs)
            return 1

        with patch("bot.database.maintenance_db.add_backup_schedule", side_effect=fake_add):
            await modal.on_submit(interaction)

        assert saved[0]["schedule_type"] == "weekly"
        assert saved[0]["backup_time"] == "04:00"
        assert saved[0]["day_of_week"] == 6  # Sunday

    @pytest.mark.asyncio
    async def test_invalid_backup_type_shows_error(self):
        from bot.cogs.maintenance_gui import AddScheduleModal
        cog = Mock()
        modal = AddScheduleModal(cog, 123)
        modal.sched_name = Mock(value="Bad")
        modal.backup_type = Mock(value="invalid_type")
        modal.schedule = Mock(value="daily@02:00")
        modal.enabled = Mock(value="yes")
        modal.target_directory = Mock(value="")

        interaction = AsyncMock()
        with patch("bot.database.maintenance_db.add_backup_schedule", new_callable=AsyncMock):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0] if interaction.response.send_message.call_args.args else ""
        assert "❌" in msg

    @pytest.mark.asyncio
    async def test_invalid_schedule_format_shows_error(self):
        from bot.cogs.maintenance_gui import AddScheduleModal
        cog = Mock()
        modal = AddScheduleModal(cog, 123)
        modal.sched_name = Mock(value="Bad Schedule")
        modal.backup_type = Mock(value="essentials")
        modal.schedule = Mock(value="monthly@02:00")  # invalid schedule type
        modal.enabled = Mock(value="yes")
        modal.target_directory = Mock(value="")

        interaction = AsyncMock()
        with patch("bot.database.maintenance_db.add_backup_schedule", new_callable=AsyncMock):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0] if interaction.response.send_message.call_args.args else ""
        assert "❌" in msg

    @pytest.mark.asyncio
    async def test_edit_mode_calls_update_not_add(self):
        from bot.cogs.maintenance_gui import AddScheduleModal
        cog = Mock()
        existing = {
            "id": 42, "name": "Old Name", "backup_type": "essentials",
            "schedule_type": "daily", "backup_time": "02:00", "day_of_week": 0, "enabled": 1,
            "target_directory": None,
        }
        modal = AddScheduleModal(cog, 123, schedule=existing)
        modal.sched_name = Mock(value="New Name")
        modal.backup_type = Mock(value="full")
        modal.schedule = Mock(value="daily@05:00")
        modal.enabled = Mock(value="no")
        modal.target_directory = Mock(value="")

        interaction = AsyncMock()
        update_calls = []

        async def fake_update(schedule_id, **kwargs):
            update_calls.append((schedule_id, kwargs))
            return True

        with patch("bot.database.maintenance_db.update_backup_schedule", side_effect=fake_update):
            with patch("bot.database.maintenance_db.add_backup_schedule", new_callable=AsyncMock) as mock_add:
                await modal.on_submit(interaction)
                mock_add.assert_not_called()

        assert len(update_calls) == 1
        sid, kwargs = update_calls[0]
        assert sid == 42
        assert kwargs["name"] == "New Name"
        assert kwargs["backup_type"] == "full"
        assert kwargs["enabled"] == 0

    @pytest.mark.asyncio
    async def test_target_directory_is_saved(self):
        """target_directory must be passed through to add_backup_schedule."""
        from bot.cogs.maintenance_gui import AddScheduleModal
        cog = Mock()
        modal = AddScheduleModal(cog, 123)
        modal.sched_name = Mock(value="Daily Test")
        modal.backup_type = Mock(value="essentials")
        modal.schedule = Mock(value="daily@03:00")
        modal.enabled = Mock(value="yes")
        modal.target_directory = Mock(value="D:\\ARK\\Backups")

        interaction = AsyncMock()
        saved = []

        async def fake_add(guild_id, name, **kwargs):
            saved.append({"guild_id": guild_id, "name": name, **kwargs})
            return 1

        with patch("bot.database.maintenance_db.add_backup_schedule", side_effect=fake_add):
            await modal.on_submit(interaction)

        assert saved[0].get("target_directory") == "D:\\ARK\\Backups"

    @pytest.mark.asyncio
    async def test_empty_target_directory_saved_as_none(self):
        """Empty target_directory input must be stored as None (not empty string)."""
        from bot.cogs.maintenance_gui import AddScheduleModal
        cog = Mock()
        modal = AddScheduleModal(cog, 123)
        modal.sched_name = Mock(value="Daily Test")
        modal.backup_type = Mock(value="essentials")
        modal.schedule = Mock(value="daily@03:00")
        modal.enabled = Mock(value="yes")
        modal.target_directory = Mock(value="")

        interaction = AsyncMock()
        saved = []

        async def fake_add(guild_id, name, **kwargs):
            saved.append({"guild_id": guild_id, "name": name, **kwargs})
            return 1

        with patch("bot.database.maintenance_db.add_backup_schedule", side_effect=fake_add):
            await modal.on_submit(interaction)

        assert saved[0].get("target_directory") is None


# ---------------------------------------------------------------------------
# Change 5: backup_scheduler reads from backup_schedules table
# ---------------------------------------------------------------------------

class CapturingAgentManager:
    """Real agent manager that records commands sent — no mocks."""

    def __init__(self, update_error: bool = False):
        self.sent: list = []  # list of (agent_id, command, server_name, kwargs)
        self._update_error = update_error

    async def get_connected_agent_for_guild(self, guild_id: int):
        return "test-agent-001"

    async def send_command(self, agent_id, command, server_name, **kwargs):
        self.sent.append((agent_id, command, server_name, kwargs))
        if self._update_error and command == "update_server":
            return {"type": "error", "error": "SteamCMD failed"}
        return {"data": {"backup_file": "backup.zip", "size_mb": "1.0",
                         "backup_type": "essentials", "file_count": 10}}


class MinimalBot:
    """Minimal real bot stub for scheduler testing — no mocks."""

    def __init__(self, agent_manager=None):
        self.guilds = []
        self.agent_manager = agent_manager

    def get_channel(self, channel_id):
        return None  # No Discord connection in tests; _log_to_channel handles this gracefully


class TestBackupSchedulerUsesNewTable:
    """backup_scheduler must iterate backup_schedules, not maintenance_config."""

    def _make_cog(self, agent_manager=None):
        from bot.cogs.maintenance_gui import MaintenanceCog
        cog = MaintenanceCog.__new__(MaintenanceCog)
        cog.bot = MinimalBot(agent_manager=agent_manager)
        cog._already_run = set()
        return cog

    async def _setup_db(self, initialized_db, backup_time="02:00", target_directory=None):
        """Insert real server config + ark server + backup schedule into the test DB."""
        from bot.database import server_config_db, maintenance_db
        guild_id = 123
        await server_config_db.create_or_update_server_config(guild_id, "Test Guild")
        await server_config_db.add_ark_server(
            guild_id, name="Server1", host="127.0.0.1",
            rcon_port=27020, rcon_password="test",
        )
        await maintenance_db.add_backup_schedule(
            guild_id, "Daily", backup_time=backup_time,
            target_directory=target_directory,
        )
        return guild_id

    @pytest.mark.asyncio
    async def test_scheduler_calls_get_all_enabled_backup_schedules(self, initialized_db):
        """Scheduler must query backup_schedules table on every tick."""
        await self._setup_db(initialized_db, backup_time="03:00")  # won't match _now
        cog = self._make_cog()
        now = datetime(2026, 2, 27, 2, 0, 0, tzinfo=timezone.utc)
        await cog.backup_scheduler.coro(cog, _now=now)
        # Schedule exists but time didn't match — _already_run stays empty (no execution)
        assert len(cog._already_run) == 0

    @pytest.mark.asyncio
    async def test_scheduler_skips_wrong_time(self, initialized_db):
        """Scheduler must not run when current time doesn't match schedule."""
        await self._setup_db(initialized_db, backup_time="03:00")
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        # _now is 02:00 but schedule is 03:00
        now = datetime(2026, 2, 27, 2, 0, 0, tzinfo=timezone.utc)
        await cog.backup_scheduler.coro(cog, _now=now)
        assert len(agent.sent) == 0, "Must not send command when time does not match"

    @pytest.mark.asyncio
    async def test_scheduler_prevents_double_run(self, initialized_db):
        """Running scheduler twice at same time must only trigger one backup."""
        await self._setup_db(initialized_db, backup_time="02:00")
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 2, 0, 0, tzinfo=timezone.utc)
        await cog.backup_scheduler.coro(cog, _now=now)
        await cog.backup_scheduler.coro(cog, _now=now)
        backup_calls = [s for s in agent.sent if s[1] == "backup_server"]
        assert len(backup_calls) == 1, "Scheduler must not double-run for the same schedule in the same minute"

    @pytest.mark.asyncio
    async def test_scheduler_uses_schedule_target_directory(self, initialized_db):
        """target_directory in schedule must be sent as backup_path to agent."""
        await self._setup_db(initialized_db, backup_time="02:00", target_directory="D:\\ARK\\Backups")
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 2, 0, 0, tzinfo=timezone.utc)
        await cog.backup_scheduler.coro(cog, _now=now)
        assert len(agent.sent) == 1, "Expected one backup_server call"
        _, command, _, kwargs = agent.sent[0]
        assert command == "backup_server"
        params = kwargs.get("params", {})
        assert params.get("backup_path") == "D:\\ARK\\Backups", \
            "Scheduler must use the schedule's target_directory as backup_path"

    @pytest.mark.asyncio
    async def test_scheduler_no_backup_path_when_target_directory_empty(self, initialized_db):
        """When schedule has no target_directory, backup_path must not be sent to agent."""
        await self._setup_db(initialized_db, backup_time="02:00", target_directory=None)
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 2, 0, 0, tzinfo=timezone.utc)
        await cog.backup_scheduler.coro(cog, _now=now)
        assert len(agent.sent) == 1, "Expected one backup_server call"
        _, _, _, kwargs = agent.sent[0]
        params = kwargs.get("params", {})
        assert "backup_path" not in params, \
            "backup_path must not be sent when schedule has no target_directory"


# ---------------------------------------------------------------------------
# Change 6: Backup All Servers (__ALL__)
# ---------------------------------------------------------------------------

class TestBackupAllServers:
    """ImmediateBackupView must show 'All Servers' option, and __ALL__ triggers all-server backup."""

    @pytest.mark.asyncio
    async def test_all_servers_option_in_view(self):
        """backup_now button must prepend an 'All Servers' option."""
        from bot.cogs.maintenance_gui import ImmediateBackupView

        options = [
            discord.SelectOption(label="All Servers", value="__ALL__", description="Back up every configured server"),
            discord.SelectOption(label="Server1", value="Server1"),
        ]
        view = ImmediateBackupView(Mock(), 123, options)
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        values = [o.value for o in select.options]
        assert "__ALL__" in values

    def _make_cog(self, n_servers=2):
        cog = Mock()
        cog.bot.agent_manager = Mock()
        cog.bot.agent_manager.get_connected_agent_for_guild = AsyncMock(return_value="agent1")
        cog.bot.agent_manager.send_command = AsyncMock(return_value={
            "data": {"backup_file": "test.zip", "size_mb": "50.0", "backup_type": "essentials", "file_count": 10}
        })
        return cog

    @pytest.mark.asyncio
    async def test_all_servers_calls_send_command_n_times(self):
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        servers = [{"name": "Server1"}, {"name": "Server2"}, {"name": "Server3"}]
        cog = self._make_cog()

        modal = ImmediateBackupModal(cog, 123, "__ALL__")

        interaction = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        interaction.client = Mock()

        with patch("bot.database.server_config_db.get_ark_servers", new_callable=AsyncMock, return_value=servers):
            with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
                with patch("bot.cogs.maintenance_gui._log_to_channel", new_callable=AsyncMock):
                    await modal._run_backup_task(interaction, "agent1", "essentials", {})

        # send_command should be called once per server
        assert cog.bot.agent_manager.send_command.call_count == len(servers), \
            f"Expected {len(servers)} send_command calls for __ALL__"

    @pytest.mark.asyncio
    async def test_all_servers_result_is_summary_embed(self):
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        servers = [{"name": "Server1"}, {"name": "Server2"}]
        cog = self._make_cog()

        modal = ImmediateBackupModal(cog, 123, "__ALL__")

        captured_embeds = []

        async def capture_edit(content=None, embed=None, view=None):
            if embed is not None:
                captured_embeds.append(embed)

        interaction = AsyncMock()
        interaction.edit_original_response = AsyncMock(side_effect=capture_edit)
        interaction.client = Mock()

        with patch("bot.database.server_config_db.get_ark_servers", new_callable=AsyncMock, return_value=servers):
            with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
                with patch("bot.cogs.maintenance_gui._log_to_channel", new_callable=AsyncMock):
                    await modal._run_backup_task(interaction, "agent1", "essentials", {})

        assert len(captured_embeds) == 1, "Should produce exactly one summary embed for __ALL__"
        embed = captured_embeds[0]
        # Both servers should appear in the description
        assert "Server1" in embed.description
        assert "Server2" in embed.description

    @pytest.mark.asyncio
    async def test_all_servers_starting_message_shown_first(self):
        from bot.cogs.maintenance_gui import ImmediateBackupModal

        servers = [{"name": "Server1"}]
        cog = self._make_cog()

        modal = ImmediateBackupModal(cog, 123, "__ALL__")

        call_order = []

        async def track(content=None, embed=None, view=None):
            if content and ("Starting" in content or "all" in content.lower()):
                call_order.append("starting")
            elif embed is not None:
                call_order.append("summary")

        interaction = AsyncMock()
        interaction.edit_original_response = AsyncMock(side_effect=track)
        interaction.client = Mock()

        with patch("bot.database.server_config_db.get_ark_servers", new_callable=AsyncMock, return_value=servers):
            with patch("bot.database.maintenance_db.add_backup_history", new_callable=AsyncMock):
                with patch("bot.cogs.maintenance_gui._log_to_channel", new_callable=AsyncMock):
                    await modal._run_backup_task(interaction, "agent1", "essentials", {})

        assert "starting" in call_order
        assert "summary" in call_order
        assert call_order.index("starting") < call_order.index("summary")


# ---------------------------------------------------------------------------
# Change 5: MaintenanceMainView build_embed uses schedule_count param
# ---------------------------------------------------------------------------

class TestMaintenanceMainViewScheduleCount:
    """build_embed shows active schedule count instead of old inline schedule fields."""

    @pytest.mark.asyncio
    async def test_embed_shows_schedule_count(self):
        from bot.cogs.maintenance_gui import MaintenanceMainView
        settings = {"guild_id": 123, "backup_enabled": 1}
        view = MaintenanceMainView(Mock(), 123, settings)
        embed = view.build_embed(schedule_count=3)
        backup_field = next((f for f in embed.fields if "Backup" in f.name), None)
        assert backup_field is not None
        assert "3" in backup_field.value

    @pytest.mark.asyncio
    async def test_embed_shows_zero_schedules(self):
        from bot.cogs.maintenance_gui import MaintenanceMainView
        settings = {"guild_id": 123}
        view = MaintenanceMainView(Mock(), 123, settings)
        embed = view.build_embed(schedule_count=0)
        backup_field = next((f for f in embed.fields if "Backup" in f.name), None)
        assert backup_field is not None
        assert "No" in backup_field.value or "0" in backup_field.value

    @pytest.mark.asyncio
    async def test_backup_schedules_button_exists(self):
        from bot.cogs.maintenance_gui import MaintenanceMainView
        view = MaintenanceMainView(Mock(), 123, {})
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Schedule" in l for l in labels), "Must have a 'Backup Schedules' button"

    @pytest.mark.asyncio
    async def test_backup_settings_button_removed(self):
        """The old 'Backup Settings' button must no longer exist on the main view."""
        from bot.cogs.maintenance_gui import MaintenanceMainView
        view = MaintenanceMainView(Mock(), 123, {})
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert not any("Backup Settings" in l for l in labels), \
            "'Backup Settings' button must be removed — per-schedule target_directory replaces it"

    @pytest.mark.asyncio
    async def test_embed_has_no_backup_target_field(self):
        """The 'Backup Target' embed field must no longer appear — target is now per-schedule."""
        from bot.cogs.maintenance_gui import MaintenanceMainView
        settings = {"guild_id": 123, "backup_root_path": "D:\\Old\\Path"}
        embed = MaintenanceMainView(Mock(), 123, settings).build_embed()
        field = next((f for f in embed.fields if "Backup Target" in f.name), None)
        assert field is None, "Global 'Backup Target' field must be removed from main embed"


# ---------------------------------------------------------------------------
# Update Scheduler
# ---------------------------------------------------------------------------

class TestUpdateScheduler:
    """update_scheduler must call get_all_enabled_update_configs and run stop/update/start."""

    def _make_cog(self, agent_manager=None):
        from bot.cogs.maintenance_gui import MaintenanceCog
        cog = MaintenanceCog.__new__(MaintenanceCog)
        cog.bot = MinimalBot(agent_manager=agent_manager)
        cog._update_already_run = set()
        return cog

    async def _setup_db(self, initialized_db, update_time="03:00", schedule_type="daily",
                        day_of_week=0, enable_saveworld=0, enable_pre_update_backup=0):
        """Insert real server config + ark server + update config into the test DB."""
        from bot.database import server_config_db, maintenance_db
        guild_id = 123
        await server_config_db.create_or_update_server_config(guild_id, "Test Guild")
        await server_config_db.add_ark_server(
            guild_id, name="Srv", host="127.0.0.1",
            rcon_port=27020, rcon_password="test",
            steamcmd_path="", server_path="",
        )
        await maintenance_db.update_maintenance_config(guild_id,
            update_enabled=1,
            update_time=update_time,
            update_schedule_type=schedule_type,
            update_day_of_week=day_of_week,
            enable_saveworld=enable_saveworld,
            enable_pre_update_backup=enable_pre_update_backup,
        )
        return guild_id

    @pytest.mark.asyncio
    async def test_calls_get_all_enabled_update_configs(self, initialized_db):
        """Scheduler must query maintenance_config table on every tick."""
        await self._setup_db(initialized_db, update_time="04:00")  # won't match _now
        cog = self._make_cog()
        # _now at 03:00, config has 04:00 — schedule won't match
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)
        await cog.update_scheduler.coro(cog, _now=now)
        # Scheduler ran and checked configs, but skipped (time mismatch)
        assert len(cog._update_already_run) == 0

    @pytest.mark.asyncio
    async def test_skips_wrong_time(self, initialized_db):
        """Scheduler must not run when current time doesn't match update_time."""
        await self._setup_db(initialized_db, update_time="04:00")
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)  # 03:00 doesn't match 04:00
        await cog.update_scheduler.coro(cog, _now=now)
        assert len(agent.sent) == 0, "Must not send command when time does not match"

    @pytest.mark.asyncio
    async def test_weekly_skips_wrong_day(self, initialized_db):
        """Weekly schedule must skip on non-matching day of week."""
        # day_of_week=0 = Monday; Feb 27 2026 is Friday (weekday 4)
        await self._setup_db(initialized_db, update_time="03:00", schedule_type="weekly", day_of_week=0)
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)  # Friday
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        assert len(agent.sent) == 0, "Weekly schedule must skip on wrong day"

    @pytest.mark.asyncio
    async def test_weekly_runs_on_right_day(self, initialized_db):
        """Weekly schedule must run on matching day of week."""
        # day_of_week=0 = Monday; March 2 2026 is Monday (weekday 0)
        await self._setup_db(initialized_db, update_time="03:00", schedule_type="weekly", day_of_week=0)
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 3, 2, 3, 0, 0, tzinfo=timezone.utc)  # Monday
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        commands_called = [s[1] for s in agent.sent]
        assert "update_server" in commands_called, "Weekly schedule must run on the right day"

    @pytest.mark.asyncio
    async def test_prevents_double_run(self, initialized_db):
        """Running update scheduler twice at same time must only trigger one update."""
        await self._setup_db(initialized_db, update_time="03:00")
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        update_calls = [s for s in agent.sent if s[1] == "update_server"]
        assert len(update_calls) == 1, "update_server must only be called once for the same minute"

    @pytest.mark.asyncio
    async def test_stop_update_start_sequence(self, initialized_db):
        """Scheduler must call stop_server, then update_server, then start_server in order."""
        await self._setup_db(initialized_db, update_time="03:00")
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        call_order = [s[1] for s in agent.sent]
        assert call_order.index("stop_server") < call_order.index("update_server"), \
            "stop_server must come before update_server"
        assert call_order.index("update_server") < call_order.index("start_server"), \
            "update_server must come before start_server"

    @pytest.mark.asyncio
    async def test_pre_update_backup_called_when_enabled(self, initialized_db):
        """When enable_pre_update_backup=1, backup_server must be called before update."""
        await self._setup_db(initialized_db, update_time="03:00", enable_pre_update_backup=1)
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        commands_called = [s[1] for s in agent.sent]
        assert "backup_server" in commands_called, "backup_server must be called for pre-update backup"

    @pytest.mark.asyncio
    async def test_no_agent_skips_gracefully(self, initialized_db):
        """If no agent is connected, scheduler must skip without error."""
        await self._setup_db(initialized_db, update_time="03:00")

        class NoAgentManager:
            async def get_connected_agent_for_guild(self, guild_id):
                return None

        cog = self._make_cog(agent_manager=NoAgentManager())
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)
        # Should not raise, just skip silently
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)

    @pytest.mark.asyncio
    async def test_update_error_skips_start_server(self, initialized_db):
        """If update_server returns an error, start_server must not be called."""
        await self._setup_db(initialized_db, update_time="03:00")
        agent = CapturingAgentManager(update_error=True)
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        commands_called = [s[1] for s in agent.sent]
        assert "start_server" not in commands_called, \
            "start_server must not be called after a failed update"

    @pytest.mark.asyncio
    async def test_update_server_called_without_validate(self, initialized_db):
        """Scheduled updates must NOT use SteamCMD validate — it doubles runtime unnecessarily."""
        await self._setup_db(initialized_db, update_time="03:00")
        agent = CapturingAgentManager()
        cog = self._make_cog(agent_manager=agent)
        now = datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)
        await cog.update_scheduler.coro(cog, _now=now, _stop_delay=0)
        update_call = next((s for s in agent.sent if s[1] == "update_server"), None)
        assert update_call is not None, "update_server must be called"
        params = update_call[3].get("params", {})
        assert params.get("validate") is False, \
            "Scheduled updates must pass validate=False to avoid unnecessary SteamCMD validation"
