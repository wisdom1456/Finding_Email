"""Distributed tracing support."""
from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional


# Tracing context
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_id_var: ContextVar[str] = ContextVar("span_id", default="")
parent_span_id_var: ContextVar[str] = ContextVar("parent_span_id", default="")

class Span:
    """Represents a trace span."""
    
    def __init__(self, name: str, operation: str, tags: Optional[Dict] = None):
        """Initialize span."""
        self.span_id = str(uuid.uuid4())
        self.trace_id = trace_id_var.get() or str(uuid.uuid4())
        self.parent_span_id = span_id_var.get()
        self.name = name
        self.operation = operation
        self.start_time = datetime.utcnow()
        self.end_time = None
        self.tags = tags or {}
        self.logs = []
        self.status = "running"
        
        # Set context
        trace_id_var.set(self.trace_id)
        parent_span_id_var.set(self.parent_span_id)
        span_id_var.set(self.span_id)
    
    def log(self, message: str, **kwargs):
        """Add log to span."""
        self.logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
            "fields": kwargs
        })
    
    def set_tag(self, key: str, value: Any):
        """Set span tag."""
        self.tags[key] = value
    
    def finish(self, status: str = "success"):
        """Finish span."""
        self.end_time = datetime.utcnow()
        self.status = status
        self._export()
    
    def _export(self):
        """Export span data."""
        span_data = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "operation": self.operation,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": (self.end_time - self.start_time).total_seconds() * 1000 if self.end_time else None,
            "tags": self.tags,
            "logs": self.logs,
            "status": self.status
        }
        
        # Ensure logs directory exists
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Export to file (can be replaced with Jaeger/Zipkin)
        with open(log_dir / "traces.json", "a") as f:
            f.write(json.dumps(span_data) + "\n")

def trace(operation: str):
    """Decorator for tracing functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            span = Span(
                name=func.__name__,
                operation=operation,
                tags={"function": func.__name__, "module": func.__module__}
            )
            
            try:
                result = func(*args, **kwargs)
                span.finish(status="success")
                return result
            except Exception as e:
                span.log("Error occurred", error=str(e))
                span.set_tag("error", True)
                span.finish(status="error")
                raise
        
        return wrapper
    return decorator
