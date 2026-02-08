import logging

import discord
from discord import app_commands
from discord.ext import commands

from dtypes import UInt64
from modules import TZBot
from shared import MAX_SHOWABLE_RESULTS, isOwner

log = logging.getLogger(__name__)

class ModuleManagement(commands.GroupCog, group_name="modules", group_description="Modules related stuff"):
    def __init__(this, client: TZBot) -> None:
        this.client = client

    async def getLoadedModules(this, ctx: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not this.client.isOwner(UInt64(ctx.user.id)): return []
        return [app_commands.Choice(name=module, value=module)
                for module in this.client.getLoadedModules()
                if module.lower().startswith(current.lower())][:MAX_SHOWABLE_RESULTS]

    async def getUnloadedModules(this, ctx: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not this.client.isOwner(UInt64(ctx.user.id)): return []
        return [app_commands.Choice(name=module, value=module)
                for module in this.client.getUnloadedModules()
                if module.lower().startswith(current.lower())][:MAX_SHOWABLE_RESULTS]

    async def getAllModules(this, ctx: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not this.client.isOwner(UInt64(ctx.user.id)): return []
        return [app_commands.Choice(name=module, value=module)
                for module in this.client.getAvailableModules()
                if module.lower().startswith(current.lower()) and \
                not this.client.modBlacklist.isBlacklisted(module)][:MAX_SHOWABLE_RESULTS]

    async def getBlacklistedModules(this, ctx: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not this.client.isOwner(UInt64(ctx.user.id)): return []
        return [app_commands.Choice(name=module, value=module)
                for module in this.client.getAvailableModules()
                if module.lower().startswith(current.lower()) and \
                this.client.modBlacklist.isBlacklisted(module)][:MAX_SHOWABLE_RESULTS]

    @app_commands.command(name="load", description="Loads a specific module.")
    @app_commands.autocomplete(modulename=getUnloadedModules)
    @app_commands.describe(modulename="The module you want to load")
    @app_commands.check(isOwner)
    async def loadModule(this, ctx: discord.Interaction, modulename: str) -> None:
        if modulename not in this.client.getUnloadedModules():
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            log.error(f"{ctx.user.name} tried to load {modulename}, which doesn't exist!")
            return

        try:
            await ctx.response.defer()
            await this.client.loadModules([modulename])
            log.info(f"{ctx.user.name} loaded {modulename}!")

            embed = await this.client.getSuccess(description=f"Module {modulename} loaded!", user=ctx.user)
            await ctx.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            log.fatal(f"Error occured: {e!s}")

    @app_commands.command(name="unload", description="Unloads a specific module.")
    @app_commands.autocomplete(modulename=getLoadedModules)
    @app_commands.describe(modulename="The module you want to unload")
    @app_commands.check(isOwner)
    async def unloadModule(this, ctx: discord.Interaction, modulename: str) -> None:
        if modulename not in this.client.getLoadedModules():
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            log.error(f"{ctx.user.name} tried to unload {modulename}, which doesn't exist!")
            return

        await ctx.response.defer()
        await this.client.unloadModules([modulename])
        log.info(f"{ctx.user.name} unloaded {modulename}!")

        embed = await this.client.getSuccess(description=f"Module {modulename} unloaded!", user=ctx.user)
        await ctx.followup.send(embed=embed, ephemeral=True)
        return

    @app_commands.command(name="reload", description="Reloads a specific module.")
    @app_commands.autocomplete(modulename=getLoadedModules)
    @app_commands.describe(modulename="The module you want to reload")
    @app_commands.check(isOwner)
    async def reloadModule(this, ctx: discord.Interaction, modulename: str) -> None:
        if modulename not in this.client.getLoadedModules():
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            log.error(f"{ctx.user.name} tried to reload {modulename}, which doesn't exist!")
            return

        await ctx.response.defer()
        await this.client.reloadModules([modulename])
        log.info(f"{ctx.user.name} reloaded {modulename}!")

        embed = await this.client.getSuccess(description=f"Module {modulename} reloaded!", user=ctx.user)
        await ctx.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="blacklist", description="Blacklists a module.")
    @app_commands.autocomplete(modulename=getAllModules)
    @app_commands.describe(modulename="The module you want to reload")
    @app_commands.check(isOwner)
    async def blacklistModule(this, ctx: discord.Interaction, modulename: str) -> None:
        if modulename not in [mod for mod in this.client.getAvailableModules() if not this.client.modBlacklist.isBlacklisted(mod)]:
            log.error(f"{ctx.user.name} tried to blacklist {modulename}, which either doesn't exist or is already blacklisted!")
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist or is already blacklisted!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)

        this.client.modBlacklist.add(modulename)
        embed = await this.client.getSuccess(description=f"Module {modulename} blacklisted!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unblacklist", description="Unblacklists a module.")
    @app_commands.autocomplete(modulename=getBlacklistedModules)
    @app_commands.describe(modulename="The module you want to reload")
    @app_commands.check(isOwner)
    async def unblacklistModule(this, ctx: discord.Interaction, modulename: str) -> None:
        if modulename not in [mod for mod in this.client.getAvailableModules() if this.client.modBlacklist.isBlacklisted(mod)]:
            log.error(f"{ctx.user.name} tried to blacklist {modulename}, which either doesn't exist or is already blacklisted!")
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist or is already blacklisted!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        this.client.modBlacklist.remove(modulename)
        embed = await this.client.getSuccess(description=f"Module {modulename} unblacklisted!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)


async def setup(client: TZBot) -> None:
    try:
        await client.add_cog(ModuleManagement(client))
    except Exception as e:
        log.fatal(f"Failed to load {client.__class__.__name__}. {e}")
