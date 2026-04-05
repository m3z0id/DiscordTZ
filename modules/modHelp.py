import logging
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import ContextMenu, Group, Command, AppCommandGroup
from discord.ext import commands

from dtypes import TZCommand
from modules import TZBot
from shared import MAX_SHOWABLE_RESULTS

log = logging.getLogger(__name__)

class Help(commands.Cog):
    commandList: dict[str, TZCommand]

    def __init__(this, client: TZBot) -> None:
        this.client = client
        this.commandList = {}

    async def refreshCommandList(this) -> None:
        log.info("Command list is being refreshed...")
        localCommandList = this.client.tree.get_commands()

        try:
            serverCommandList = await this.client.tree.fetch_commands()
        except discord.HTTPException:
            log.error("Failed to fetch global commands")
            return

        serverByName = {cmd.name: cmd for cmd in serverCommandList}

        if this.client.guilds:
            for guild in this.client.guilds:
                try:
                    guildCommands = await this.client.tree.fetch_commands(guild=guild)
                    for cmd in guildCommands:
                        serverByName[cmd.name] = cmd
                except (discord.HTTPException, discord.Forbidden):
                    log.warning(f"Failed to fetch commands for guild {guild.id} ({guild.name})")

        newCommandMap: dict[str, TZCommand] = {}

        for local in localCommandList:
            if isinstance(local, ContextMenu | Group):
                continue

            server = serverByName.get(local.name)
            if server:
                newCommandMap[local.name] = TZCommand.fromAppCommand((local, server))

        localSubcommands: list[Command] = []
        for group in localCommandList:
            if isinstance(group, Group):
                localSubcommands.extend(cmd for cmd in group.commands if isinstance(cmd, Command))

        serverSubcommands: list[AppCommandGroup] = []
        for cmd in serverByName.values():
            if cmd.options:
                serverSubcommands.extend(option for option in cmd.options if isinstance(option, AppCommandGroup))

        serverSubcommandByName = {cmd.name: cmd for cmd in serverSubcommands}

        for local in localSubcommands:
            if isinstance(local, ContextMenu):
                continue

            server = serverSubcommandByName.get(local.name)
            if server:
                newCommandMap[server.qualified_name] = TZCommand.fromAppSubcommand((local, server))

        this.commandList = newCommandMap
        log.info(f"Generated help for {len(this.commandList)} commands!")

    async def commandAutocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=name, value=name)
                for name, cmd in self.commandList.items()
                if name.lower().startswith(current.lower()) \
                and cmd.canBeExecutedBy(interaction.permissions)][:MAX_SHOWABLE_RESULTS]

    @app_commands.command(name="help", description="Display a list of all available commands or detailed info for a specific command.")
    @app_commands.describe(command="Command you want to show documentation for.")
    @app_commands.autocomplete(command=commandAutocomplete)
    async def help(this, ctx: discord.Interaction, command: Optional[str] = None) -> None:
        embed = discord.Embed()
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"Requested by {ctx.user}", icon_url=ctx.user.display_avatar)

        if not command:  # Show generic command list
            embed.colour = discord.Color.green()
            commandListStr = ""
            for command_name, command in this.commandList.items():
                if not command.canBeExecutedBy(ctx.permissions):
                    continue

                commandListStr += f"- /{command_name}\n"

            embed.title = "Command List"
            embed.description = commandListStr

        elif command in this.commandList.keys() and this.commandList[command].canBeExecutedBy(ctx.permissions):
            requestedCmd = this.commandList[command]
            embed.title = f"Documentation for </{requestedCmd.name}:{requestedCmd.commandId}>"
            embed.colour = discord.Color.green()

            embed.add_field(name="Command Information", inline=False, value="\n".join([
                f"Command: `{requestedCmd.name}`",
                f"Description: `{requestedCmd.description}`",
                f"Is Staff-Only: `{requestedCmd.isStaff()}`",
                f"[Required Permissions](<https://discord.com/developers/docs/topics/permissions>): `{requestedCmd.permissions}`"
            ]))

            argsUsage: list[str] = []
            if requestedCmd.hasArgs():
                argsStr = ""
                for index, argument in enumerate(requestedCmd.args.values()):
                    argsStr += "\n".join([
                        f"Name: `{argument.name}`",
                        f"Description: `{argument.description}`",
                        f"Type: `{argument.type.name}`",
                        f"Required: `{argument.required}`",
                    ])

                    if argument.required:
                        argsUsage.append(f"<{argument.name}: {argument.type.name}>")
                    else:
                        argsUsage.append(f"({argument.name}: {argument.type.name})")

                    if index != len(requestedCmd.args) - 1:
                        argsStr += "\n----------\n"

                embed.add_field(name="Arguments", inline=False, value=argsStr)

            embed.add_field(name="Usage", inline=False,
                            value=f"<> = required; () = optional\n```/{requestedCmd.name} {" ".join(argsUsage)}```")

        else:
            log.warning(f"{ctx.user.name} tried getting help for command {command} which doesn't exist!")
            embed.title = "Error"
            embed.colour = discord.Color.red()
            embed.description = f"Command `{command}` not found."

        await ctx.response.send_message(embed=embed)


async def setup(bot: TZBot) -> None:
    await bot.add_cog(Help(client=bot))