"""
Centralized Logging Configuration

This module provides a centralized logging configuration for the Legal Document Analysis Portal.
It sets up structured JSON logging for production-grade observability and debugging.

Features:
- JSON-formatted logs for machine readability
- Timestamp, log level, logger name, and message included
- Configurable log levels
- Production-ready structured logging
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Outputs logs in JSON format with consistent structure:
    {
        "timestamp": "2025-08-09T14:20:00.000Z",
        "level": "INFO",
        "logger": "backend_logic.email_generation.services.json_processing_service",
        "message": "Processing started",
        "module": "json_processing_service",
        "function": "generate_html_letter"
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as JSON.
        
        Args:
            record: The log record to format
            
        Returns:
            JSON-formatted log string
        """
        # Create the base log entry
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": getattr(record, 'module', record.name.split('.')[-1]),
            "function": getattr(record, 'funcName', record.funcName)
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add any extra fields from the record
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'lineno', 'funcName', 'created', 
                          'msecs', 'relativeCreated', 'thread', 'threadName', 
                          'processName', 'process', 'getMessage', 'exc_info', 
                          'exc_text', 'stack_info'):
                log_entry[key] = value
        
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO", enable_console: bool = True) -> None:
    """
    Set up centralized structured logging for the application.
    
    This function configures the root logger with JSON formatting and sets up
    handlers for console output. It should be called once at application startup.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_console: Whether to enable console logging
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create JSON formatter
    json_formatter = JSONFormatter()
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set root logger level
    root_logger.setLevel(numeric_level)
    
    # Create console handler if enabled
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(json_formatter)
        root_logger.addHandler(console_handler)
    
    # Configure specific loggers to prevent double logging
    # Disable urllib3 info logs to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    
    # Log the logging configuration
    logger = logging.getLogger(__name__)
    logger.info(
        "Structured logging configured",
        extra={
            "level": level,
            "console_enabled": enable_console,
            "formatter": "JSON"
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    This is a convenience function that returns a logger instance.
    The logger will use the centralized configuration set up by setup_logging().
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Convenience function for getting module-specific loggers
def get_module_logger(module_name: str) -> logging.Logger:
    """
    Get a logger for a specific module with enhanced context.
    
    Args:
        module_name: Name of the module (e.g., __name__)
        
    Returns:
        Logger with module context
    """
    logger = logging.getLogger(module_name)
    
    # Add a filter to include module name in extra context
    class ModuleFilter(logging.Filter):
        def __init__(self, module_name: str):
            super().__init__()
            self.module_name = module_name.split('.')[-1]
            
        def filter(self, record: logging.LogRecord) -> bool:
            record.module = self.module_name
            return True
    
    logger.addFilter(ModuleFilter(module_name))
    return logger