import logging
from pathlib import Path

log = logging.getLogger(__name__)

_SYSTEM_READ = [
    "/usr/lib",
    "/usr/lib64",
    "/etc",
    "/usr/share",
]

_SYSTEM_RW = [
    "/tmp",
]


def apply_sandbox() -> None:
    try:
        from landlock import FSAccess, Ruleset  # type: ignore[import-untyped]
    except ImportError:
        log.warning("Skipping sandboxing: landlock not available.")
        return

    handled = (
        FSAccess.READ_FILE
        | FSAccess.WRITE_FILE
        | FSAccess.TRUNCATE
        | FSAccess.READ_DIR
        | FSAccess.REMOVE_FILE
        | FSAccess.REMOVE_DIR
        | FSAccess.MAKE_REG
        | FSAccess.MAKE_DIR
        | FSAccess.MAKE_SYM
        | FSAccess.REFER
    )
    ro = FSAccess.READ_FILE | FSAccess.READ_DIR

    rs = Ruleset(handled)

    rs.allow(str(Path.cwd()), rules=handled)

    for p in _SYSTEM_READ:
        rs.allow(p, rules=ro)

    for p in _SYSTEM_RW:
        rs.allow(p, rules=handled)

    rs.apply()
    log.info("Sandbox applied.")
