import asyncio
from ipaddress import IPv4Address, AddressValueError
from typing import override, Optional
from uuid import UUID

import geoip2.errors
import tzlocal

from modules import TZBot
from server import APIPermissions
from server.protocol import Client
from server.requests import autoRespond, UserIdRequest, APIRequest, UUIDRequest, SimpleRequest
from shared import Helpers, TIMEZONE_CHECK_LIST
from dtypes import ErrorCode


class TimezoneFromUserIdRequest(UserIdRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.DISCORD_ID)

    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_FROM_USERID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            this.response = ErrorCode.OK
            this.response.message = await this.tzBot.db.getTimezoneFromUserId(this.userId)
            if not this.response.message:
                this.response = ErrorCode.NOT_FOUND


class TimezoneFromIPRequest(APIRequest):
    askedIp: Optional[IPv4Address]

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.IP_ADDRESS)

        try:
            this.askedIp = IPv4Address(str(this.data.get("ip")))
            this.data["ip"] = "<redacted>"
        except AddressValueError:
            this.askedIp = None


    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_FROM_IP"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            try:
                if not this.askedIp:
                    this.response = ErrorCode.BAD_REQUEST
                else:
                    if this.askedIp.is_private:
                        if this.client.ip.is_private:
                            this.response = ErrorCode.OK
                            this.response.message = tzlocal.get_localzone().key
                        else:
                            requestCity = this.tzBot.maxMindDb.city(str(this.client.ip))
                            this.response = ErrorCode.OK
                            this.response.message = requestCity.location.time_zone

                    else:
                        requestCity = this.tzBot.maxMindDb.city(str(this.askedIp))
                        this.response = ErrorCode.OK
                        this.response.message = requestCity.location.time_zone
            except geoip2.errors.AddressNotFoundError:
                this.response = ErrorCode.NOT_FOUND


class PingRequest(SimpleRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot)

    @override
    def packetNameStringRepr(this) -> str:
        return "PING"

    @override
    @autoRespond
    async def process(this) -> None:
        if not this.response:
            this.response = ErrorCode.OK
            this.response.message = "Pong"


class UserIdUUIDLinkPost(APIRequest):
    code: str = ""
    uuid: Optional[UUID]
    timezone: Optional[str]

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.UUID_POST)
        this.timezone = this.data.get("timezone")
        try:
            this.uuid = UUID(this.data.get("uuid"))
        except ValueError:
            this.uuid = None


    @override
    def packetNameStringRepr(this) -> str:
        return "USER_ID_UUID_LINK_POST"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if not this.uuid:
                this.response = ErrorCode.BAD_REQUEST
                this.response.message = "Invalid UUID"

            if this.timezone not in TIMEZONE_CHECK_LIST:
                this.response = ErrorCode.NOT_FOUND

            elif await this.tzBot.db.getUserIdFromUUID(this.uuid) or this.uuid in [val[0] for val in this.tzBot.linkCodes.values()]:
                this.response = ErrorCode.CONFLICT
                this.response.message = "UUID already registered"

            else:
                this.code = Helpers.generateCharSequence(6)

                this.tzBot.linkCodes.update({this.code: (this.uuid, this.timezone)})
                asyncio.create_task(this.tzBot.removeCode(15, this.code))

                this.response = ErrorCode.OK
                this.response.message = this.code


class TimezoneFromUUIDRequest(UUIDRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.MINECRAFT_UUID)

    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_FROM_UUID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            timezone = await this.tzBot.db.getTimezoneFromUUID(this.uuid)
            if not timezone:
                this.response = ErrorCode.NOT_FOUND

            else:
                this.response = ErrorCode.OK
                this.response.message = timezone


class IsLinkedRequest(UUIDRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.MINECRAFT_UUID)

    @override
    def packetNameStringRepr(this) -> str:
        return "IS_LINKED"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if discordUsername := await this.tzBot.db.getUserIdFromUUID(this.uuid):
                this.response = ErrorCode.OK
                this.response.message = (await this.tzBot.fetch_user(discordUsername())).name
            else:
                this.response = ErrorCode.NOT_FOUND


class UserIdFromUUIDRequest(UUIDRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.MINECRAFT_UUID, APIPermissions.DISCORD_ID)

    @override
    def packetNameStringRepr(this) -> str:
        return "USER_ID_FROM_UUID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if not (userId := await this.tzBot.db.getUserIdFromUUID(this.uuid)):
                this.response = ErrorCode.NOT_FOUND
            else:
                this.response = ErrorCode.OK
                this.response.message = userId


class UUIDFromUserIdRequest(UserIdRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.MINECRAFT_UUID, APIPermissions.DISCORD_ID)

    @override
    def packetNameStringRepr(this) -> str:
        return "UUID_FROM_USER_ID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if not (uid := await this.tzBot.db.getUUIDFromUserId(this.userId)):
                this.response = ErrorCode.NOT_FOUND
            else:
                this.response = ErrorCode.OK
                this.response.message = uid