import discord
from discord.ext import commands

from database.stats.StatsDatabase import collectCommandStats
from modules.TZBot import TZBot
from shared.Helpers import Helpers
from shell.Logger import Logger


class ModuleManagement(commands.Cog):
    modulesGroup = discord.SlashCommandGroup(name="modules", description="Modules related stuff", checks=[commands.is_owner()])

    def __init__(this, client: TZBot) -> None:
        this.client = client

    async def getLoadedModules(this, ctx: discord.AutocompleteContext) -> list[str]:
        if not await this.client.is_owner(ctx.interaction.user): return []
        return [module for module in this.client.getLoadedModules() if module.lower().startswith(ctx.value.lower())]

    async def getUnloadedModules(this, ctx: discord.AutocompleteContext) -> list[str]:
        if not this.client.is_owner(ctx.interaction.user): return []
        return [module for module in this.client.getUnloadedModules() if module.lower().startswith(ctx.value.lower())]

    @modulesGroup.command(name="load", description="Loads a specific module.")
    @commands.is_owner()
    @collectCommandStats
    async def loadModule(
        this, ctx: discord.ApplicationContext, modulename: discord.Option(str, "The module you want to load", autocomplete=getUnloadedModules)
    ) -> bool:
        if modulename not in this.client.getUnloadedModules():
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to load {modulename}, which doesn't exist!")
            return False

        await this.client.loadModules([modulename])
        Logger.success(f"{ctx.user.name} loaded {modulename}!")

        embed = await this.client.getSuccess(description=f"Module {modulename} loaded!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return True

    @modulesGroup.command(name="unload", description="Unloads a specific module.")
    @commands.is_owner()
    @collectCommandStats
    async def unloadModule(
        this, ctx: discord.ApplicationContext, modulename: discord.Option(str, "The module you want to unload", autocomplete=getLoadedModules)
    ) -> bool:
        if modulename not in this.client.getLoadedModules():
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to unload {modulename}, which doesn't exist!")
            return False

        await this.client.unloadModules([modulename])
        Logger.success(f"{ctx.user.name} unloaded {modulename}!")

        embed = await this.client.getSuccess(description=f"Module {modulename} unloaded!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return True

    @modulesGroup.command(name="reload", description="Reloads a specific module.")
    @commands.is_owner()
    @collectCommandStats
    async def reloadModule(
        this, ctx: discord.ApplicationContext, modulename: discord.Option(str, "The module you want to reload", autocomplete=getLoadedModules)
    ) -> bool:
        if modulename not in this.client.getLoadedModules():
            embed = await this.client.getFail(description=f"Module {modulename} doesn't exist!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to reload {modulename}, which doesn't exist!")
            return False

        await this.client.reloadModules([modulename])
        Logger.success(f"{ctx.user.name} reloaded {modulename}!")

        embed = await this.client.getSuccess(description=f"Module {modulename} reloaded!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return True


def setup(client: TZBot) -> None:
    client.add_cog(ModuleManagement(client))
