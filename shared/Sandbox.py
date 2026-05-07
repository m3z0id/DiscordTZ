import logging
from shared import SYSTEM_READ, SYSTEM_RW
from shared.Constants import ROOT_DIR

log = logging.getLogger(__name__)
def applySandbox() -> None:
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
    rs.allow(str(ROOT_DIR), rules=handled)

    for p in SYSTEM_READ:
        rs.allow(p, rules=ro)

    for p in SYSTEM_RW:
        rs.allow(p, rules=handled)

    rs.apply()
    log.info("Sandbox applied.")
