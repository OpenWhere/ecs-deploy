import logging
import sys

import os

logging.basicConfig(format="%(asctime)s %(levelname)s [%(threadName)s] - %(message)s",
                    stream=sys.stdout,
                    level=(os.getenv("LOG_LEVEL", "DEBUG")))

__version__ = '2.0.0'
