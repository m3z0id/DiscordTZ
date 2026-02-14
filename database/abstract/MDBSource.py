import asyncio
import logging
import warnings
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiomysql
import pymysql
from aiomysql.utils import _PoolContextManager

from dtypes import MariaDBConfig

log = logging.getLogger(__name__)

class MDBSource:
    def __init__(this, config: MariaDBConfig) -> None:
        this.config = config
        this._initialized = False
        this._pool: aiomysql.Pool

    @asynccontextmanager
    async def getConn(this) -> AsyncGenerator[aiomysql.Connection]:
        if not this._pool:
            raise RuntimeError("MDB is not initialized!")

        async with this._pool.acquire() as conn:
            yield conn

    async def asyncInit(this, statements: list[str]) -> None:
        if this._initialized: return
        try:
            this._pool = await aiomysql.create_pool(**this.config.__dict__)
        except Exception as e:
            log.fatal(f"MDB is not available! {e!s}")
            return

        this._initialized = True
        async with this.getConn() as conn, conn.cursor() as cur:
            try:
                for statement in statements:
                    await cur.execute(statement)
            except pymysql.OperationalError as e:
                warnings.warn(f"Failed to execute query: {e!s}")