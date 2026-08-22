from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildError(Exception):
    code: str
    message: str
    source_id: str | None = None
    source_path: str | None = None

    def payload(self) -> dict[str, object]:
        detail: dict[str, object] = {
            "code": self.code,
            "message": self.message,
        }
        if self.source_id is not None:
            detail["source_id"] = self.source_id
        if self.source_path is not None:
            detail["source_path"] = self.source_path
        return {"ok": False, "error": detail}
