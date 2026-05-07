import json
from ipaddress import IPv4Address
from typing import TYPE_CHECKING

from dtypes import UInt16, PacketFlags, ValidProtocol
from shared import Helpers

if TYPE_CHECKING:
    from server.APIServer import APIServer

class Client:
    ip: IPv4Address
    port: UInt16
    aesKey: bytes
    flags: PacketFlags
    server: APIServer

    def __init__(this, ipAddress: tuple[str, int], aesKey: bytes, flags: PacketFlags, server: APIServer) -> None:
        this.ip: IPv4Address = IPv4Address(ipAddress[0])
        this.port = UInt16(ipAddress[1])
        this.aesKey = aesKey
        this.flags = flags
        this.server = server

    def _applyFlags(this, data: dict):
        # Pattern + headerLen + flags + contentLen
        headerLen = 2 + 1 + 1 + 2
        header = b"tz" + headerLen.to_bytes(1, "big", signed=False) + this.flags.to_bytes(1, "big", signed=False)

        if this.flags & PacketFlags.MSGPACK:
            rawBytes = Helpers.jsonToMsgpack(data)
        else:
            rawBytes = json.dumps(data).encode()

        if (this.flags & PacketFlags.CHACHAPOLY) or (this.flags & PacketFlags.AESGCM):
            header += int(len(rawBytes) + 28).to_bytes(2, "big", signed=False)
            if this.flags & PacketFlags.CHACHAPOLY:
                rawBytes = Helpers.ChaCha20Encrypt(rawBytes, this.aesKey, header)
            elif this.flags & PacketFlags.AESGCM:
                rawBytes = Helpers.AESEncrypt(rawBytes, this.aesKey, header)

        else:
            header += len(rawBytes).to_bytes(2, "big", signed=False)

        return header + rawBytes

    def getProtocolStringRepr(this) -> ValidProtocol:
        pass

    async def send(this, data: dict) -> None:
        pass

    async def close(this) -> None:
        pass
