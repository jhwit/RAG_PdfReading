"""Logging configuration."""
import logging
import sys
from datetime import datetime


def setup_logger(name: str = "rag_kb") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        # File handler
        file_handler = logging.FileHandler(f"logs/app_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
