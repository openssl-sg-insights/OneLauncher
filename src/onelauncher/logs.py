import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from platform import platform

import onelauncher
from onelauncher import config


class Logger():
    def __init__(self, logs_dir: Path, log_name: str) -> None:
        """
        Args:
            logs_dir (Path): Directory to put log in.
            log_name (str): Name of log. Should not include file extension.
        """
        self.logger = self.setup_logging(logs_dir, log_name)
        self.log_basic_info()

    def handle_uncaught_exceptions(self, exc_type, exc_value, exc_traceback):
        """Handler for uncaught exceptions that will write to the logs"""
        if issubclass(exc_type, KeyboardInterrupt):
            # call the default excepthook saved at __excepthook__
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        self.logger.critical(
            "Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback)
        )

    def setup_logging(self, logs_dir: Path, log_name: str, file_logging_level=logging.INFO,
                      stream_logging_level=logging.WARNING) -> logging.Logger:
        """Initializes logging and logger object

        Args:
            log_dir (Path): Directory to put log in
            log_name (str): Name of log. Should not include file extension.
        """
        # Make sure logs dir exists
        logs_dir.mkdir(exist_ok=True, parents=True)

        # Create or get custom logger
        logger = logging.getLogger(log_name)

        # This is for the logger globally. Different handlers
        # attached to it have their own levels.
        logger.setLevel(logging.DEBUG)

        # Create handlers
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(stream_logging_level)

        log_file = logs_dir/f"{log_name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            mode="a",
            maxBytes=10 * 1024 * 1024,
            backupCount=2,
            encoding=None,
            delay=0,
        )
        file_handler.setLevel(file_logging_level)

        # Create formatters and add it to handlers
        stream_format = logging.Formatter(
            "%(module)s - %(levelname)s - %(message)s"
        )
        stream_handler.setFormatter(stream_format)
        file_format = logging.Formatter(
            "%(asctime)s - %(module)s - %(levelname)s - %(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_format)

        # Add handlers to the logger
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

        # Setup handling of uncaught exceptions
        sys.excepthook = self.handle_uncaught_exceptions

        return logger

    def log_basic_info(self):
        self.logger.info("Logging started")
        self.logger.info(f"{onelauncher.__title__}: {onelauncher.__version__}")
        self.logger.info(platform())

def setup_application_logging():
    """Create main logger configured for running application"""
    Logger(config.platform_dirs.user_log_path, "main")
