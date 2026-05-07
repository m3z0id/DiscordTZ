import logging
from uuid import UUID

import discord
from discord import app_commands
from discord.ext import commands

from dtypes import UInt64
from modules import TZBot
from shared import VERIFY_CODE_LEN

log = logging.getLogger(__name__)

class TzLink(commands.Cog):
    def __init__(this, client: TZBot) -> None:
        this.client = client

    @app_commands.command(name="link", description="Links you to your Minecraft account.")
    @app_commands.describe(code="Code that was generated for you in Minecraft.")
    async def link(this, ctx: discord.Interaction, code: app_commands.Range[str, VERIFY_CODE_LEN, VERIFY_CODE_LEN]) -> None:
        if code not in this.client.linkCodes:
            log.warning(f"{ctx.user.name} tried to link themselves with an invalid code!")
            embed = await this.client.getFail(description="There's no such code! Maybe it expired?", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return
        
        testId = UInt64(0)
        if testUuid := await this.client.db.getUUIDFromUserId(UInt64(ctx.user.id)):
            testId = await this.client.db.getUserIdFromUUID(testUuid)

        if testUuid and testId() == ctx.user.id:
            log.warning(f"{ctx.user.name} is already linked to {str(testUuid)}!")
            embed = await this.client.getFail(description="Your account is already linked!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        entry: tuple[UUID, str] = this.client.linkCodes.pop(code)
        await this.client.db.assignUUIDToUserId(entry[0], UInt64(ctx.user.id), entry[1])

        embed = await this.client.getSuccess(description=f"Your Discord account has been successfully linked with `{entry[0]}`!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unlink", description="Unlinks your Minecraft account.")
    async def unlink(this, ctx: discord.Interaction) -> None:
        testId = UInt64(0)
        if testUuid := await this.client.db.getUUIDFromUserId(UInt64(ctx.user.id)):
            testId = await this.client.db.getUserIdFromUUID(testUuid)

        if not testUuid or testId() != ctx.user.id:
            log.warning(f"{ctx.user.name} isn't linked to any account!")
            embed = await this.client.getFail(description="There's nothing to unlink!", user=ctx.user)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        embed = await this.client.getSuccess(description="Your Discord account has been successfully unlinked!", user=ctx.user)
        await ctx.response.send_message(embed=embed, ephemeral=True)

        await this.client.db.unassignUUIDFromUserId(UInt64(ctx.user.id))


async def setup(client: TZBot) -> None:
    await client.add_cog(TzLink(client))
