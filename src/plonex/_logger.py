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
