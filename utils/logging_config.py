"""Centralized logging configuration with enhanced observability."""
import logging
import sys
from pathlib import Path
from utils.structured_logger import StructuredLogger
from utils.metrics import MetricsCollector
from utils.audit_logger import audit_logger
import os

def setup_logging(app_name: str = "legal-portal", level: str = None):
    """Setup application-wide logging with observability features.
    
    Args:
        app_name: Application name for identification
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    
    # Determine log level
    log_level = level or os.getenv('LOG_LEVEL', 'INFO')
    
    # Create logs directory structure
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    (log_dir / "audit").mkdir(exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(message)s',
        handlers=[]
    )
    
    # Disable noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    logging.getLogger('streamlit').setLevel(logging.WARNING)
    
    # Initialize metrics collector
    metrics = MetricsCollector()
    
    # Create loggers for different components
    loggers = {
        'app': StructuredLogger('app', log_level),
        'auth': StructuredLogger('auth', log_level),
        'api': StructuredLogger('api', log_level),
        'database': StructuredLogger('database', log_level),
        'security': StructuredLogger('security', log_level),
        'performance': StructuredLogger('performance', log_level),
        'document': StructuredLogger('document', log_level),
        'email': StructuredLogger('email', log_level),
        'ai': StructuredLogger('ai', log_level),
        'video': StructuredLogger('video', log_level),
        'audio': StructuredLogger('audio', log_level)
    }
    
    # Log startup
    loggers['app'].info(
        "Application logging initialized",
        app_name=app_name,
        log_level=log_level,
        environment=os.getenv('ENVIRONMENT', 'development'),
        version=os.getenv('APP_VERSION', '1.0.0')
    )
    
    return loggers

def get_logger(name: str, component: str = 'app') -> StructuredLogger:
    """Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        component: Component category (app, auth, api, etc.)
    
    Returns:
        Configured structured logger instance
    """
    # Get or create the logger
    return StructuredLogger(name, os.getenv('LOG_LEVEL', 'INFO'))

def get_module_logger(module_name: str) -> StructuredLogger:
    """Get a logger for a specific module with enhanced context.
    
    Args:
        module_name: Name of the module (e.g., __name__)
    
    Returns:
        Logger with module context
    """
    # Extract component from module name
    parts = module_name.split('.')
    
    # Map module paths to components
    if 'auth' in parts or 'authentication' in parts:
        component = 'auth'
    elif 'api' in parts or 'endpoint' in parts:
        component = 'api'
    elif 'security' in parts or 'validation' in parts:
        component = 'security'
    elif 'document' in parts or 'processor' in parts:
        component = 'document'
    elif 'email' in parts or 'generator' in parts:
        component = 'email'
    elif 'ai' in parts or 'openai' in parts or 'analyzer' in parts:
        component = 'ai'
    elif 'video' in parts:
        component = 'video'
    elif 'audio' in parts:
        component = 'audio'
    else:
        component = 'app'
    
    return get_logger(module_name, component)

# Initialize logging on import
loggers = setup_logging()

# Export commonly used loggers
app_logger = loggers['app']
auth_logger = loggers['auth']
api_logger = loggers['api']
security_logger = loggers['security']
document_logger = loggers['document']
email_logger = loggers['email']
ai_logger = loggers['ai']
performance_logger = loggers['performance']

# Convenience functions for common logging patterns
def log_api_request(endpoint: str, method: str, user: str = None, **kwargs):
    """Log API request with metrics."""
    api_logger.info(
        f"API request: {method} {endpoint}",
        endpoint=endpoint,
        method=method,
        user=user,
        **kwargs
    )
    MetricsCollector.record_counter('api.requests', tags={'method': method, 'endpoint': endpoint})

def log_api_response(endpoint: str, method: str, status_code: int, duration: float, **kwargs):
    """Log API response with metrics."""
    api_logger.info(
        f"API response: {method} {endpoint} - {status_code}",
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        duration_ms=duration * 1000,
        **kwargs
    )
    MetricsCollector.record_timing('api.response_time', duration, tags={'endpoint': endpoint})
    
    if status_code >= 400:
        MetricsCollector.record_error('api', tags={'endpoint': endpoint, 'status': status_code})

def log_document_processing(document_name: str, action: str, user: str, success: bool = True, **kwargs):
    """Log document processing with audit trail."""
    document_logger.info(
        f"Document {action}: {document_name}",
        document=document_name,
        action=action,
        user=user,
        success=success,
        **kwargs
    )
    
    # Audit logging for compliance
    audit_logger.log_document_processing(
        user=user,
        document_name=document_name,
        action=action,
        success=success,
        **kwargs
    )
    
    # Metrics
    MetricsCollector.record_counter(f'documents.{action}', tags={'success': str(success)})

def log_authentication(username: str, action: str, success: bool, ip_address: str = None, **kwargs):
    """Log authentication events with audit trail."""
    auth_logger.info(
        f"Authentication {action}: {username}",
        username=username,
        action=action,
        success=success,
        ip_address=ip_address,
        **kwargs
    )
    
    # Audit logging for compliance
    audit_logger.log_authentication(
        username=username,
        action=action,
        success=success,
        ip_address=ip_address,
        **kwargs
    )
    
    # Metrics
    MetricsCollector.record_counter(f'auth.{action}', tags={'success': str(success)})

def log_ai_processing(operation: str, model: str, tokens: int = None, **kwargs):
    """Log AI processing operations."""
    ai_logger.info(
        f"AI processing: {operation}",
        operation=operation,
        model=model,
        tokens=tokens,
        **kwargs
    )
    
    # Metrics
    MetricsCollector.record_counter('ai.operations', tags={'operation': operation, 'model': model})
    if tokens:
        MetricsCollector.record_gauge('ai.tokens_used', tokens, tags={'model': model})

def log_performance_metric(operation: str, duration: float, **kwargs):
    """Log performance metrics."""
    performance_logger.info(
        f"Performance: {operation} took {duration*1000:.2f}ms",
        operation=operation,
        duration_ms=duration * 1000,
        **kwargs
    )
    
    # Record metric
    MetricsCollector.record_timing(operation, duration)

def log_security_event(event_type: str, severity: str, description: str, **kwargs):
    """Log security events with audit trail."""
    security_logger.warning(
        f"Security event: {event_type}",
        event_type=event_type,
        severity=severity,
        description=description,
        **kwargs
    )
    
    # Audit logging
    audit_logger.log_security_event(
        event_type=event_type,
        severity=severity,
        description=description,
        **kwargs
    )
    
    # Metrics
    MetricsCollector.record_counter('security.events', tags={'type': event_type, 'severity': severity})

# Export all components for direct use
__all__ = [
    'setup_logging',
    'get_logger',
    'get_module_logger',
    'app_logger',
    'auth_logger',
    'api_logger',
    'security_logger',
    'document_logger',
    'email_logger',
    'ai_logger',
    'performance_logger',
    'log_api_request',
    'log_api_response',
    'log_document_processing',
    'log_authentication',
    'log_ai_processing',
    'log_performance_metric',
    'log_security_event',
    'audit_logger',
    'MetricsCollector'
]