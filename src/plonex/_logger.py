from rich.logging import RichHandler

import logging


FORMAT: str = "%(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=FORMAT,
    datefmt="[%X]",
    handlers=[
        RichHandler(
            markup=True,
            show_path=False,
            show_time=False,
        ),
    ],
)

logger: logging.Logger = logging.getLogger("plonex")
logger.setLevel(logging.INFO)

_warning_once_keys: set[str] = set()


def warning_once(
    logger_instance: logging.Logger,
    key: str,
    message: str,
    *args,
) -> bool:
    """Log a warning once for the provided key.

    Returns True when the warning is emitted, False when skipped.
    """
    if key in _warning_once_keys:
        return False
    _warning_once_keys.add(key)
    logger_instance.warning(message, *args)
    return True
