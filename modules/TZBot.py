import asyncio
import contextlib
import copy
import datetime
import logging
from typing import Final, Optional, cast
from uuid import UUID

import discord
from discord import User
from discord.ext import commands
from discord.ext.commands import ExtensionNotLoaded, ExtensionNotFound, ExtensionAlreadyLoaded, \
    NoEntryPointError, ExtensionFailed, Context, errors
from discord.ext.commands._types import BotT
from geoip2 import database  # noqa: F401

from database import APIKeyDatabase, DataDatabase
from dtypes import Config, Command, UInt64, ModuleBlacklist
from modules.modHelp import Help
from server.APIServer import APIServer
from server.ServerLogger import ServerLogger
from shared import CONFIG_FILE, GEO_IP_DB_FILE, SUCCESS, FAIL, MODULES_DIR, SORRY_PATTERN, \
    ROMANIA_PATTERN, MOD_BLACKLIST_FILE, GeoIP
from shared.NetClient import NetClient

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
        this.netClient = NetClient()

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

    # WSS shit
    async def startRunning(this, *, apiOnly: bool = False) -> None:
        this.geoIP = await GeoIP.create(this, GEO_IP_DB_FILE)
        if apiOnly:
            await this.API_PACKET_LOGGER.setLoggingEnabled(False)
            await this.API_SERVER.start()
            log.warning("Running in API-only mode!")
        else:
            this.API_SERVER_TASK = asyncio.create_task(this.API_SERVER.start())
            await this.start(this.config.token)

    async def on_ready(this) -> None:
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

        elif isinstance(exception, commands.BadLiteralArgument):
            log.warning(f"{ctx.author.name} tried to run a command with an invalid literal argument!")
            await ctx.reply(embed=await this.getFail(description="One of the arguments you provided is invalid!", user=ctx.author))

        else:
            log.error(f"Unhandled error type: {exception.__class__.__name__}")
            log.error(f"{exception.__dict__}")
            await ctx.send("An unexpected error occurred.")

    # is_owner override
    def isOwner(this, userId: UInt64) -> bool:
        return userId == this.ownerId

    async def is_owner(this, user: User) -> bool:
        return this.isOwner(UInt64(user.id))

    # Modules shit
    def getAvailableModules(this, *, exemptBlacklisted: bool = False) -> list[str]:
        modules = [file.stem[3:] for file in MODULES_DIR.glob("mod*.py")]
        if exemptBlacklisted:
            return [module for module in modules if not this.modBlacklist.isBlacklisted(module)]

        return modules

    def getLoadedModules(this) -> list[str]:
        return this.loadedModules

    def getUnloadedModules(this) -> list[str]:
        return [module for module in this.getAvailableModules() if module not in this.loadedModules]

    async def _refreshHelp(this) -> None:
        this.helpCog = cast(Help, this.get_cog("Help"))
        await this.helpCog.refreshCommandList()

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
        await this._refreshHelp()

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
        await this._refreshHelp()

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
        await this._refreshHelp()

    async def loadCogs(this) -> None:
        availableModules = this.getAvailableModules(exemptBlacklisted=True)
        await this.loadModules(availableModules)


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