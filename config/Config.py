from dataclasses import dataclass
from typing import Annotated

from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class MaxmindConfig:
    accountId: int
    token: str


from typing import TypedDict, ReadOnly

type MDBParams = MariaDBConnectionParams


class MariaDBConnectionParams(TypedDict):
    host: ReadOnly[str]
    user: ReadOnly[str]
    password: ReadOnly[str]
    db: ReadOnly[str]
    port: ReadOnly[int]
    autocommit: ReadOnly[bool]


@dataclass_json
@dataclass
class MariaDBConfig:
    database: str
    user: str
    password: str
    host: str
    port: int
    autocommit: bool

    def to_connection_params(self) -> MDBParams:
        return {
            "db": self.database,
            "host": self.host,
            "user": self.user,
            "password": self.password,
            "port": self.port,
            "autocommit": self.autocommit,
        }


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
    whoToPing: int


@dataclass_json
@dataclass
class Config:
    token: str
    ownerId: int
    maxmind: MaxmindConfig
    mariadbDetails: MariaDBConfig
    server: ServerConfig
    packetLogs: PacketLogsConfig
