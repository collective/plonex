from rich.logging import RichHandler

import logging


FORMAT = "%(message)s"
logging.basicConfig(
    level=logging.INFO, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

logger = logging.getLogger("plonex")
logger.setLevel(logging.INFO)
