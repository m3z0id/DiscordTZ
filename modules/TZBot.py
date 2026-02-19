import asyncio
import contextlib
import copy
import datetime
import logging
import tarfile
import time
from copy import deepcopy
from typing import Final, Optional
from uuid import UUID

import aiohttp
import discord
import geoip2
import maxminddb.errors
from aiohttp import BasicAuth, ClientResponseError
from discord import User
from discord.ext import commands
from discord.ext.commands import ExtensionNotLoaded, ExtensionNotFound, ExtensionAlreadyLoaded, \
    NoEntryPointError, ExtensionFailed, Context, errors
from discord.ext.commands._types import BotT
from geoip2 import database  # noqa: F401
from six import BytesIO

from database import APIKeyDatabase, DataDatabase
from dtypes import Config, Command, UInt64, ModuleBlacklist
from server.APIServer import APIServer
from server.ServerLogger import ServerLogger
from shared import CONFIG_FILE, GEO_IP_DB_FILE, SUCCESS, FAIL, HTTP_HEADERS, DAY_SECONDS, \
    GEO_IP_URL, MODULES_DIR, SORRY_PATTERN, ROMANIA_PATTERN, MOD_BLACKLIST_FILE

log = logging.getLogger(__name__)

class TZBot(commands.Bot):
    loadedModules: list[str] = []
    loadedCommands: list[Command] = []

    API_SERVER_TASK: asyncio.Task
    API_SERVER: Final[APIServer]
    API_PACKET_LOGGER: Final[ServerLogger]

    syncOverride: bool = False

    def __init__(this, **kwargs) -> None:
        super().__init__(**kwargs)

        with CONFIG_FILE.open("r") as f:
            this.config: Config = Config.schema().loads(f.read())

        this.ownerId = this.config.ownerId
        this.linkCodes: dict[str, tuple[UUID, str]] = {}
        this.db: DataDatabase = DataDatabase(this.config.mariadbDetails)
        this.apiDb = APIKeyDatabase()
        this.modBlacklist = ModuleBlacklist(MOD_BLACKLIST_FILE)

        GEO_IP_DB_FILE.parent.mkdir(exist_ok=True, parents=True)
        GEO_IP_DB_FILE.touch(exist_ok=True)

        try:
            this.maxMindDb: geoip2.database.Reader = geoip2.database.Reader(GEO_IP_DB_FILE)
        except maxminddb.errors.InvalidDatabaseError:
            log.error("MaxMind DB is invalid, will fetch")
            this.syncOverride = True

        this.API_PACKET_LOGGER = ServerLogger(this, True)
        this.API_SERVER = APIServer(this)

    # Command Response
    async def getSuccess(this, *, description: Optional[str] = None, user: Optional[discord.User] = None) -> discord.Embed:
        successCpy = copy.deepcopy(SUCCESS)
        successCpy.timestamp = datetime.datetime.now()
        if user:
            successCpy.set_footer(text=user.name, icon_url=user.avatar.url)
        if description:
            successCpy.description = description

        return successCpy

    async def getFail(this, *, description: Optional[str] = None, user: Optional[discord.User] = None) -> discord.Embed:
        failCpy = copy.deepcopy(FAIL)
        failCpy.timestamp = datetime.datetime.now()
        if user:
            failCpy.set_footer(text=user.name, icon_url=user.avatar.url)
        if description:
            failCpy.description = description

        return failCpy

    # Internet shit
    async def downloadFile(this, url: str, contentTypes: set[str]) -> Optional[tuple[str, bytes]]:
        log.info(f"Downloading from {url}")
        headersCpy = deepcopy(HTTP_HEADERS)
        headersCpy["Accept"] = ",".join(contentTypes)

        try:
            async with aiohttp.ClientSession(headers=headersCpy) as session:
                async with session.get(url) as response:
                    if response.status == 200 and response.content_type in contentTypes:
                        log.info("Download was successful!")
                        return response.content_type, await response.read()

                    else:
                        log.error(f"Download failed! Content type: {response.content_type}; Code: {response.status}")
                        return None

        except ClientResponseError as e:
            log.error(f"Download failed!: {e!s}")

    async def syncGeoIP(this):
        if not this.syncOverride:
            if GEO_IP_DB_FILE.is_file():
                currentTime = time.time()
                secondsDiff = currentTime - GEO_IP_DB_FILE.stat().st_ctime
                if secondsDiff < DAY_SECONDS:
                    log.info("Skipping GeoLite2 database download, it was updated less than 24 hours ago.")
                    return

        log.info("Downloading GeoLite2 database...")
        headers = copy.deepcopy(HTTP_HEADERS)
        headers["Accept"] = ",".join({"application/tar", "application/tar+gzip"})
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(GEO_IP_URL, auth=BasicAuth(str(this.config.maxmind.accountId), this.config.maxmind.token, "utf-8")) as response:
                if response.status == 200:
                    tarArchiveRaw = BytesIO(await response.read())
                else:
                    log.error(f"GeoIP failed! Content type: {response.content_type}; Code: {response.status}; {await response.read()}")
                    return

        mmdb: Optional[bytes] = None
        with tarfile.open(fileobj=tarArchiveRaw, mode="r:*") as tar:
            for member in tar:
                if member.isfile() and member.name.endswith("GeoLite2-City.mmdb"):
                    extracted = tar.extractfile(member)
                    if extracted:
                        mmdb = extracted.read()
                    break

        if not mmdb:
            log.error("Failed to find the database file in the TAR.")
            return

        with GEO_IP_DB_FILE.open("wb") as f:
            f.write(mmdb)

        this.maxMindDb = geoip2.database.Reader(GEO_IP_DB_FILE)
        log.info("Fresh GeoIP database fetched!")

    # WSS shit
    async def startRunning(this, *, apiOnly: bool = False) -> None:
        if apiOnly:
            await this.API_PACKET_LOGGER.setLoggingEnabled(False)
            await this.API_SERVER.start()
            log.warning("Running in API-only mode!")
        else:
            this.API_SERVER_TASK = asyncio.create_task(this.API_SERVER.start())
            await this.start(this.config.token)

    async def on_ready(this) -> None:
        await this.syncGeoIP()
        await this.loadCogs()
        await this.db.asyncInit()
        await this.apiDb.asyncInit()

        actr = await this.fetch_guild(148831815984087041)
        this.errorChannel = await this.fetch_channel(this.config.packetLogs.errorChannelId())
        this.successChannel = await this.fetch_channel(this.config.packetLogs.successChannelId())
        this.devlogRole = await actr.fetch_role(this.config.server.devlogRoleId())
        this.apiThread = await actr.fetch_channel(this.config.server.apiApproveChannelId())

        await this.tree.sync()
        log.info("Discord Bot is online!")

    async def on_command_error(this, ctx: Context[BotT], exception: errors.CommandError, /) -> None:
        if isinstance(exception, commands.CommandNotFound):
            log.warning(f"{ctx.author.name} tried to run a command which doesn't exist!")
            await ctx.reply(embed=await this.getFail(description="This command doesn't exist!", user=ctx.author))

        elif isinstance(exception, commands.MissingPermissions):
            log.warning(f"{ctx.author.name} tried to run a command without sufficient permissions! Missing perms: {", ".join(exception.missing_permissions)}")
            await ctx.reply(embed=await this.getFail(description="You don't have sufficient permissions!", user=ctx.author))

        elif isinstance(exception, commands.CommandOnCooldown):
            log.warning(f"{ctx.author.name} tried to run a command too fast!")
            await ctx.reply(embed=await this.getFail(description=f"Slow down! Try again in {exception.retry_after:.2f}s.", user=ctx.author))

        elif isinstance(exception, commands.MissingRequiredArgument):
            log.warning(f"{ctx.author.name} tried to run a command which requires arguments!")
            await ctx.reply(embed=await this.getFail(description="I think you forgot some arguments to this command!", user=ctx.author))

        else:
            log.error(f"Unhandled error type: {exception.__class__.__name__}")
            await ctx.send("An unexpected error occurred.")

    # is_owner override
    def isOwner(this, userId: UInt64) -> bool:
        return userId == this.ownerId

    async def is_owner(this, user: User) -> bool:
        return this.isOwner(UInt64(user.id))

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
                await this.unload_extension(f"modules.mod{module}")
                this.loadedModules.remove(module)
            except (ExtensionNotFound, ExtensionNotLoaded) as e:
                log.error(f"Failed to unload module {module}: {e!s}")

        await this.tree.sync()
        log.info(f"Module {", ".join(modules)} unloaded!")

    async def loadModules(this, modules: list[str]) -> None:
        for module in modules:
            if module not in this.getUnloadedModules():
                raise ExtensionAlreadyLoaded(f"Module {module} is loaded")

            try:
                await this.load_extension(f"modules.mod{module}")
                this.loadedModules.append(module)
            except (ExtensionNotFound, ExtensionAlreadyLoaded, NoEntryPointError, ExtensionFailed) as e:
                log.error(f"Failed to load module {module}: {e!s}")

        await this.tree.sync()
        log.info(f"Modules {", ".join(modules)} loaded!")

    async def reloadModules(this, modules: list[str]) -> None:
        for module in modules:
            if module not in this.getLoadedModules():
                raise ExtensionNotLoaded(f"Module {module} is not loaded")

            try:
                await this.reload_extension(f"modules.mod{module}")
            except (ExtensionNotFound, ExtensionNotLoaded, NoEntryPointError, ExtensionFailed) as e:
                log.error(f"Failed to reload module {module}: {e!s}")

        await this.tree.sync()
        log.info(f"Module {", ".join(modules)} reloaded!")

    async def loadCogs(this) -> None:
        this.loadedModules.extend(this.getAvailableModules())
        for module in this.getAvailableModules():
            if this.modBlacklist.isBlacklisted(module):
                log.info(f"Module {module} is blacklisted, skipping!")
                this.loadedModules.remove(module)
                continue

            await this.load_extension(f"modules.mod{module}")

        log.info(f"Modules {', '.join(this.loadedModules)} loaded!")


    # Verification code invalidifier
    async def removeCode(this, delay: int, code: str) -> None:
        await asyncio.sleep(delay * 60)
        with contextlib.suppress(KeyError):
            this.linkCodes.pop(code)

    # Fun stuff
    async def on_message(this, message: discord.Message) -> None:
        await this.process_commands(message)
        if message.author.id == this.ownerId():
            # Canada
            if bool(SORRY_PATTERN.search(message.content)):
                await message.reply("🇨🇦", mention_author=False)
            # Romania
            elif bool(ROMANIA_PATTERN.search(message.content)):
                await message.reply("🇷🇴", mention_author=False)