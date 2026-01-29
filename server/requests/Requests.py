import asyncio
from typing import override

import geoip2.errors
import tzlocal

from server.Api import ApiPermissions
from server.ServerError import ErrorCode
from server.protocol.Client import Client
from server.requests.AbstractRequests import APIRequest, SimpleRequest, UserIdRequest, UUIDRequest, \
    autoRespond, LinkPostData, IPData, UUIDData, BaseData
from shared.Helpers import Helpers
from shared.Timezones import Timezones
from shell.Logger import Logger


class TimeZoneRequest(UserIdRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot, ApiPermissions.DISCORD_ID)

    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_FROM_USERID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            this.response = ErrorCode.OK
            this.response.message = await Helpers.tzBot.db.getTimeZone(this.userId)
            if not this.response.message:
                this.response = ErrorCode.NOT_FOUND


class TimeZoneFromIPRequest(APIRequest[IPData]):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot, ApiPermissions.IP_ADDRESS)

        this.askedIp = str(this.data.get("ip"))
        this.data["ip"] = "<redacted>"

    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_FROM_IP"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if not this.askedIp:
                this.response = ErrorCode.BAD_REQUEST
            else:
                try:
                    if await Helpers.isLocalSubnet(this.askedIp):
                        if await Helpers.isLocalSubnet(this.client.ip.address):
                            this.response = ErrorCode.OK
                            this.response.message = tzlocal.get_localzone().key
                        else:
                            requestCity = this.tzBot.maxMindDb.city(this.client.ip.address)
                            if requestCity:
                                this.response = ErrorCode.OK
                                this.response.message = requestCity.location.time_zone
                            else:
                                this.response = ErrorCode.NOT_FOUND
                    else:
                        requestCity = this.tzBot.maxMindDb.city(this.askedIp)
                        if requestCity:
                            this.response = ErrorCode.OK
                            this.response.message = requestCity.location.time_zone
                        else:
                            this.response = ErrorCode.NOT_FOUND

                except geoip2.errors.AddressNotFoundError:
                    this.response = ErrorCode.NOT_FOUND

class PingRequest(SimpleRequest[BaseData]):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
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


class UserIdUUIDLinkPost(APIRequest[LinkPostData]):
    code: str = ""

    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot, ApiPermissions.UUID_POST)
        this.timezone = this.data.get("timezone")
        this.uuid = this.data.get("uuid")

    @override
    def packetNameStringRepr(this) -> str:
        return "USER_ID_UUID_LINK_POST"

    @override
    @autoRespond
    async def process(this) -> None:
        # Check UUID validity manually since we don't inherit UUIDRequest anymore
        if (not this.response and this.uuid is None) or not Helpers.isUUID(this.uuid):
            this.response = ErrorCode.BAD_REQUEST
            this.response.message = "Invalid UUID" 
            return

        await super().process()

        if not this.response:
            if this.timezone not in Timezones.CHECK_LIST:
                this.response = ErrorCode.NOT_FOUND

            elif await this.tzBot.db.getUserIdByUUID(this.uuid) or this.uuid in [val[0] for val in Helpers.tzBot.linkCodes.values()]:
                this.response = ErrorCode.CONFLICT
                this.response.message = "UUID already registered"

            else:
                this.code = await Helpers.generateCharSequence(6)

                this.tzBot.linkCodes.update({this.code: (this.uuid, this.timezone)})
                asyncio.create_task(this.tzBot.removeCode(15, this.code))

                this.response = ErrorCode.OK
                this.response.message = this.code


class TimezoneFromUUIDRequest(UUIDRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot, ApiPermissions.MINECRAFT_UUID)

    @override
    def packetNameStringRepr(this) -> str:
        return "TIMEZONE_FROM_UUID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            timezone = await this.tzBot.db.getTimezoneByUUID(this.uuid)
            if not timezone:
                this.response = ErrorCode.NOT_FOUND

            else:
                this.response = ErrorCode.OK
                this.response.message = timezone


class IsLinkedRequest(UUIDRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot, ApiPermissions.MINECRAFT_UUID)

    @override
    def packetNameStringRepr(this) -> str:
        return "IS_LINKED"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if discordUsername := await this.tzBot.db.getUserIdByUUID(this.uuid):
                this.response = ErrorCode.OK
                this.response.message = (await this.tzBot.fetch_user(discordUsername)).name
            else:
                this.response = ErrorCode.NOT_FOUND


class UserIDFromUUIDRequest(UUIDRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot, ApiPermissions.MINECRAFT_UUID, ApiPermissions.DISCORD_ID)

    @override
    def packetNameStringRepr(this) -> str:
        return "USER_ID_FROM_UUID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if not (userId := await this.tzBot.db.getUserIdByUUID(this.uuid)):
                this.response = ErrorCode.NOT_FOUND
            else:
                this.response = ErrorCode.OK
                this.response.message = userId


class UUIDFromUserIDRequest(UserIdRequest):
    def __init__(this, client: Client, headers: dict, data: dict, tzBot: "TZBot") -> None:
        super().__init__(client, headers, data, tzBot, ApiPermissions.MINECRAFT_UUID, ApiPermissions.DISCORD_ID)

    @override
    def packetNameStringRepr(this) -> str:
        return "UUID_FROM_USER_ID"

    @override
    @autoRespond
    async def process(this) -> None:
        await super().process()

        if not this.response:
            if not (uid := await this.tzBot.db.getUUIDByUserId(this.userId)):
                this.response = ErrorCode.NOT_FOUND
            else:
                this.response = ErrorCode.OK
                this.response.message = uid