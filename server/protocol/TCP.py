import asyncio
from typing import override, TYPE_CHECKING

from server.protocol.Client import Client
from dtypes import PacketFlags, ValidProtocol

if TYPE_CHECKING:
    from server.APIServer import APIServer

class TCPClient(Client):
    def __init__(this, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, aesKey: bytes, server: APIServer, flags: PacketFlags = 0) -> None:
        this.reader: asyncio.StreamReader = reader
        this.writer: asyncio.StreamWriter = writer
        super().__init__(this.writer.get_extra_info("peername"), aesKey, flags, server)

    async def send(this, data: dict) -> None:
        finalData = this._applyFlags(data)
        this.writer.write(finalData)

        await this.writer.drain()
        this.writer.close()
        await this.writer.wait_closed()

    @override
    def getProtocolStringRepr(this) -> ValidProtocol:
        return "TCP"