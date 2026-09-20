from __future__ import annotations

from typing import Any

from core.service import OpsRelayService

service = OpsRelayService()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    body = event.get("detail") or event
    if isinstance(body, list):
        results = [service.ingest_event(item, publish=True) for item in body]
    else:
        results = [service.ingest_event(body, publish=True)]
    return {"statusCode": 200, "processed": len(results), "events": results}
