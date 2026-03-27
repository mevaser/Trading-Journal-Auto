from __future__ import annotations


class ExecutionMappingError(Exception):
    """Raised when broker execution data cannot be mapped to ExecutionDTO safely."""
