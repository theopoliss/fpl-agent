import sys
from pathlib import Path
from loguru import logger
from src.utils.config import config


def setup_logging():
    """Configure logging for the application"""
    
    # Remove default logger
    logger.remove()
    
    # Console logging
    if config.logging.console_enabled:
        logger.add(
            sys.stdout,
            format=config.logging.format,
            level=config.logging.level,
            colorize=True,
            enqueue=True
        )
    
    # File logging
    if config.logging.file_enabled:
        # Ensure logs directory exists
        Path("logs").mkdir(exist_ok=True)
        
        logger.add(
            config.logging.file_path,
            format=config.logging.format,
            level=config.logging.level,
            rotation=config.logging.rotation,
            retention=config.logging.retention,
            compression="zip",
            enqueue=True
        )
    
    # Add custom log levels
    logger.level("DECISION", no=35, color="<yellow>")
    logger.level("TRANSFER", no=36, color="<green>")
    logger.level("CHIP", no=37, color="<magenta>")
    
    return logger


# Initialize logger
app_logger = setup_logging()


class LogContext:
    """Context manager for structured logging"""
    
    def __init__(self, context_name: str, **kwargs):
        self.context_name = context_name
        self.context_data = kwargs
        
    def __enter__(self):
        app_logger.info(f"Starting {self.context_name}", **self.context_data)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            app_logger.error(
                f"Error in {self.context_name}: {exc_val}",
                exc_info=True,
                **self.context_data
            )
        else:
            app_logger.info(f"Completed {self.context_name}", **self.context_data)


def log_decision(decision_type: str, **details):
    """Log a decision made by the agent"""
    app_logger.log("DECISION", f"{decision_type}: {details}")


def log_transfer(player_in: str, player_out: str, **details):
    """Log a transfer decision"""
    app_logger.log(
        "TRANSFER",
        f"Transfer: {player_out} -> {player_in}",
        **details
    )


def log_chip_usage(chip: str, gameweek: int, **details):
    """Log chip usage"""
    app_logger.log(
        "CHIP",
        f"Using {chip} in GW{gameweek}",
        **details
    )