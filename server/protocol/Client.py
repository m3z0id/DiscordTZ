from ipaddress import IPv4Address

from shared import Helpers
from dtypes import UInt16, PacketFlags


class Client:
    ip: IPv4Address
    port: UInt16
    aesKey: bytes
    flags: PacketFlags
    server: "APIServer"

    def __init__(this, ipAddress: tuple[str, int], aesKey: bytes, flags: PacketFlags, server: "APIServer") -> None:
        this.ip: IPv4Address = IPv4Address(ipAddress[0])
        this.port = UInt16(ipAddress[1])
        this.aesKey = aesKey
        this.flags = flags
        this.server = server

    async def _applyFlags(this, data: bytes):
        # Pattern + headerLen + flags + contentLen
        headerLen = 2 + 1 + 1 + 2
        header = (b"tz" + headerLen.to_bytes(1, "big", signed=False) + this.flags.to_bytes(1, "big", signed=False))

        if this.flags & PacketFlags.MSGPACK:
            data = Helpers.jsonToMsgpack(data)
        if this.flags & PacketFlags.GUNZIP:
            data = Helpers.compressGzip(data)

        if this.flags & PacketFlags.CHACHAPOLY or this.flags | PacketFlags.AESGCM:
            header += int(len(data) + 28).to_bytes(2, "big", signed=False)
            if this.flags & PacketFlags.CHACHAPOLY:
                data = Helpers.ChaCha20Encrypt(data, this.aesKey, header)
            elif this.flags & PacketFlags.AESGCM:
                data = Helpers.AESEncrypt(data, this.aesKey, header)

        else:
            header += len(data).to_bytes(2, "big", signed=False)

        return header + data

    async def send(this, data: bytes) -> None:
        pass

    async def close(this) -> None:
        pass
