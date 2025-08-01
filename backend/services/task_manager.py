import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from backend.utils.async_models import TaskStatus, TaskStatusResponse
from backend.utils.data_models import CaseResults


class TaskManager:
    """Manages asynchronous tasks and their results in memory."""

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def create_task(self) -> str:
        """Creates a new task and returns its ID."""
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "status": TaskStatus.PENDING,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "result": None,
            "progress": 0,
            "current_step": "Task initiated",
        }
        print(f"Task created with ID: {task_id}")
        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskStatusResponse]:
        """Retrieves the status of a specific task."""
        task = self.tasks.get(task_id)
        if not task:
            return None
        return TaskStatusResponse(
            task_id=task_id,
            status=task["status"],
            progress=task["progress"],
            current_step=task["current_step"],
            created_at=task["created_at"],
            updated_at=task["updated_at"],
        )

    def update_task_progress(self, task_id: str, progress: int, current_step: str):
        """Updates the progress of a task."""
        if task_id in self.tasks:
            self.tasks[task_id].update({
                "status": TaskStatus.PROCESSING,
                "progress": progress,
                "current_step": current_step,
                "updated_at": datetime.now(),
            })
            print(f"Task {task_id} progress: {progress}% - {current_step}")

    def complete_task(self, task_id: str, result: CaseResults):
        """Marks a task as completed and stores the final result."""
        if task_id in self.tasks:
            self.tasks[task_id].update({
                "status": TaskStatus.COMPLETED,
                "result": result,
                "progress": 100,
                "current_step": "Analysis complete",
                "updated_at": datetime.now(),
            })
            print(f"Task {task_id} completed.")

    def fail_task(self, task_id: str, error_message: str):
        """Marks a task as failed and stores the error message."""
        if task_id in self.tasks:
            self.tasks[task_id].update({
                "status": TaskStatus.FAILED,
                "result": {"error": error_message},
                "progress": self.tasks[task_id].get("progress", 0),
                "current_step": "Task failed",
                "updated_at": datetime.now(),
            })
            print(f"Task {task_id} failed: {error_message}")

    def get_task_result(self, task_id: str) -> Optional[CaseResults]:
        """Retrieves the result of a completed task."""
        task = self.tasks.get(task_id)
        if task and task["status"] == TaskStatus.COMPLETED:
            return task["result"]
        return None