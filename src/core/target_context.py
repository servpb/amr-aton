"""Backward-compatible target context module re-exporting unified TaskContextManager."""

from src.core.task_context import (  # noqa: F401
    TaskContext,
    TaskContextManager,
    get_task_context,
    get_target_context,
)

# Backward-compatibility alias
TargetContextManager = TaskContextManager

__all__ = [
    "TaskContext",
    "TaskContextManager",
    "TargetContextManager",
    "get_task_context",
    "get_target_context",
]
