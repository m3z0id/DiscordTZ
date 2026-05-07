import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

from shared import Helpers

log = logging.getLogger(__name__)
class SQLiteSource:
    new: bool = False

    def __init__(this, path: Path) -> None:
        if not Helpers.isFileRW(path):
            log.warning(f"SQLiteSource path {path} doesn't exist, creating...")
            this.new = True

        this.path = path
        this._initialized = False

    @asynccontextmanager
    async def getConn(this) -> AsyncGenerator[aiosqlite.Connection]:
        conn = await aiosqlite.connect(this.path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    async def asyncInit(this, statements: list[str]) -> None:
        if this._initialized: return

        if this.new:
            this.path.parent.mkdir(parents=True, exist_ok=True)
            async with this.getConn() as db:
                await db.execute("PRAGMA foreign_keys = ON")
                for statement in statements:
                    await db.execute(statement)

        this._initialized = True
        this.new = False