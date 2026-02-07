import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiomysql
from aiomysql.utils import _PoolContextManager

from dtypes import MariaDBConfig

log = logging.getLogger(__name__)

class MDBSource:
    def __init__(this, config: MariaDBConfig) -> None:
        this.config = config
        this._initialized = False
        this._pool: _PoolContextManager

    @asynccontextmanager
    async def getConn(this) -> AsyncGenerator[aiomysql.Connection]:
        if not this._initialized:
            raise RuntimeError("MDB is not initialized!")
        conn = await this._pool.acquire()
        try:
            yield conn
        finally:
            await conn.close()

    async def asyncInit(this, statements: list[str]) -> None:
        if this._initialized: return
        try:
            this._pool = await aiomysql.create_pool(
                **this.config.__dict__,
                loop=asyncio.get_event_loop()
            )
        except Exception as e:
            log.fatal(f"MDB is not available! {e!s}")
            return

        async with this.getConn() as conn, conn.cursor() as cur:
            for statement in statements:
                await cur.execute(statement)

        this._initialized = True