from __future__ import annotations

from dataclasses import dataclass

@dataclass(slots=True)
class ProgressState:
    stage1_cleared: bool
    stage2_cleared: bool
    stage3_cleared: bool

    def as_payload(self) -> dict[str, object]:
        return {
            "stage1": {"cleared": self.stage1_cleared},
            "stage2": {"cleared": self.stage2_cleared},
            "stage3": {"cleared": self.stage3_cleared},
            "downloads": {
                "stage1": True,
                "stage2": self.stage1_cleared,
                "stage3": self.stage2_cleared,
            },
        }

EMPTY_PROGRESS = ProgressState(
    stage1_cleared=False,
    stage2_cleared=False,
    stage3_cleared=False,
)
