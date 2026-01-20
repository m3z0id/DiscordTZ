import inspect
import json
import random

import geoip2
from geoip2 import errors  # noqa: F401
from geoip2.models import City

from server.Api import ApiKey, ApiPermissions
from server.ServerError import ErrorCode
from server.protocol.APIPayload import PacketFlags
from server.protocol.Client import Client
from server.protocol.Response import Response
from server.protocol.TCP import TCPClient
from shared.Helpers import Helpers
from shell.Logger import Logger


from typing import ParamSpec, TypeVar, Callable, Coroutine, Any

P = ParamSpec("P")
R = TypeVar("R")

def autoRespond(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
    async def wrapper(this, *args: P.args, **kwargs: P.kwargs) -> R:
        if not inspect.iscoroutinefunction(func):
            raise RuntimeError("Annotated function isn't async!")

        result = await func(this, *args, **kwargs)
        await this.respond()
        return result
    return wrapper

class SimpleRequest:
    client: Client
    headers: dict
    data: dict
    response: Response | None = None
    city: City | None
    protocol: str
    tzBot: "TZBot"

    def packetNameStringRepr(this) -> str:
        return "INVALID"

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        this.client = client
        this.data = data
        this.headers = headers
        this.tzBot = tzBot

        this.protocol = "TCP" if isinstance(client, TCPClient) else "UDP"
        try:
            this.city = this.tzBot.maxMindDb.city(this.client.ip.address)
        except geoip2.errors.AddressNotFoundError:
            this.city = None


    @autoRespond
    async def process(this) -> None:
        if this.city and this.city.country.iso_code in Helpers.BLACKLISTED_COUNTRIES:
            this.response = ErrorCode.BAD_GEOLOC
            return

    async def respond(this) -> None:
        await sendResponse(this)

    def __str__(this) -> str:
        return f"{this.__class__.__name__}({this.protocol}, {this.client.ip}, {this.headers}, {this.data})"


class PartiallyEncryptedRequest(SimpleRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot)

    async def process(this) -> None:
        super().process()
        if not this.response:
            if not this.client.flags & (PacketFlags.AESGCM | PacketFlags.CHACHAPOLY):
                if not await Helpers.isLocalSubnet(this.client.ip.address):
                    this.response = ErrorCode.BAD_REQUEST
                    this.response.message = "Bad Request, Unencrypted"


class EncryptedRequest(SimpleRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot)

    async def process(this) -> None:
        super().process()
        if not this.response:
            if not this.client.flags & (PacketFlags.AESGCM | PacketFlags.CHACHAPOLY):
                this.response = ErrorCode.BAD_REQUEST
                this.response.message = "Bad Request, Unencrypted"


class APIRequest(PartiallyEncryptedRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot", *requiredPerms: ApiPermissions) -> None:
        super().__init__(client, headers, data, tzBot)
        this.requiredPerms = requiredPerms
        this.rawApiKey = this.headers.get("apiKey")

    async def process(this) -> None:
        await super().process()
        if not this.response:
            if not this.rawApiKey:
                this.response = ErrorCode.FORBIDDEN
                return

            if not await this.tzBot.apiDb.isValidKey(this.rawApiKey):
                Logger.error("Key isn't in the DB")
                this.response = ErrorCode.FORBIDDEN
                return

            apiKey = ApiKey.fromDbForm(this.rawApiKey)

            if not apiKey.hasPermissions(*this.requiredPerms):
                Logger.error("No permissions")
                this.response = ErrorCode.FORBIDDEN
                return


class UserIdRequest(APIRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot", *requiredPerms: ApiPermissions) -> None:
        super().__init__(client, headers, data, tzBot, *requiredPerms)
        this.userId = int(data.get("userId")) if str(data.get("userId")).isnumeric() else None

    async def process(this) -> None:
        await super().process()
        if not this.response:
            if not this.userId:
                Logger.log(f"Response: {this.response}, User ID: {this.userId}")
                this.response = ErrorCode.BAD_REQUEST

class UUIDRequest(APIRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot", *requiredPerms: ApiPermissions) -> None:
        super().__init__(client, headers, data, tzBot, *requiredPerms)
        this.uuid = data.get("uuid")

    async def process(this) -> None:
        if (not this.response and this.uuid is None) or not Helpers.isUUID(this.uuid):
            this.response = ErrorCode.BAD_REQUEST
            this.response.message = "Invalid UUID"


async def chinaResponse(request: SimpleRequest) -> None:
    messages: list[str] = [
        "Taiwan is a country.",
        "Fuck Xi Jinping.",
        "Fuck the CCP.",
        "Free Taiwan.",
        "Tiananmen Square June 4th 1989.",
        "Xi Jinping = Winnie the Pooh",
        "动态网自由门",
        "天安門",
        "天安门",
        "法輪功",
        "李 洪 志",
        "Free Tibet",
        "六四天安門事件",
        "The Tiananmen Square protests of 1989",
        "天安門 大屠殺",
        "The Tiananmen Square Massacre",
        "反右派鬥爭",
        "The Anti-Rightist Struggle",
        "大躍進政策",
        "The Great Leap Forward",
        "文化大革命",
        "The Bad Proletarian Cultural Revolution",
        "人權",
        "Human Rights",
        "民運",
        "Democratization",
        "自由",
        "Freedom",
        "獨立",
        "Independence",
        "多黨制",
        "Multi-party system",
        "台灣",
        "臺灣",
        "Taiwan",
        "Formosa",
        "西藏",
        "新疆維吾爾自治區",
        "民主",
        "言論",
        "思想",
    ]

    request.response = Response(403, random.choice(messages))  # noqa: S311


async def sendResponse(request: SimpleRequest) -> None:
    if request.response and request.response.code == ErrorCode.BAD_GEOLOC.code:
        Logger.log(f"Not responding due to it being from {request.city.country.iso_code}")
        await request.tzBot.API_PACKET_LOGGER.sendLogEmbed(request)
        return

    if request.response:
        Logger.log(f"Responding with: {json.dumps(request.response.__dict__)}")
        await request.client.send(json.dumps(request.response.__dict__).encode())
    await request.tzBot.API_PACKET_LOGGER.sendLogEmbed(request)
