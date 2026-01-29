import copy
from dataclasses import dataclass
from enum import IntEnum
from ipaddress import IPv4Address
from typing import Literal, TypeVar, Generic, Self, NewType, TypeIs, TypedDict, NotRequired, ReadOnly

from dataclasses_json import dataclass_json
from discord import Option

from shared.Constants import UUID_PATTERN

T = TypeVar("T")

class DeepCopier(type):
    def __getattribute__(cls, name: str) -> object:
        return copy.deepcopy(super().__getattribute__(name))

@dataclass_json
@dataclass
class MaxmindConfig:
    accountId: int
    token: str

@dataclass_json
@dataclass
class MariaDBConfig:
    db: str
    user: str
    password: str
    host: str
    port: int
    autocommit: bool


@dataclass_json
@dataclass
class ServerConfig:
    port: int
    aesKey: str
    apiKeysKey: str
    apiApproveChannelId: int
    devlogRoleId: int


@dataclass_json
@dataclass
class PacketLogsConfig:
    errorChannelId: int
    successChannelId: int
    guildId: int


@dataclass_json
@dataclass
class Config:
    token: str
    ownerId: int
    maxmind: MaxmindConfig
    mariadbDetails: MariaDBConfig
    server: ServerConfig
    packetLogs: PacketLogsConfig


type ValidStatusCode = Literal[-1, 200, 400, 403, 404, 405, 409, 500]
@dataclass
class Response(Generic[T]):
    code: ValidStatusCode
    message: T

    def __init__(this, code: ValidStatusCode, message: T) -> None:
        this.code = code
        this.message = message


class ErrorCode(metaclass=DeepCopier):
    OK = Response(200, "OK")
    BAD_REQUEST = Response(400, "Bad Request")
    FORBIDDEN = Response(403, "Forbidden")
    NOT_FOUND = Response(404, "Not Found")
    BAD_METHOD = Response(405, "Bad Method")
    INTERNAL_SERVER_ERROR = Response(500, "Internal Server Error")
    CONFLICT = Response(409, "Conflict")
    BAD_GEOLOC = Response(-1, "Bad Geolocation")

class PacketFlags(IntEnum):
    AESGCM = 1 << 0
    CHACHAPOLY = 1 << 1
    GUNZIP = 1 << 2
    MSGPACK = 1 << 3

class APIPayload:
    dataOffset: int
    requestType: int
    flags: PacketFlags
    contentLen: int

    def __init__(this, dataOffset: int, requestType: int, flags: PacketFlags, contentLen: int) -> None:
        this.dataOffset = dataOffset
        this.requestType = requestType
        this.flags = flags
        this.contentLen = contentLen

    @classmethod
    def fromTuple(cls, apiPayload: tuple[int, int, int, int, int]) -> Self:
        return cls(*apiPayload)

Port = NewType("Port", int)
def isPort(port: Port | int) -> TypeIs[Port]:
    return 0 >= port <= 65535

UUID = NewType("UUID", str)
def isUUID(uuid: UUID | str) -> TypeIs[UUID]:
    return bool(UUID_PATTERN.match(uuid))

class RequestHeaders(TypedDict):
    apiKey: NotRequired[ReadOnly[str]]

class UserIdData(TypedDict):
    userId: ReadOnly[int | str]

class UUIDData(TypedDict):
    uuid: ReadOnly[str]

class TimezoneData(TypedDict):
    uuid: ReadOnly[str]
    timezone: ReadOnly[str]

class IPData(TypedDict):
    ip: IPv4Address

type RequestDataPayload = UserIdData | UUIDData | TimezoneData | IPData

@dataclass_json
@dataclass
class Profile:
    presence: str = "online"
    activityType: int = -1
    activityName: str = ""

@dataclass
class Command:
    prefix: Literal["/", "tz!"]

    name: str
    description: str
    cooldown: float | None
    checks: list
    args: list[Option]
    mention: str

    def isOwnerCommand(this) -> bool:
        for check in this.checks:
            if str(check.__qualname__).startswith("is_owner"):
                return True

        return False