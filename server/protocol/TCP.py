import asyncio

from server.protocol.Client import Client
from shared.Types import PacketFlags


class TCPClient(Client):
    def __init__(this, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, aesKey: bytes, server: "APIServer", flags: PacketFlags = 0) -> None:
        this.reader: asyncio.StreamReader = reader
        this.writer: asyncio.StreamWriter = writer
        super().__init__(this.writer.get_extra_info("peername"), aesKey, flags, server)

    async def send(this, data: bytes) -> None:
        finalData = await this._applyFlags(data)
        this.writer.write(finalData)

        await this.writer.drain()
        this.writer.close()
        await this.writer.wait_closed()
