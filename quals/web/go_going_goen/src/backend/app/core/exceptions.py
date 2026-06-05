from __future__ import annotations

class AppError(Exception):
    def __init__(self, *, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
