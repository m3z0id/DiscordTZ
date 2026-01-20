import contextlib

import discord
from discord.ext import commands

from database.stats.StatsDatabase import collectCommandStats
from modules.TZBot import TZBot
from modules.helplib.Command import Command
from shared.Helpers import Helpers
from shell.Logger import Logger


class Help(commands.Cog):
    helpGroup = discord.SlashCommandGroup("help", description="Shows different kinds of command help.")

    def __init__(this, client: TZBot) -> None:
        this.client = client

    async def commandAutocomplete(this, ctx: discord.AutocompleteContext | None = None) -> list[str]:
        if not ctx:
            return [cmd.name for cmd in this.client.loadedCommands]
        else:
            return [cmd.name for cmd in this.client.loadedCommands if cmd.name.startswith(ctx.value)]

    @helpGroup.command(name="commands", description="Shows you available commands/help with a specific command.")
    @collectCommandStats
    async def commands(this, ctx: discord.ApplicationContext, commandname: discord.Option(str, "Command name to display help for. If left empty, shows a list of commands.", required=False, autocomplete=commandAutocomplete) = None) -> bool:
        if commandname is None:
            embed = discord.Embed(title="**Command List**", description="", color=discord.Color.green())
            for cmd in this.client.loadedCommands:
                embed.description += f"- {cmd.prefix}{cmd.name}\n"

            await ctx.response.send_message(embed=embed)
            return True

        if commandname in await this.commandAutocomplete():
            cmd: Command | None = None
            for command in this.client.loadedCommands:
                with contextlib.suppress(IndexError):
                    if command.name == commandname or command.name == commandname.split(" ")[-1]:
                        cmd = command
                        break

            embed = discord.Embed(title=f"**Command Help for {cmd.mention}**", description="", color=discord.Color.green())
            embed.add_field(
                name="**Command Info**",
                value="\n".join([
                    f"Command: `{commandname}`",
                    f"Description: `{cmd.description}` {f"\nCooldown: `{int(cmd.cooldown)}s`" if cmd.cooldown else ""}",
                    f"Permissions: `{"Owner" if cmd.isOwnerCommand() else "Everyone"}`",
                ]), inline=False)

            argsUsage: list[str] = []
            if len(cmd.args) != 0:
                argsHelp: list[str] = []
                for arg in cmd.args:
                    argsUsage.append(f"<{arg.name}: {arg.input_type.name}>" if arg.required else f"({arg.name}: {arg.input_type.name})")
                    argsHelp.append("\n".join([
                        f"Name: `{arg.name}`",
                        f"Description: `{arg.description}`",
                        f"Type: `{arg.input_type.name}`",
                        f"Required: `{arg.required}` {f'\nDefault: `{arg.default}`\n' if not arg.required else '\n'}",
                    ]))

                embed.add_field(name="**Arguments**", value="----------\n".join(argsHelp), inline=False)

            embed.add_field(
                name="**Usage**",
                value=f"<> = required; () = optional\n\
                ```{cmd.prefix}{cmd.name} {' '.join(argsUsage)}```",
                inline=False
            )
            await ctx.response.send_message(embed=embed)
            return True

        else:
            embed = await this.client.getFail(description="Invalid command.", user=ctx.user)
            await ctx.response.send_message(embed=embed)
            return False


def setup(client: TZBot) -> None:
    client.add_cog(Help(client))