import asyncio
import logging
from ipaddress import IPv4Address
from typing import override
from uuid import UUID

import geoip2.errors
import tzlocal

from dtypes import ErrorCode, TimezoneRepr
from modules import TZBot
from server import APIPermissions
from server.protocol import Client
from server.requests import autoRespond, UserIdRequest, APIRequest, UUIDRequest, SimpleRequest
from shared import Helpers, TChecker

log = logging.getLogger(__name__)

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
    askedIp: IPv4Address

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.IP_ADDRESS)

    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_FROM_IP"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            try:
                this.askedIp = IPv4Address(TChecker.expectUInt32(this.data.get("ip"))())
                if this.askedIp.is_private:
                    if this.client.ip.is_private:
                        this.response = ErrorCode.OK
                        this.response.message = tzlocal.get_localzone().key
                    else:
                        requestCity = this.tzBot.geoIP.country(str(this.client.ip))
                        this.response = ErrorCode.OK
                        this.response.message = requestCity.location.time_zone

                else:
                    requestCity = this.tzBot.geoIP.country(str(this.askedIp))
                    this.response = ErrorCode.OK
                    this.response.message = requestCity.location.time_zone

            except (geoip2.errors.AddressNotFoundError, ValueError):
                this.response = ErrorCode.BAD_REQUEST

            finally:
                if this.askedIp: this.data["ip"] = "<redacted>"


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
    uuid: UUID
    timezone: TimezoneRepr

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.UUID_POST)

    @override
    def packetNameStringRepr(this) -> str:
        return "USER_ID_UUID_LINK_POST"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            try:
                this.uuid = TChecker.expectUUID(this.data.get("uuid"))
                this.timezone = TChecker.expectTimezone(this.data.get("timezone"))

                if await this.tzBot.db.getUserIdFromUUID(this.uuid) or await this.tzBot.isLinking(this.uuid):
                    this.response = ErrorCode.CONFLICT
                    this.response.message = "UUID already registered"

                else:
                    this.code = Helpers.generateCharSequence(6)

                    this.tzBot.linkCodes.update({this.code: (this.uuid, this.timezone.stringify())})
                    asyncio.create_task(this.tzBot.removeCode(15, this.code))

                    this.response = ErrorCode.OK
                    this.response.message = this.code

            except ValueError:
                this.response = ErrorCode.BAD_REQUEST


class TimezoneAdjustRequest(APIRequest):
    uuid: UUID
    timezone: TimezoneRepr

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: TZBot) -> None:
        super().__init__(client, headers, data, tzBot, APIPermissions.UUID_POST)

    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_ADJUSTMENT"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            try:
                this.uuid = TChecker.expectUUID(this.data.get("uuid"))
                this.timezone = TChecker.expectTimezone(this.data.get("timezone"))

                if not await this.tzBot.db.getUserIdFromUUID(this.uuid):
                    this.response = ErrorCode.NOT_FOUND

                else:
                    this.response = ErrorCode.INTERNAL_SERVER_ERROR
                    if await this.tzBot.db.setTimezoneUUID(this.uuid, this.timezone.stringify()):
                        this.response = ErrorCode.OK

            except ValueError:
                this.response = ErrorCode.BAD_REQUEST


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
                this.response.message = userId()


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
                this.response.message = str(uid)