"""
Logging configuration for CARD Catalog scrapers
"""
import logging
import sys
from datetime import datetime


def setup_logger(name: str, log_file: str = None, level: int = logging.INFO, clear: bool = False) -> logging.Logger:
    """
    Set up a logger with both file and console handlers
    
    Args:
        name: Name of the logger (usually __name__)
        log_file: Optional log file path. If None, uses scraper_{timestamp}.log
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        clear: If True and log_file is specified, clears the existing log file before logging
    
    Returns:
        Configured logger instance
    """
    root = logging.getLogger()
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if already configured
    if root.handlers:
        return logger

    root.setLevel(logging.DEBUG)  # let handlers decide their own level

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        mode = 'w' if clear else 'a'
        file_handler = logging.FileHandler(log_file, mode=mode, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    return logger


def get_default_log_file(prefix: str = "scraper") -> str:
    """Generate a timestamped log filename in the project logs/ directory."""
    import os
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return os.path.join(logs_dir, f"{prefix}_{timestamp}.log")
