import copy
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from io import BytesIO
from typing import Literal, TypeVar, Self, ClassVar, Final, Union, Type, Optional, NamedTuple

from dataclasses_json import dataclass_json, config
from discord import Permissions
from discord.app_commands import Command, Group, AppCommand, AppCommandGroup, MissingPermissions
from discord.app_commands.transformers import CommandParameter
from marshmallow import fields

from shared import Constants


class DeepCopier(type):
    def __getattribute__(cls, name: str) -> object:
        return copy.deepcopy(super().__getattribute__(name))

class LimitedInt:
    MASK: ClassVar[int]
    _val: int

    def __init__(this, value: int):
        this._val = value & this.MASK

    def max(this) -> int:
        return this.MASK

    def __int__(this):
        return this._val

    def __str__(this):
        return str(this._val)

    def __eq__(this, other: Self) -> bool:
        return this._val == other._val

    def __add__(this, other: Union[Self, int]) -> Self:
        this._val = (this._val + int(other)) & this.MASK
        return this

    def __sub__(this, other: Union[Self, int]) -> Self:
        this._val = (this._val - int(other)) & this.MASK
        return this

    def __and__(this, other: Union[Self, int]) -> Self:
        this._val = this._val & int(other)
        return this

    def __or__(this, other: Union[Self, int]) -> Self:
        this._val = this._val | int(other)
        return this

    def __xor__(this, other: Union[Self, int]) -> Self:
        this._val = this._val ^ int(other)
        return this

    def __iadd__(this, other: Union[Self, int]) -> Self:
        this._val = (this._val + int(other)) & this.MASK
        return this

    def __isub__(this, other: Union[Self, int]) -> Self:
        this._val = (this._val - int(other)) & this.MASK
        return this

    def __iand__(this, other: Union[Self, int]) -> Self:
        this._val &= int(other)
        this._val &= this.MASK
        return this

    def __ior__(this, other: Union[Self, int]) -> Self:
        this._val |= int(other)
        this._val &= this.MASK
        return this

    def __ixor__(this, other: Union[Self, int]) -> Self:
        this._val ^= int(other)
        this._val &= this.MASK
        return this

    def __call__(this, *args, **kwargs) -> int:
        return this._val

    def __hash__(this) -> int:
        return this._val.__hash__()

    @classmethod
    def boundsChecked(cls, value: int) -> LimitedInt:
        if 0 > value >= cls.MASK:
            raise ValueError("Integer failed bounds check!")

        return cls(value)

class UInt8(LimitedInt):
    MASK: ClassVar[int] = 0xFF
    def __init__(this, value: int) -> None:
        super().__init__(value)

class UInt16(LimitedInt):
    MASK: ClassVar[int] = 0xFFFF
    def __init__(this, value: int) -> None:
        super().__init__(value)

class UInt32(LimitedInt):
    MASK: ClassVar[int] = 0xFFFFFFFF
    def __init__(self, value: int) -> None:
        super().__init__(value)

class UInt64(LimitedInt):
    MASK: ClassVar[int] = 0xFFFFFFFF_FFFFFFFF
    def __init__(self, value: int) -> None:
        super().__init__(value)

class UInt128(LimitedInt):
    MASK: ClassVar[int] = 0xFFFFFFFF_FFFFFFFF_FFFFFFFF_FFFFFFFF
    def __init__(self, value: int) -> None:
        super().__init__(value)


T = TypeVar("T", bound="LimitedInt")
def LimitedIntCoder(cls: Type[T]) -> dict[str, dict]:
    return config(
        encoder=int,
        decoder=lambda i: cls(i) if i is not None else cls(0),
        mm_field=fields.Integer()
    )

@dataclass_json
@dataclass
class MaxmindConfig:
    accountId: UInt32 = field(metadata=LimitedIntCoder(UInt32))
    token: str

@dataclass_json
@dataclass
class MariaDBConfig:
    db: str
    user: str
    password: str
    host: str
    port: int = field(metadata=LimitedIntCoder(UInt16))
    autocommit: bool


@dataclass_json
@dataclass
class ServerConfig:
    port: UInt16 = field(metadata=LimitedIntCoder(UInt16))
    aesKey: str
    apiKeysKey: str
    apiApproveChannelId: UInt64 = field(metadata=LimitedIntCoder(UInt64))
    devlogRoleId: UInt64 = field(metadata=LimitedIntCoder(UInt64))


@dataclass_json
@dataclass
class PacketLogsConfig:
    errorChannelId: UInt64 = field(metadata=LimitedIntCoder(UInt64))
    successChannelId: UInt64 = field(metadata=LimitedIntCoder(UInt64))
    guildId: UInt64 = field(metadata=LimitedIntCoder(UInt64))


@dataclass_json
@dataclass
class Config:
    token: str
    ownerId: UInt64 = field(metadata=LimitedIntCoder(UInt64))
    maxmind: MaxmindConfig
    mariadbDetails: MariaDBConfig
    server: ServerConfig
    packetLogs: PacketLogsConfig


type ValidStatusCode = Literal[-1, 200, 400, 403, 404, 405, 409, 500]
@dataclass
class Response:
    code: ValidStatusCode
    message: str

    def __init__(this, code: ValidStatusCode, message: str) -> None:
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
    NONE = 0
    AESGCM = 1 << 0
    CHACHAPOLY = 1 << 1
    MSGPACK = 1 << 3

class APIPayload(NamedTuple):
    dataOffset: UInt8
    requestType: UInt8
    flags: PacketFlags
    contentLen: UInt16

ServerAny = Union[AppCommand, AppCommandGroup]

type PresenceType = Literal["online", "offline", "idle", "dnd", "invisible", "streaming"]
type ActivityType = Literal["unknown", "playing", "streaming", "listening", "watching"]
type ColorSpace = Literal["rgb", "hsl", "okhsl", "oklab", "oklch"]
type ValidProtocol = Literal["TCP", "UDP"]

@dataclass_json
@dataclass
class Profile:
    presence: str = "online"
    activityType: int = -1
    activityName: str = ""

type FullCommand = tuple[Command, AppCommand]
type FullSubcommand = tuple[Command, AppCommandGroup]

class FakeInteraction:
    permissions: Permissions

    def __init__(self, permissions: Permissions):
        self.permissions = permissions

class TZCommand:
    STAFF_PERMS: Final[set[int]] = {Permissions.manage_guild.flag, Permissions.manage_roles.flag, Permissions.moderate_members.flag, Permissions.kick_members.flag}

    name: Final[str]
    description: Final[str]
    args: Final[dict[str, CommandParameter]]
    permissions: Final[int]
    commandId: Final[int]
    isOwnerOnly: Final[bool]

    def __init__(this, name: str, description: str, params: dict[str, CommandParameter], permissions: int, commandId: int, isOwnerOnly: bool = False) -> None:
        this.name = name
        this.description = description
        this.args = params
        this.commandId = commandId
        this.permissions = permissions
        this.isOwnerOnly = isOwnerOnly

    def getMention(this) -> str:
        return f"</{this.name}:{this.commandId}>"

    @staticmethod
    def _permissionWalker(command: Union[Command, Group]) -> int:
        perms = 0

        if command.default_permissions:
            perms |= command.default_permissions.value

        if command.parent:
            perms |= TZCommand._permissionWalker(command.parent)

        return int(perms)

    @staticmethod
    def _checkWalker(command: Union[Command, Group]) -> int:
        sign: bool = False
        permissions = 0

        def check(cmd: Command) -> int:
            nonlocal sign
            perms = 0
            for ch in cmd.checks:
                if ch.__name__ == "isOwner":
                    sign = True
                    continue

                try:
                    ch(FakeInteraction(permissions=Permissions(0)))
                except MissingPermissions as e:
                    missing = Permissions()

                    for name in e.missing_permissions:
                        setattr(missing, name, True)

                    perms |= missing.value

            return perms

        permissions |= check(command)
        if command.parent and isinstance(command.parent, Command):
            permissions |= TZCommand._checkWalker(command.parent)

        if sign:
            permissions |= (1 << 63)

        return int(permissions)

    @classmethod
    def fromAppCommand(cls, command: FullCommand) -> Self:
        return cls(command[0].name, command[0].description, command[0]._params, int(TZCommand._permissionWalker(command[0]) | (checks := TZCommand._checkWalker(command[0])) & ~(1 << 63)), int(command[1].id), bool(checks & (1 << 63)))

    @classmethod
    def fromAppSubcommand(cls, command: FullSubcommand) -> Self:
        return cls(command[1].qualified_name, command[0].description, command[0]._params, int(TZCommand._permissionWalker(command[0]) | (checks := TZCommand._checkWalker(command[0])) & ~(1 << 63)), int(command[1].parent.id), bool(checks & (1 << 63)))

    def prettyPrintPerms(this) -> Optional[str]:
        if this.permissions & Permissions.administrator.flag: return "administrator"

        return ", ".join([
                flagName.replace("_", " ").title()
                for flagName, flagVal in Permissions.VALID_FLAGS.items()
                if this.permissions & flagVal == 0
        ])

    def canBeExecutedBy(this, userPerms: Permissions):
        if this.permissions == 0: return True

        return this.permissions & userPerms.value

    def isStaff(this) -> bool:
        if this.isOwnerOnly: return True
        if not this.permissions: return False
        if this.permissions & Permissions.administrator.flag: return True

        for perm in TZCommand.STAFF_PERMS:
            if this.permissions & perm:
                return True

        return False

    def hasArgs(self) -> bool:
        return self.args is not None and len(self.args) > 0

class TimezoneRepr(NamedTuple):
    area: str
    city: str

    def stringify(this) -> str:
        return f"{this.area}/{this.city.replace(" ", "_")}"

    @classmethod
    def fromString(cls, tz: str) -> TimezoneRepr:
        if tz not in Constants.TIMEZONE_CHECK_SET:
            raise ValueError(f"Unknown timezone: {tz}")

        split = tz.split("/")
        return cls(split[0], split[1].replace("_", " "))

class TypedBytesIO(NamedTuple):
    contentType: str
    content: BytesIO

class FileAccessType(IntFlag):
    F_OK = 0
    R_OK = 4
    W_OK = 2
    X_OK = 1