import mariadb
import os
from logger import Logger

class Database:
    conn: mariadb.Connection
    tableName: str

    def __init__(this, connectionDetails: dict):
        this.conn = mariadb.connect(
            database=connectionDetails.get("database"),
            user=connectionDetails.get("user"),
            password=connectionDetails.get("password"),
            host=connectionDetails.get("host"),
            port=int(connectionDetails.get("port")),
            autocommit=bool(connectionDetails.get("autocommit"))
        )
        this.tableName = connectionDetails.get("tableName")
        
    def set(this, userId: int, timezone: str) -> bool:
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"INSERT into {this.tableName} (user, timezone) VALUES (%s, %s) ON DUPLICATE KEY UPDATE timezone = %s"

        data: tuple[int, str, str] = (userId, timezone.replace(" ", "_"), timezone.replace(" ", "_"))

        try:
            cursor.execute(query, data)
            conn.commit()
            
            return True
        
        except mariadb.Error as e:
            Logger.error(f"Error while writing data to database: {e}")
            return False
        
    def get(this, userId: int) -> str | None:
        conn: mariadb.Connection = this.conn
        cursor: mariadb.Cursor = conn.cursor(prepared=True)
        query: str = f"SELECT timezone from {this.tableName} WHERE user = %s"
        data: list[int] = [userId]

        try:
            cursor.execute(query, data)
            conn.commit()

            result = cursor.fetchone()

            if(result):
                return str(result[0])
            else:
                return this.defaultTz()

        except mariadb.Error as e:
            Logger.error(e)
            return None

    def defaultTz(this) -> str:
        temp: list[str] = os.readlink("/etc/localtime").split("/")
        return f"{temp[-2]}/{temp[-1]}"
            