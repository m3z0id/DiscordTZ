import contextlib
import datetime

import discord

from modules.TZBot import TZBot
from modules.ui.DecisionActionRow import DecisionActionRow
from server.APIKey import ApiKey, ApiPermissions
from shell.Logger import Logger


class TzApiExplanationModal(discord.ui.Modal):
    appInfo: str = ""
    apiUsage: str = ""

    def __init__(this, *children: discord.InputText, custom_id: str | None = None) -> None:
        super().__init__(*children, title="Info about your API usage.", custom_id=custom_id, timeout=None)
        this.appNameBox = discord.ui.InputText(
            label="Application Name", placeholder="My Super Cool App", style=discord.InputTextStyle.short, required=True
        )
        this.appInfoBox = discord.ui.InputText(
            label="Application Info",
            placeholder="My Application will be used for...",
            style=discord.InputTextStyle.paragraph,
            required=True,
            max_length=4000,
        )
        this.apiUsageBox = discord.ui.InputText(
            label="Your API Usage",
            placeholder="I will use Timezone bot API for...",
            style=discord.InputTextStyle.paragraph,
            required=True,
            max_length=4000,
        )

        this.add_item(this.appInfoBox)
        this.add_item(this.apiUsageBox)

    async def callback(this, ctx: discord.Interaction) -> None:
        this.appInfo = this.children[0].value
        this.apiUsage = this.children[1].value
        await ctx.response.send_message("Answers recorded!", ephemeral=True)


class TzApiRequestUI(discord.ui.View):
    perms: list[str] = []
    duration: str = ""
    modal: TzApiExplanationModal | None = None

    def __init__(this, client: TZBot, dialogOwner: int, *items) -> None:
        super().__init__(*items, timeout=None)
        this.dialogOwner = dialogOwner
        this.client = client

    @discord.ui.select(
        placeholder="Select permissions you want to use",
        min_values=1,
        max_values=4,
        options=[
            discord.SelectOption(label="Discord ID", description="You may use Discord ID to query/get.", value="DISCORD_ID", emoji="🔵"),
            discord.SelectOption(
                label="Minecraft UUID", description="You may use linked Minecraft UUIDs to query/get.", value="MINECRAFT_UUID", emoji="🟩"
            ),
            discord.SelectOption(
                label="Edit Minecraft UUIDs", description="You may edit the linked Minecraft UUIDs database.", value="UUID_POST", emoji="🖋️"
            ),
            discord.SelectOption(label="IP Address", description="You may use IP addresses to do timezone queries", value="IP_ADDRESS", emoji="📡"),
        ],
        custom_id="PERMSELECT",
    )
    async def permsSelect(this, selection: discord.ui.Select, ctx: discord.Interaction) -> None:
        if ctx.user.id != this.dialogOwner:
            await ctx.response.send_message("You can't do that!", ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to mess with {ctx.guild.get_member(this.dialogOwner).display_name}'s dialog!")
            return

        this.perms = selection.values
        await ctx.response.send_message("Permissions selected! Turn on DMs from this server to receive the notification!", ephemeral=True)

    @discord.ui.select(
        placeholder="Select Duration",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label="Infinite", description="This API key will be valid unless you cancel it.", value="INFINITE", emoji="⏳", default=True
            ),
        ],
        custom_id="DURATIONSELECT",
    )
    async def durationSelect(this, selection: discord.ui.Select, ctx: discord.Interaction) -> None:
        if ctx.user.id != this.dialogOwner:
            await ctx.response.send_message("You can't do that!", ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to mess with {ctx.guild.get_member(this.dialogOwner).display_name}'s dialog!")
            return

        this.duration = selection.value
        await ctx.response.send_message("Duration selected! Turn on DMs from this server to receive the notification!", ephemeral=True)

    @discord.ui.button(
        label="Submit!",
        style=discord.ButtonStyle.success,
        custom_id="SUBMIT",
    )
    async def buttonHandler(this, button: discord.ui.Button, ctx: discord.Interaction) -> None:  # noqa: ARG002
        if ctx.user.id != this.dialogOwner:
            await ctx.response.send_message("You can't do that!", ephemeral=True)
            Logger.error(f"{ctx.user.name} tried to mess with {(await ctx.client.fetch_user(this.dialogOwner)).name}'s dialog!")
            return

        this.modal = TzApiExplanationModal()
        await ctx.response.send_modal(this.modal)
        await this.modal.wait()

        permsInt = ApiPermissions(0)
        for perm in this.perms:
            permsInt |= getattr(ApiPermissions, perm)

        newApiKey: ApiKey = ApiKey(ctx.user.id, permsInt, "INFINITE")
        dbForm: str = newApiKey.toDbForm()

        for child in this.children:
            child.disabled = True
        this.stop()

        with contextlib.suppress(ValueError):
            this.client.dialogOwners.remove(this.dialogOwner)

        await ctx.message.edit(view=this)

        apiChannel: discord.Thread = await ctx.client.fetch_channel(this.client.config.server.apiApproveChannelId)
        embed: discord.Embed = discord.Embed(
            color=discord.Color.darker_grey(),
            title="**API Key Requested**",
            description=f"**ID**: {newApiKey.keyId}\n**Requested by**: {ctx.user.name}\n**Duration**: {newApiKey.validUntil}",
        )

        embed.add_field(name="**Permissions**", value=f"```{', '.join(newApiKey.prettyPrintPerms())} ({newApiKey.permissions})```", inline=False)
        embed.add_field(name="**App Info**", value=f"```{this.modal.appInfo}```", inline=False)
        embed.add_field(name="**Intended API Usage**", value=f"```{this.modal.apiUsage}```", inline=False)
        embed.set_thumbnail(url=ctx.user.avatar.url)
        embed.set_author(name=ctx.user.name, icon_url=ctx.user.avatar.url)
        embed.set_footer(text=f"Requested by {ctx.user.name}", icon_url=ctx.user.avatar.url)
        embed.timestamp = datetime.datetime.now()

        msg: discord.Message = await apiChannel.send(embed=embed, view=DecisionActionRow(this.client))

        await this.client.apiDb.addToPending(dbForm, msg.id)
