from __future__ import annotations

import json
from typing import Any

from core.service import OpsRelayService

service = OpsRelayService()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            body = json.loads(record.get("body", "{}"))
            detail = body.get("detail") if isinstance(body, dict) and "detail" in body else body
            if isinstance(detail, str): detail = json.loads(detail)
            service.process_event(detail)
        except Exception:
            failures.append({"itemIdentifier": record.get("messageId", "unknown")})
    return {"batchItemFailures": failures}
