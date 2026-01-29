import datetime

import discord

from modules.TZBot import TZBot
from server.APIKey import ApiKey
from shell.Logger import Logger


class RejectionExplanationModal(discord.ui.Modal):
    explanation: str | None = None

    def __init__(this, *children: discord.InputText, custom_id: str | None = None, timeout: float | None = None) -> None:
        super().__init__(*children, title="Explain the rejection.", custom_id=custom_id, timeout=timeout)
        this.rejectionBox = discord.ui.InputText(
            label="Rejection Reason", placeholder="This is so trash because...", style=discord.InputTextStyle.paragraph, required=True
        )

        this.add_item(this.rejectionBox)

    async def callback(this, ctx: discord.Interaction) -> None:
        this.explanation = this.children[0].value
        await ctx.response.send_message("Rejection explanation recorded!", ephemeral=True)


class DecisionActionRow(discord.ui.View):
    def __init__(this, client: TZBot) -> None:
        super().__init__(timeout=None)
        this.client = client

    @discord.ui.button(label="Accept!", style=discord.ButtonStyle.green, custom_id="ACCEPT")
    async def acceptHandler(this, button: discord.ui.Button, ctx: discord.Interaction) -> None:
        if ctx.user.id != this.client.ownerId:
            await ctx.response.send_message("You can't do that! You aren't my owner!", ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to reject a request!")
            return

        dbKeyForm = await this.client.apiDb.getRequestByMsgId(ctx.message.id)
        key = ApiKey.fromDbForm(dbKeyForm)
        keyOwner: discord.User = await ctx.client.fetch_user(key.owner)

        acceptBtn = this.get_item("ACCEPT")
        rejectBtn = this.get_item("REJECT")

        devlogRole: discord.Role = await ctx.guild._fetch_role(this.client.config.server.devlogRoleId)
        if devlogRole is None:
            Logger.error("Devlog role not found!")

        if button.custom_id == "ACCEPT":
            embed = discord.Embed(
                color=discord.Color.green(),
                title="**Accepted**!",
                description=f"Congratulations {keyOwner.mention}! Your request has been accepted.",
                timestamp=datetime.datetime.now(),
            )

            embed.add_field(name="**API Key** (save and don't share!)", value=f"```{dbKeyForm}```", inline=False)
            embed.add_field(name="**Permissions**", value=f"```{', '.join(key.prettyPrintPerms())}```", inline=False)

            await keyOwner.send(keyOwner.mention, embed=embed)

            await this.client.apiDb.moveToReal(dbKeyForm)
            acceptBtn.disabled = True
            rejectBtn.disabled = True
            thisEmbed = ctx.message.embeds[0]
            thisEmbed.colour = discord.Color.green()
            thisEmbed.title = "**API Key Approved**"

            await ctx.guild.get_member(key.owner).add_roles(devlogRole)

            await ctx.message.edit(view=this, embed=thisEmbed)
            await ctx.response.send_message("Approved!", ephemeral=True)
        else:
            await ctx.response.send_message("You can't do that!", ephemeral=True)

    @discord.ui.button(label="Reject!", style=discord.ButtonStyle.red, custom_id="REJECT")
    async def rejectHandler(this, button: discord.ui.Button, ctx: discord.Interaction) -> None:
        if ctx.user.id != this.client.ownerId:
            await ctx.response.send_message("You can't do that! You aren't my owner!", ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to reject a request!")
            return

        dbKeyForm = await this.client.apiDb.getRequestByMsgId(ctx.message.id)
        key = ApiKey.fromDbForm(dbKeyForm)
        keyOwner: discord.User = await ctx.client.fetch_user(key.owner)

        acceptBtn = this.get_item("ACCEPT")
        rejectBtn = this.get_item("REJECT")

        if button.custom_id == "REJECT":
            explanation = RejectionExplanationModal()
            await ctx.response.send_modal(explanation)
            await explanation.wait()

            embed = discord.Embed(
                color=discord.Color.red(),
                title="**Rejected**",
                description=f"{keyOwner.mention}, your request has been rejected.",
            )
            embed.add_field(name="**Reason**", value=f"```{explanation.explanation}```")
            await keyOwner.send(keyOwner.mention, embed=embed)
            await this.client.apiDb.flushRequest(dbKeyForm)

            acceptBtn.disabled = True
            rejectBtn.disabled = True

            thisEmbed = ctx.message.embeds[0]
            thisEmbed.colour = discord.Color.red()
            thisEmbed.title = "**API Key Rejected**"
            thisEmbed.add_field(name="**Rejection Reason**", value=f"```{explanation.explanation}```")

            await ctx.message.edit(view=this, embed=thisEmbed)
        else:
            await ctx.response.send_message("You can't do that!", ephemeral=True)
