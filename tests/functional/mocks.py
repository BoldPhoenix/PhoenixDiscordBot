"""Reusable fakes/mocks for functional command tests (no network/discord).
"""

import asyncio
from typing import Any


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []

    async def defer(self, ephemeral: bool = False):
        self.deferred = True

    async def send_message(self, content=None, embed=None, ephemeral=None, view=None):
        self.messages.append({"content": content, "embed": embed, "view": view, "ephemeral": ephemeral})

    def is_done(self):
        return self.deferred or len(self.messages) > 0


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content=None, embed=None, ephemeral=None, view=None):
        self.messages.append({"content": content, "embed": embed, "view": view, "ephemeral": ephemeral})
        return None


class FakeGuildPerms:
    def __init__(self, administrator: bool = False):
        self.administrator = administrator


class FakeRole:
    def __init__(self, role_id: int):
        self.id = role_id


class FakeUser:
    def __init__(self, user_id: int, name: str, roles=None, is_admin: bool = False):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.mention = f"@{name}"
        self.roles = roles or []
        self.guild_permissions = FakeGuildPerms(administrator=is_admin)


class FakeInteraction:
    def __init__(self, user: FakeUser, client=None):
        self.user = user
        self.client = client
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data: dict[str, Any] = {}


class FakeRconClient:
    def __init__(self, players_online: list[dict]):
        self.players_online = players_online
        self.commands: list[str] = []

    async def get_player_list(self):
        return self.players_online

    async def execute_command(self, command: str):
        self.commands.append(command)
        return "OK"


class FakeRconManager:
    def __init__(self, clients: dict):
        self.clients = clients


class FakeServerMonitor:
    def __init__(self, clients: dict, status_cache: dict):
        self.rcon_manager = FakeRconManager(clients)
        self.server_status_cache = status_cache


class FakeEventsConfig:
    def __init__(self, config: dict):
        self.config = config

    def get_event_config(self, name: str):
        return self.config if name == "christmas" else None


class FakeBot:
    def __init__(self, cogs: dict):
        self._cogs = cogs

    def get_cog(self, name: str):
        return self._cogs.get(name)

    async def wait_until_ready(self):
        """Mock wait_until_ready to prevent task exceptions."""
        return
