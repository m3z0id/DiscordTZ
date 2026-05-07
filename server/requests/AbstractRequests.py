from __future__ import annotations

import inspect
import json
import logging
import random
from typing import ParamSpec, TypeVar, Callable, Coroutine, Any, TYPE_CHECKING, Optional
from uuid import UUID

import geoip2
from geoip2 import errors  # noqa: F401
from geoip2.models import Country

from dtypes import ErrorCode, Response, PacketFlags, UInt64
from modules import TZBot
from server.APIKey import APIKey, APIPermissions
from server.protocol import Client
from shared import BLACKLISTED_COUNTRIES, TChecker

if TYPE_CHECKING:
    pass

P = ParamSpec("P")
R = TypeVar("R")

log = logging.getLogger(__name__)

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
    response: Optional[Response] = None
    country: Optional[Country] = None
    tzBot: TZBot

    def packetNameStringRepr(this) -> str:
        return "INVALID"

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        this.client = client
        this.data = data
        this.headers = headers
        this.tzBot = tzBot

        try:
            this.country = this.tzBot.geoIP.country(this.client.ip)
        except geoip2.errors.AddressNotFoundError:
            this.country = None

    async def process(this) -> None:
        if this.country and this.country.country.iso_code in BLACKLISTED_COUNTRIES:
            this.response = ErrorCode.BAD_GEOLOC

        if this.__class__.__name__ == "SimpleRequest":
            await this.respond()

    async def respond(this) -> None:
        await sendResponse(this)

    def __str__(this) -> str:
        return f"{this.__class__.__name__}({this.client.getProtocolStringRepr()}, {this.client.ip}, {this.headers}, {this.data})"


class PartiallyEncryptedRequest(SimpleRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot)

    async def process(this) -> None:
        await super().process()
        if not this.response:
            if not this.client.flags & (PacketFlags.AESGCM | PacketFlags.CHACHAPOLY):
                if not this.client.ip.is_private:
                    this.response = ErrorCode.BAD_REQUEST
                    this.response.message = "Bad Request, Unencrypted"


class EncryptedRequest(SimpleRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot)

    async def process(this) -> None:
        await super().process()
        if not this.response:
            if not this.client.flags & (PacketFlags.AESGCM | PacketFlags.CHACHAPOLY):
                this.response = ErrorCode.BAD_REQUEST
                this.response.message = "Bad Request, Unencrypted"


class APIRequest(PartiallyEncryptedRequest):
    requiredPerms: tuple[APIPermissions, ...]
    apiKey: APIKey
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot, *requiredPerms: APIPermissions) -> None:
        super().__init__(client, headers, data, tzBot)
        this.requiredPerms = requiredPerms

    async def process(this) -> None:
        await super().process()
        if not this.response:
            rawApiKey: Optional[Any] = this.headers.get("apiKey")
            if not isinstance(rawApiKey, str):
                this.response = ErrorCode.FORBIDDEN
                return

            if not await this.tzBot.apiDb.isKeyValid(rawApiKey):
                log.error("Key isn't in the DB")
                this.response = ErrorCode.FORBIDDEN
                return

            this.apiKey = APIKey.fromJWT(rawApiKey, this.tzBot.config.server.apiKeysKey)
            if not this.apiKey.hasPermissions(*this.requiredPerms):
                log.error("No permissions")
                this.response = ErrorCode.FORBIDDEN
                return


class UserIdRequest(APIRequest):
    userId: UInt64
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot, *requiredPerms: APIPermissions) -> None:
        super().__init__(client, headers, data, tzBot, *requiredPerms)

    async def process(this) -> None:
        await super().process()
        if not this.response:
            try:
                this.userId = TChecker.expectUInt64(this.data.get("userId"))
            except ValueError:
                this.response = ErrorCode.BAD_REQUEST

class UUIDRequest(APIRequest):
    uuid: UUID
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot, *requiredPerms: APIPermissions) -> None:
        super().__init__(client, headers, data, tzBot, *requiredPerms)

    async def process(this) -> None:
        await super().process()
        if not this.response:
            try:
                this.uuid = TChecker.expectUUID(this.data.get("uuid"))
            except ValueError:
                this.response = ErrorCode.BAD_REQUEST


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
    if request.response and request.country and request.response.code == ErrorCode.BAD_GEOLOC.code:
        log.warning(f"Not responding due to it being from {request.country.country.iso_code}")
        await request.tzBot.API_PACKET_LOGGER.sendLogEmbed(request)
        return

    if request.response:
        log.info(f"Responding with: {json.dumps(request.response.__dict__)}")
        await request.client.send(request.response.__dict__)
    await request.tzBot.API_PACKET_LOGGER.sendLogEmbed(request)
