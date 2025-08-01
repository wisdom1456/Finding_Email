from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class TaskStatus(str, Enum):
    """Enum for task status values."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskInitResponse(BaseModel):
    """Response model for task initialization."""
    task_id: str = Field(..., description="Unique identifier for the task")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current status of the task")
    message: str = Field(default="Task created successfully", description="Status message")
    created_at: datetime = Field(default_factory=datetime.now, description="Task creation timestamp")

class TaskStatusResponse(BaseModel):
    """Response model for task status queries."""
    task_id: str = Field(..., description="Unique identifier for the task")
    status: TaskStatus = Field(..., description="Current status of the task")
    progress: Optional[int] = Field(None, description="Progress percentage (0-100)")
    current_step: Optional[str] = Field(None, description="Description of current processing step")
    message: Optional[str] = Field(None, description="Status message or error details")
    created_at: datetime = Field(..., description="Task creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")