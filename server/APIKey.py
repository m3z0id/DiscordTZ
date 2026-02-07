from enum import IntFlag
from typing import Self, Union

import jwt

from dtypes.Types import UInt64
from shared import Helpers


class APIPermissions(IntFlag):
    DISCORD_ID = 1 << 0
  # TZBOT_ALIAS = 1 << 1
    MINECRAFT_UUID = 1 << 2
    UUID_POST = 1 << 3
    IP_ADDRESS = 1 << 4
  # TZ_OVERRIDES_GET = 1 << 5
  # TZ_OVERRIDES_POST = 1 << 6
  # COMMAND_API = 1 << 7
  # IMAGE_API = 1 << 8

class APIKey:
    def __init__(this, owner: Union[UInt64, int], permissions: Union[UInt64, int], validUntil: str = "INFINITE", keyId: str = Helpers.generateCharSequence(32)) -> None:
        if isinstance(owner, int):
            this.owner = UInt64(owner)()
        else:
            this.owner = owner()

        if isinstance(permissions, int):
            this.permissions = UInt64(permissions)()
        else:
            this.permissions = permissions()

        this.validUntil = validUntil
        this.keyId = keyId

    def hasPermissions(this, *permissions: APIPermissions) -> bool:
        required = 0
        for perm in permissions:
            required |= perm.value  # accumulate required bits

        return (this.permissions & required) == required

    def prettyPrintPerms(this) -> list[str]:
        return [flag.name for flag in APIPermissions if APIPermissions(this.permissions) & flag and flag.name]

    def toJWT(this, key: str) -> str:
        return jwt.encode(this.__dict__, key, algorithm="HS256")

    @classmethod
    def fromJWT(cls, token: str, key: str) -> Self:
        data = jwt.decode(token, key, algorithms=["HS256"])
        return cls(**data)