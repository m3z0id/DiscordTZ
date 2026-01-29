import discord
from discord.ext import commands

from database.stats.StatsDatabase import collectCommandStats
from modules.TZBot import TZBot
from shared import Types
from shared.Helpers import Helpers


class TzLink(commands.Cog):
    def __init__(this, client: TZBot) -> None:
        this.client = client

    @discord.slash_command(name="link", description="Links you to your Minecraft account.")
    @collectCommandStats
    async def link(this, ctx: discord.ApplicationContext, code: discord.Option(str, "Code that was generated for you in Minecraft.")) -> bool:
        if code not in this.client.linkCodes:
            embed = await this.client.getFail(description="There's no such code! Maybe it expired?", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return False

        testUuid = await this.client.db.getUUIDByUserId(ctx.user.id)
        
        testId = None
        if testUuid and Types.isUUID(testUuid):
            testId = await this.client.db.getUserIdByUUID(testUuid)

        if testUuid and testId and int(testId) == ctx.user.id:
            embed = await this.client.getFail(description="Your account is already linked!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return False

        entry: tuple[str, str] = this.client.linkCodes.pop(code)
        embed = await this.client.getSuccess(description=f"Your Discord account has been successfully linked with `{entry[0]}`!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)

        await this.client.db.assignUUIDToUserId(entry[0], ctx.user.id, entry[1])
        return True

    @discord.slash_command(name="unlink", description="Unlinks your Minecraft account.")
    @collectCommandStats
    async def unlink(this, ctx: discord.ApplicationContext) -> bool:
        testUuid = await this.client.db.getUUIDByUserId(ctx.user.id)

        testId = None
        if testUuid and Types.isUUID(testUuid):
            testId = await this.client.db.getUserIdByUUID(testUuid)

        if not (testUuid and testId) or int(testId) != ctx.user.id:
            embed = await this.client.getFail(description="There's nothing to unlink!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return False

        embed = await this.client.getSuccess(description="Your Discord account has been successfully unlinked!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)

        await this.client.db.unassignUUIDFromUserId(ctx.user.id)
        return True


def setup(client: TZBot) -> None:
    client.add_cog(TzLink(client))
