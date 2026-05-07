import warnings
from pathlib import Path
from typing import Final

from shared import Helpers, MODULES_DIR


class ModuleBlacklist:
    _path: Final[Path]
    _blacklisted: set[str]

    def __init__(this, blacklistPath: Path):
        this._path = blacklistPath
        this._blacklisted = set()
        this.reload()

    def reload(this) -> None:
        if not Helpers.isFileRW(this._path):
            this._path.touch(exist_ok=True)
            this._blacklisted = set()
            return

        with this._path.open("r") as f:
            contents = f.read().strip()

        this._blacklisted.clear()
        if len(contents) < 1: return

        temp = contents.split(";")
        for item in temp:
            item = item.strip()
            if len(item) < 1: continue
            if not Helpers.isFileRW(MODULES_DIR / f"mod{item}.py"):
                warnings.warn(f"Module {item} doesn't exist!")

            this._blacklisted.add(item)

    def dump(this) -> None:
        if len(this._blacklisted) == 0: return

        with this._path.open("w") as f:
            f.write(";".join(this._blacklisted))

    def isBlacklisted(this, modName: str) -> bool:
        return modName in this._blacklisted

    def add(this, modName: str) -> None:
        if this._blacklisted.__contains__(modName):
            warnings.warn("This module is already blacklisted!")
            return

        this._blacklisted.add(modName)
        this.dump()

    def remove(this, modName: str) -> None:
        try:
            this._blacklisted.remove(modName)
        except KeyError:
            warnings.warn("This module is not blacklisted!")
        finally:
            this.dump()