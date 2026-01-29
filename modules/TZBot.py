import asyncio
import contextlib
import copy
import datetime
import json
import re
import tarfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Final, AsyncGenerator

import discord
import geoip2
import maxminddb.errors
from aiohttp import ClientSession, BasicAuth, ClientResponseError
from discord import ExtensionAlreadyLoaded, ExtensionFailed, ExtensionNotFound, ExtensionNotLoaded, NoEntryPointError, \
    User, Option, SlashCommand
from discord.ext import bridge
from discord.ext.bridge import BridgeSlashCommand
from discord.ext.commands import errors
from geoip2 import database  # noqa: F401
from six import BytesIO

from database.APIKeyDatabase import ApiKeyDatabase
from database.DataDatabase import Database
from database.stats.StatsDatabase import StatsDatabase
from server.APIServer import APIServer
from server.ServerLogger import ServerLogger
from shared.Constants import CONFIG_FILE, GEO_IP_DB_FILE, DIALOG_OWNERS_FILE, SUCCESS, FAIL, HTTP_HEADERS, DAY_SECONDS, \
    GEO_IP_URL, MODULES_DIR, SORRY_PATTERN, ROMANIA_PATTERN
from shared.Helpers import Helpers
from shared.Types import Config, Command
from shell.Logger import Logger


class TZBot(bridge.Bot):
    loadedModules: list[str] = []
    loadedCommands: list[Command] = []

    API_SERVER: Final[APIServer]
    API_SERVER_TASK: Final[asyncio.Task]
    API_PACKET_LOGGER: Final[ServerLogger]

    syncOverride: bool = False

    def __init__(this, **kwargs) -> None:
        super().__init__(**kwargs)

        with CONFIG_FILE.open("r") as f:
            this.config: Config = Config.schema().loads(f.read())

        Helpers.tzBot = this

        this.ownerId = this.config.ownerId
        this.linkCodes: dict[str, tuple[str, str]] = {}
        this.db: Database = Database(this.config.mariadbDetails)
        this.apiDb = ApiKeyDatabase(this.config.server.apiKeysKey)
        if not GEO_IP_DB_FILE.parent.exists():
            GEO_IP_DB_FILE.parent.mkdir(exist_ok=True)
        if not GEO_IP_DB_FILE.exists():
            GEO_IP_DB_FILE.touch(exist_ok=True)
        try:
            this.maxMindDb: geoip2.database.Reader = geoip2.database.Reader(GEO_IP_DB_FILE)
        except maxminddb.errors.InvalidDatabaseError:
            Logger.error("MaxMind DB is invalid, will fetch")
            this.syncOverride = True

        this.statsDb: Final[StatsDatabase] = StatsDatabase()

        if not DIALOG_OWNERS_FILE.exists():
            DIALOG_OWNERS_FILE.touch()
        try:
            with DIALOG_OWNERS_FILE.open("r") as f:
                this.dialogOwners: set[int] = set(json.loads(f.read()))
        except json.JSONDecodeError:
            this.dialogOwners: set[int] = set()

        this.API_PACKET_LOGGER = ServerLogger(this, True)
        this.API_SERVER = APIServer(this)

    # Command Response
    async def getSuccess(this, *, description: str | None = None, user: discord.User | None = None) -> discord.Embed:
        successCpy = copy.deepcopy(SUCCESS)
        successCpy.timestamp = datetime.datetime.now()
        if user:
            successCpy.set_footer(text=user.name, icon_url=user.avatar.url)
        if description:
            successCpy.description = description

        return successCpy

    async def getFail(this, *, description: str | None = None, user: discord.User | None = None) -> discord.Embed:
        failCpy = copy.deepcopy(FAIL)
        failCpy.timestamp = datetime.datetime.now()
        if user:
            failCpy.set_footer(text=user.name, icon_url=user.avatar.url)
        if description:
            failCpy.description = description

        return failCpy

    # HTTP Client
    @contextlib.asynccontextmanager
    async def getNewClient(this, contentTypes: set[str]) -> AsyncGenerator[ClientSession]:
        headersCpy = deepcopy(HTTP_HEADERS)
        headersCpy["Accept"] = ",".join(contentTypes)
        session = ClientSession(headers=headersCpy)
        try:
            yield session
        finally:
            await session.close()

    # Internet shit
    async def downloadFile(this, url: str, contentTypes: set[str]) -> tuple[str, bytes] | None:
        Logger.log(f"Downloading from {url}")
        try:
            async with this.getNewClient(contentTypes) as session:
                async with session.get(url) as response:
                    if response.status == 200 and response.content_type in contentTypes:
                        Logger.success("Download was successful!")
                        return response.content_type, await response.read()

                    else:
                        Logger.error(f"Download failed! Content type: {response.content_type}; Code: {response.status}")
                        Logger.error(await response.read())
                        return None
        except ClientResponseError as e:
            Logger.error(f"Download failed!")
            Logger.error(e)

    async def syncGeoIP(this):
        if not this.syncOverride:
            if GEO_IP_DB_FILE.is_file():
                currentTime = time.time()
                secondsDiff = currentTime - GEO_IP_DB_FILE.stat().st_ctime
                if secondsDiff < DAY_SECONDS:
                    Logger.log("Skipping GeoLite2 database download, it was updated less than 24 hours ago.")
                    return

        Logger.log("Downloading GeoLite2 database...")
        async with this.getNewClient({"application/tar", "application/tar+gzip"}) as session:
            async with session.get(GEO_IP_URL, auth=BasicAuth(str(this.config.maxmind.accountId), this.config.maxmind.token, "utf-8")) as response:
                if response.status == 200:
                    tarArchiveRaw = BytesIO(await response.read())
                else:
                    Logger.error(f"GeoIP failed! Content type: {response.content_type}; Code: {response.status}")

        mmdb: bytes | None = None
        with tarfile.open(fileobj=tarArchiveRaw, mode="r:*") as tar:
            for member in tar:
                if member.isfile() and member.name.endswith("GeoLite2-City.mmdb"):
                    extracted = tar.extractfile(member)
                    if extracted:
                        mmdb = extracted.read()
                    break

        if not mmdb:
            Logger.error("Failed to find the database file in the TAR.")
            return

        with GEO_IP_DB_FILE.open("wb") as f:
            f.write(mmdb)

        this.maxMindDb = geoip2.database.Reader(GEO_IP_DB_FILE)
        Logger.success("Fresh GeoIP database fetched!")

    # WSS shit
    async def startRunning(this) -> None:
        this.API_SERVER_TASK = asyncio.create_task(this.API_SERVER.start())
        await this.start(this.config.token)

    async def stopRunning(this):
        await this.close()

    async def stop(this):
        await this.API_SERVER.stop()
        await this.stopRunning()
        await this.API_SERVER_TASK

    async def on_connect(this) -> None:
        await this.syncGeoIP()
        await this.loadCogs()
        await this.sync_commands()

    async def on_application_command_error(this, ctx: discord.Interaction, error: discord.DiscordException) -> bool:
        embed = await this.getFail(description="There was an error with the command's execution.", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return False

    async def on_command_error(this, ctx: bridge.BridgeContext, exception: errors.CommandError) -> bool:
        embed = await this.getFail(description="There was an error with the command's execution.")
        await ctx.respond(embed=embed, ephemeral=True)
        return False

    async def on_ready(this) -> None:
        this.errorChannel = await this.fetch_channel(this.config.packetLogs.errorChannelId)
        this.successChannel = await this.fetch_channel(this.config.packetLogs.successChannelId)

        await this.refreshCommands()
        Logger.success("Discord Bot is online!")

    # is_owner override
    async def is_owner(this, user: User) -> bool:
        return user.id == this.ownerId

    # Modules shit
    def getAvailableModules(this) -> list[str]:
        return [file.stem[3:] for file in MODULES_DIR.glob("mod*.py")]

    def getLoadedModules(this) -> list[str]:
        return this.loadedModules

    def getUnloadedModules(this) -> list[str]:
        return [module for module in this.getAvailableModules() if module not in this.loadedModules]

    async def unloadModules(this, modules: list[str]) -> None:
        for module in modules:
            if module not in this.getLoadedModules():
                raise ExtensionNotLoaded(f"Module {module} is not loaded")

            try:
                this.unload_extension(f"modules.mod{module}")
                this.loadedModules.remove(module)
            except (ExtensionNotFound, ExtensionNotLoaded) as e:
                Logger.error(f"Failed to unload module {module}: {e}")

        await this.sync_commands(force=True)
        await this.refreshCommands()
        Logger.success(f"Module {", ".join(modules)} unloaded!")

    async def loadModules(this, modules: list[str]) -> None:
        for module in modules:
            if module not in this.getUnloadedModules():
                raise ExtensionAlreadyLoaded(f"Module {module} is loaded")

            try:
                this.load_extension(f"modules.mod{module}")
                this.loadedModules.append(module)
            except (ExtensionNotFound, ExtensionAlreadyLoaded, NoEntryPointError, ExtensionFailed) as e:
                Logger.error(f"Failed to load module {module}: {e}")

        await this.sync_commands(force=True)
        await this.refreshCommands()
        Logger.success(f"Modules {", ".join(modules)} loaded!")

    async def reloadModules(this, modules: list[str]) -> None:
        for module in modules:
            if module not in this.getLoadedModules():
                raise ExtensionNotLoaded(f"Module {module} is not loaded")

            try:
                this.reload_extension(f"modules.mod{module}")
            except (ExtensionNotFound, ExtensionNotLoaded, NoEntryPointError, ExtensionFailed) as e:
                Logger.error(f"Failed to reload module {module}: {e}")

        await this.sync_commands(force=True)
        await this.refreshCommands()
        Logger.success(f"Module {", ".join(modules)} reloaded!")

    async def loadCogs(this) -> None:
        this.loadedModules.extend([ext.split(".")[1][3:] for module in this.getAvailableModules() for ext in this.load_extension(f"modules.mod{module}")])
        Logger.success(f"Modules {', '.join(this.loadedModules)} loaded!")

    async def refreshCommands(this):
        this.loadedCommands.clear()
        for cmd in this.walk_application_commands():
            if not isinstance(cmd, (SlashCommand, BridgeSlashCommand)):
                continue

            name: str = cmd.qualified_name
            description: str = cmd.description
            cooldown: float | None = None
            if cmd.cooldown:
                cooldown: float | None = cmd.cooldown.per
            checks: list = cmd.checks
            args: list[Option] = copy.deepcopy(cmd.options)

            if isinstance(cmd, BridgeSlashCommand):
                cmdHelpEntry = Command("tz!", name, description, cooldown, checks, args, f"`tz!{name}`")
            else:
                cmdHelpEntry = Command("/", name, description, cooldown, checks, args, cmd.mention)
            this.loadedCommands.append(cmdHelpEntry)

    # Persistent UI shit
    async def addOwner(this, userId: int) -> None:
        this.dialogOwners.add(userId)
        with DIALOG_OWNERS_FILE.open("w") as f:
            f.write(json.dumps(list(this.dialogOwners)))

    # Verification code invalidifier
    async def removeCode(this, delay: int, code: str) -> None:
        await asyncio.sleep(delay * 60)
        with contextlib.suppress(KeyError):
            this.linkCodes.pop(code)

    # Fun stuff
    async def on_message(this, message: discord.Message) -> None:
        await this.process_commands(message)
        if message.author.id == this.ownerId:
            # Canada
            if bool(SORRY_PATTERN.search(message.content)):
                await message.reply("🇨🇦", mention_author=False)
            # Romania
            elif bool(ROMANIA_PATTERN.search(message.content)):
                await message.reply("🇷🇴", mention_author=False)