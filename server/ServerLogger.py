import io
import json
from datetime import datetime
from typing import Final

import discord

from server.ServerError import ErrorCode
from server.protocol.APIPayload import PacketFlags
from server.requests.AbstractRequests import SimpleRequest
from server.requests.Requests import PingRequest, TimeZoneFromIPRequest, UserIdUUIDLinkPost
from shared.Helpers import Helpers


class ServerLogger:
    MAX_DATA_EMBED_LEN: Final[int] = 900

    def __init__(this, tzBot: "TZBot", loggingEnabled: bool) -> None:
        this.tzBot = tzBot
        this.loggingEnabled = loggingEnabled

    async def setLoggingEnabled(this, enabled: bool) -> None:
        this.loggingEnabled = enabled

    async def sendLogEmbed(this, request: SimpleRequest) -> None:
        if isinstance(request, PingRequest):
            return

        embed: discord.Embed = discord.Embed()
        fileSendList: list[discord.File] = []

        lock = "🔒" if request.client.flags & PacketFlags.AESGCM else ""
        warning = "⚠️" if request.city and (request.response and request.response.code == ErrorCode.BAD_GEOLOC.code) else ""
        if warning:
            request.response = None

        if not warning and isinstance(request, TimeZoneFromIPRequest):
            request.data["ip"] = "<redacted>"

        if not warning and isinstance(request, UserIdUUIDLinkPost) and request.response.code == ErrorCode.OK.code:
            request.response.message = "<redacted>"

        if len(str(request.data)) < this.MAX_DATA_EMBED_LEN:
            embed.add_field(name="Request Data", value=f"```{str(request.data).replace("'", "\"")}```", inline=False)
        else:
            embed.add_field(name="Request Data", value=f"Request is included in the file below due to its size.", inline=False)
            requestFile = discord.File(io.BytesIO(str(request.data).replace("'", "\"").encode("utf-8")), "RequestData.json")
            fileSendList.append(requestFile)

        if request.response:
            if len(str(request.response)) < this.MAX_DATA_EMBED_LEN:
                embed.add_field(name="Response Data", value=f"```{json.dumps(request.response.__dict__)}```", inline=False)
            else:
                embed.add_field(name="Response Data", value=f"Request is included in the file below due to its size.", inline=False)
                responseFile = discord.File(io.BytesIO(json.dumps(request.response.__dict__).encode("utf-8")), "ResponseData.json")
                fileSendList.append(responseFile)


        packetName: str = request.packetNameStringRepr()
        protocol: str = request.protocol
        source: str = f"{warning} {await Helpers.getCountryOrHost(request)} {warning}".strip()

        flags: list[str] = [flag.name for flag in PacketFlags if request.client.flags & flag and flag.name is not (None or 0)]

        description = "\n".join([
            f"**Packet**: {packetName}",
            f"**Protocol**: {protocol}",
            f"**Source**: {source}",
            f"**Flags**: {", ".join(flags)}"
        ])

        embed.description = description
        embed.timestamp = datetime.now()

        if request.response and 200 <= request.response.code <= 300:
            embed.colour = discord.Color.green()
            embed.title = f"{lock} **Success** {lock}".strip()
            await this.tzBot.successChannel.send(embed=embed, files=fileSendList)

        else:
            embed.colour = discord.Color.red()
            embed.title = f"{lock} **Error** {lock}".strip()
            await this.tzBot.errorChannel.send(embed=embed, files=fileSendList)