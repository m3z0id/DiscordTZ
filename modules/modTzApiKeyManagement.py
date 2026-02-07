import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from dtypes import Disablable, UInt64
from modules import TZBot
from server.APIKey import APIPermissions, APIKey

log = logging.getLogger(__name__)

class TZUI(discord.ui.LayoutView):
    client: TZBot
    ownerId: UInt64

    def __init__(this, client: TZBot, ownerId: UInt64, timeout: Optional[float] = None) -> None:
        this.client = client
        this.ownerId = ownerId
        super().__init__(timeout=timeout)

    async def disable(this, ctx: Optional[discord.Interaction] = None) -> None:
        for child in this.walk_children():
            if isinstance(child, Disablable):
                child._underlying.disabled = True
        this.stop()

        if ctx:
            await ctx.message.edit(view=this)

    def checkIfOwner(this, receivedId: UInt64) -> bool:
        return this.ownerId == receivedId

class RejectionExplanationModal(discord.ui.Modal):
    explanation: Optional[str] = None
    rejectionBox = discord.ui.TextInput(label="Rejection Reason", placeholder="This is so trash because...", style=discord.TextStyle.paragraph, required=True)
    def __init__(this) -> None:
        super().__init__(title="Explain the rejection.", timeout=0)
        this.add_item(this.rejectionBox)

    async def callback(this, ctx: discord.Interaction) -> None:
        this.explanation = this.rejectionBox.value
        await ctx.response.send_message("Rejection explanation recorded!", ephemeral=True)


class DecisionActionRow(discord.ui.View):
    def __init__(this, client: TZBot) -> None:
        super().__init__(timeout=None)
        this.client = client
        this.ownerId = client.ownerId

        async def buttonHandler(ctx: discord.Interaction) -> None:
            if not this.checkIfOwner(UInt64(ctx.user.id)):
                await ctx.response.send_message("You can't do that! You aren't my owner!", ephemeral=True)
                log.error(f"{ctx.user.name} tried to reject a request!")
                return

            jwt = await this.client.apiDb.getPendingKeyByMsgId(UInt64(ctx.message.id))
            key = APIKey.fromJWT(jwt, this.client.config.server.apiKeysKey)
            try:
                keyOwner: discord.User = await ctx.client.fetch_user(key.owner)
            except discord.errors.NotFound:
                log.error(f"User with ID {key.owner} not found!")
                fail = await this.client.getFail(description=f"User with ID {key.owner} not found.", user=ctx.user)
                await ctx.response.send_message(embed=fail, ephemeral=True)
                return

            match ctx.data.get("custom_id", None):
                case "ACCEPT":
                    await this.disable()
                    embed = discord.Embed(
                        color=discord.Color.green(),
                        title="**Accepted**!",
                        description=f"Congratulations {keyOwner.mention}! Your request has been accepted.",
                        timestamp=datetime.now(),
                    )

                    embed.add_field(name="**API Key** (save and don't share!)", value=f"```{jwt}```", inline=False)
                    embed.add_field(name="**Permissions**", value=f"```{', '.join(key.prettyPrintPerms())}```",
                                    inline=False)

                    await keyOwner.send(keyOwner.mention, embed=embed)

                    await this.client.apiDb.makeKeyValid(jwt)
                    thisEmbed = ctx.message.embeds[0]
                    thisEmbed.colour = discord.Color.green()
                    thisEmbed.title = "**API Key Approved**"

                    if this.client.devlogRole:
                        await ctx.guild.get_member(key.owner).add_roles(this.client.devlogRole)
                    else:
                        log.warning("Not assigning devlog role since it can't be found!")

                    await ctx.message.edit(view=this, embed=thisEmbed)
                    await ctx.response.send_message("Approved!", ephemeral=True)

                case "REJECT":
                    await this.disable()
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
                    await this.client.apiDb.denyKey(jwt)

                    thisEmbed = ctx.message.embeds[0]
                    thisEmbed.colour = discord.Color.red()
                    thisEmbed.title = "**API Key Rejected**"
                    thisEmbed.add_field(name="**Rejection Reason**", value=f"```{explanation.explanation}```")

                    await ctx.message.edit(view=this, embed=thisEmbed)

                case None:
                    log.error("No custom id found! DecisionActionRow#buttonCallback")

        acceptBtn = discord.ui.Button(label="Accept!", style=discord.ButtonStyle.green, custom_id="ACCEPT")
        rejectBtn = discord.ui.Button(label="Reject!", style=discord.ButtonStyle.red, custom_id="REJECT")

        acceptBtn.callback = buttonHandler
        rejectBtn.callback = buttonHandler

        this.add_item(acceptBtn)
        this.add_item(rejectBtn)

    async def disable(this, ctx: Optional[discord.Interaction] = None) -> None:
        for child in this.walk_children():
            if isinstance(child, Disablable):
                child._underlying.disabled = True
        this.stop()

        if ctx:
            await ctx.message.edit(view=this)

    def checkIfOwner(this, receivedId: UInt64) -> bool:
        return this.ownerId == receivedId

class TzApiExplanationModal(discord.ui.Modal):
    appName: str = ""
    appInfo: str = ""
    apiUsage: str = ""

    def __init__(this) -> None:
        super().__init__(title="Info about your API usage.", custom_id="TZMODAL", timeout=None)
        this.appNameBox = discord.ui.TextInput(
            label="Application Name",
            placeholder="My Super Cool App",
            style=discord.TextStyle.short,
            required=True,
            custom_id="APPNAME"
        )
        this.appInfoBox = discord.ui.TextInput(
            label="Application Info",
            placeholder="My Application will be used for...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            custom_id="APPINFO"
        )
        this.apiUsageBox = discord.ui.TextInput(
            label="Your API Usage",
            placeholder="I will use Timezone bot API for...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            custom_id="APIUSAGE"
        )

        this.add_item(this.appNameBox)
        this.add_item(this.appInfoBox)
        this.add_item(this.apiUsageBox)

    async def on_submit(this, ctx: discord.Interaction) -> None:
        for child in this.children:
            if isinstance(child, discord.ui.TextInput):
                match child.custom_id:
                    case this.appNameBox.custom_id: this.appName = child.value
                    case this.appInfoBox.custom_id: this.appInfo = child.value
                    case this.apiUsageBox.custom_id: this.apiUsage = child.value

        await ctx.response.send_message("Answers recorded!", ephemeral=True)

class TZAPIRequestUI(TZUI):
    modal = TzApiExplanationModal()
    perms: UInt64 = UInt64(0)
    duration: str = "INFINITE"

    async def buttonCallback(this, ctx: discord.Interaction) -> None:
        if not this.checkIfOwner(UInt64(ctx.user.id)):
            await ctx.response.send_message("This is not your UI!")
            log.log(f"{ctx.user.name} tried to mess with {(await ctx.client.fetch_user(this.ownerId())).name}'s UI.")
            return

        match ctx.data.get("custom_id", None):
            case "CANCEL":
                await this.disable()
                await ctx.message.edit(view=this)
                await ctx.response.send_message("Cancelling!", ephemeral=True)
            case "SUBMIT":
                await ctx.response.send_modal(this.modal)
                await this.modal.wait()

                newApiKey: APIKey = APIKey(UInt64(ctx.user.id), this.perms, "INFINITE")
                dbForm: str = newApiKey.toJWT(this.client.config.server.apiKeysKey)

                await this.disable()
                await ctx.message.edit(view=this)

                embed: discord.Embed = discord.Embed(
                    color=discord.Color.darker_grey(),
                    title=f"**API Key Request for {this.modal.appName}**",
                    description=f"**ID**: {newApiKey.keyId}\n**Requested by**: {ctx.user.name}\n**Duration**: {newApiKey.validUntil}",
                )

                embed.add_field(name="**Permissions**",
                                value=f"```{', '.join(newApiKey.prettyPrintPerms())} ({newApiKey.permissions})```",
                                inline=False)
                embed.add_field(name="**App Info**", value=f"```{this.modal.appInfo}```", inline=False)
                embed.add_field(name="**Intended API Usage**", value=f"```{this.modal.apiUsage}```", inline=False)
                embed.set_thumbnail(url=ctx.user.avatar.url)
                embed.set_author(name=ctx.user.name, icon_url=ctx.user.avatar.url)
                embed.set_footer(text=f"Requested by {ctx.user.name}", icon_url=ctx.user.avatar.url)
                embed.timestamp = datetime.now()

                msg = await this.client.apiThread.send(embed=embed, view=DecisionActionRow(this.client))

                await this.client.apiDb.addKeyToPending(dbForm, UInt64(msg.id))
            case None:
                log.error("No custom id found! TZAPIRequestUI#buttonCallback")

    def __init__(this, client: TZBot, user: UInt64) -> None:
        super().__init__(client, user)

        container = discord.ui.Container()
        title = discord.ui.TextDisplay("# TZBot API Key Request Form")
        separator = discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)

        tosTitle = discord.ui.TextDisplay("## Terms of Service")
        tosDesc = discord.ui.TextDisplay("\n".join([
            "By using this service, you agree not to abuse request limits or functionality. Any form of request abuse or misuse will result in a permanent ban from accessing the service.",
            "API usage must remain within intended limits; API abuse is strictly prohibited.",
            "API keys may be revoked at any time without prior notice or explanation.",
            "I reserve the right to modify, suspend, or terminate service access at our sole discretion.",
            "You will receive necessary notifications regarding significant updates, changes, or policy modifications.",
            "Continued use of the service constitutes acceptance of the most recent TOS.",
            "Violations may result in immediate suspension or termination of access.",
            "By clicking \"Submit!\", I agree to these Terms of Service."
        ]))

        detailsTitle = discord.ui.TextDisplay("## Details")
        detailsInfo = discord.ui.TextDisplay("We need some details about your app and its usage to approve it. Fill the options below.")

        async def selectCallback(ctx: discord.Interaction) -> None:
            if not this.checkIfOwner(UInt64(ctx.user.id)):
                await ctx.response.send_message("This is not your UI!")
                log.info(f"{ctx.user.name} tried to mess with {(await this.client.fetch_user(this.ownerId())).name}'s UI.")
                return

            if not (idToMatch := ctx.data.get("custom_id", None)):
                return

            for child in this.walk_children():
                if hasattr(child, "custom_id") and child.custom_id == idToMatch:
                    break
            else:
                log.fatal("Can't find any children with specified ID!")
                return

            match idToMatch:
                case "PERMSELECT":
                    tempPerms = 0
                    for perm in child.values:
                        tempPerms |= APIPermissions[perm].value

                    this.perms = UInt64(tempPerms)
                    await ctx.response.send_message("Permissions selected!", ephemeral=True)
                case "DURATIONSELECT":
                    this.duration = child.values[0]
                    await ctx.response.send_message("Duration selected!", ephemeral=True)

        permSelector = discord.ui.Select(options=[
            discord.SelectOption(label="Discord ID", description="You may use Discord ID to query/get.",
                                 value="DISCORD_ID", emoji="🔵"),
            discord.SelectOption(label="Minecraft UUID", description="You may use linked Minecraft UUIDs to query/get.",
                                 value="MINECRAFT_UUID", emoji="🟩"),
            discord.SelectOption(label="Edit Minecraft UUIDs",
                                 description="You may edit the linked Minecraft UUIDs database.", value="UUID_POST",
                                 emoji="🖋️"),
            discord.SelectOption(label="IP Address", description="You may use IP addresses to do timezone queries",
                                 value="IP_ADDRESS", emoji="📡")
        ], min_values=1, max_values=4, placeholder="Select permissions you want to use", custom_id="PERMSELECT")

        durationSelector = discord.ui.Select(options=[
            discord.SelectOption(label="Infinite", description="This API key will be valid unless you cancel it.",
                                 value="INFINITE", emoji="⏳")
        ], placeholder="Select Duration", min_values=1, max_values=1, custom_id="DURATIONSELECT")

        permSelector.callback = selectCallback
        durationSelector.callback = selectCallback

        submitButton = discord.ui.Button(style=discord.ButtonStyle.success, label="Submit!", custom_id="SUBMIT")
        cancelButton = discord.ui.Button(style=discord.ButtonStyle.danger, label="Cancel", custom_id="CANCEL")

        submitButton.callback = this.buttonCallback
        cancelButton.callback = this.buttonCallback

        container.add_item(title)
        container.add_item(separator)
        container.add_item(tosTitle)
        container.add_item(tosDesc)
        container.add_item(separator)

        container.add_item(detailsTitle)
        container.add_item(detailsInfo)

        actionRow1 = discord.ui.ActionRow()
        actionRow1.add_item(permSelector)

        actionRow2 = discord.ui.ActionRow()
        actionRow2.add_item(durationSelector)

        actionRow3 = discord.ui.ActionRow()
        actionRow3.add_item(submitButton)
        actionRow3.add_item(cancelButton)

        container.add_item(actionRow1)
        container.add_item(actionRow2)
        container.add_item(actionRow3)

        this.add_item(container)

class TzApiKeyManagement(commands.GroupCog, group_name="tzapi", group_description="TZBot API related commands"):
    def __init__(this, client: TZBot) -> None:
        this.client = client

    @app_commands.command(name="requestkey", description="Request a Timezone API key")
    async def request(this, ctx: discord.Interaction) -> None:
            await ctx.response.send_message(view=TZAPIRequestUI(this.client, UInt64(ctx.user.id)))


async def setup(client: TZBot) -> None:
    client.add_view(DecisionActionRow(client))
    await client.add_cog(TzApiKeyManagement(client))
