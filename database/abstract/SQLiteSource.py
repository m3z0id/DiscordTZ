from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

class SQLiteSource:
    def __init__(this, path: Path) -> None:
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

        this.path.parent.mkdir(parents=True, exist_ok=True)
        async with this.getConn() as db:
            await db.execute("PRAGMA foreign_keys = ON")
            for statement in statements:
                await db.execute(statement)

        this._initialized = True