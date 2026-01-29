import base64
import json
import random
import string
from enum import IntFlag

from shared.Helpers import Helpers


class ApiPermissions(IntFlag):
    DISCORD_ID = 1 << 0
  # TZBOT_ALIAS = 1 << 1
    MINECRAFT_UUID = 1 << 2
    UUID_POST = 1 << 3
    IP_ADDRESS = 1 << 4
  # TZ_OVERRIDES_GET = 1 << 5
  # TZ_OVERRIDES_POST = 1 << 6
  # COMMAND_API = 1 << 7
  # IMAGE_API = 1 << 8


class ApiKey:
    def __init__(
        this,
        owner: int,
        permissions: int,
        validUntil: str = "INFINITE",
        keyId: str = "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(32)),
    ) -> None:
        this.owner = owner
        this.permissions = permissions
        this.validUntil = validUntil
        this.keyId = keyId

    def hasPermissions(this, *permissions: ApiPermissions) -> bool:
        required = ApiPermissions(0)
        for perm in permissions:
            required |= perm

        return (ApiPermissions(this.permissions) & required) == required

    def prettyPrintPerms(this) -> list[str]:
        return [flag.name for flag in ApiPermissions if ApiPermissions(this.permissions) & flag and flag.name]

    def toDbForm(this) -> str:
        return (
            base64.encodebytes(Helpers.AESCBCEncrypt(json.dumps(this.__dict__, separators=(",", ":")).encode(), str(Helpers.tzBot.config.server.apiKeysKey).encode()))
            .decode()
            .replace("\n", "")
        )

    @classmethod
    def fromDbForm(cls, dbFormKey: str):  # noqa: ANN206
        data = json.loads(Helpers.AESCBCDecrypt(base64.decodebytes(dbFormKey.encode()), str(Helpers.tzBot.config.server.apiKeysKey).encode()))
        return cls(**data)

    def __str__(this) -> str:
        return f"owner={this.owner}; permissions={', '.join(this.prettyPrintPerms())}({this.permissions}); validUntil={this.validUntil}"
