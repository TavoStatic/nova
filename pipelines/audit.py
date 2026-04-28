from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping, Optional


class PipelineAuditLogger:
    """Append-only audit log for governed pipeline activity."""

    def __init__(self, path: Path):
        self.path = path

    def append(
        self,
        *,
        pipeline_id: str,
        action: str,
        status: str,
        detail: str = "",
        data: Optional[Mapping[str, Any]] = None,
    ) -> None:
        event: dict[str, Any] = {
            "ts": int(time.time()),
            "pipeline_id": pipeline_id,
            "action": action,
            "status": status,
        }
        if detail:
            event["detail"] = detail
        if data:
            event["data"] = dict(data)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=True) + "\n")
        except Exception:
            pass
